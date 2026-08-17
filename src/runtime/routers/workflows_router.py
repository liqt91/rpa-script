"""
Workflow CRUD + Node management + Python export
"""

import asyncio
import json
import logging
import math
import os
import subprocess
import sys
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import schemas, auth
from src.repo import runtime_models as models
from src.config import runtime_config as config
from src.runtime.workflow.handlers.registry import get_command
from ..workflow.handlers.registry import get_all_handlers
from ..workflow.new_catalog import load_new_catalog
from ..workflow.exporter import build_python
from ..workflow.extension_runner import (
    run_workflow_extension,
    get_active_runner,
    list_active_runners,
)
from src.providers import run_progress
from src.providers.workflow_lock import (
    MAX_CONCURRENT_WORKFLOWS,
    WorkflowConcurrencyError,
    WORKFLOW_LOCK_TIMEOUT_SECONDS,
    current_workflow_lock_capacity,
    workflow_lock,
)
from src.repo.browser_utils import detect_browser_paths
from src.service.elements_service import (
    build_element_tree,
    compute_selector_chain,
    normalize_element_capture,
    _looks_like_capture,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

# Generated workflow scripts directory
_GENERATED_DIR = os.path.join(config.REPO_DIR, "service", "local_jobs", "_generated", "workflows")
os.makedirs(_GENERATED_DIR, exist_ok=True)


def get_db():
    db = models.SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- Run logs (must register before /{wf_id}) ----------

@router.get("/runs")
def list_all_runs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user=Depends(auth.get_current_user)
):
    """List all run history across workflows."""
    rows = (db.query(models.Result, models.Workflow)
            .join(models.Workflow, models.Result.workflow_id == models.Workflow.id, isouter=True)
            .order_by(models.Result.started_at.desc())
            .limit(limit)
            .all())
    out = []
    for r, wf in rows:
        d = json.loads(r.data) if r.data else {}
        out.append({
            "id": r.id,
            "runId": r.run_id,
            "workflowId": r.workflow_id,
            "workflowName": wf.name if wf else None,
            "triggerType": r.trigger_type,
            "startedAt": r.started_at.isoformat() if r.started_at else None,
            "completedAt": r.completed_at.isoformat() if r.completed_at else None,
            "success": d.get("success"),
            "totalSteps": d.get("total_steps", 0),
            "completedSteps": r.total,
            "error": d.get("error"),
            "outputs": d.get("outputs", {}),
            "logDir": r.log_dir,
        })
    return out


@router.get("/runs/active", response_model=list[schemas.ActiveRunOut])
async def list_active_runs(
    db: Session = Depends(get_db),
    user=Depends(auth.get_current_user)
):
    """返回当前正在运行的扩展工作流列表（含流程名）。"""
    runners = await list_active_runners()
    wf_ids = {r.workflow_id for _, r in runners if r.workflow_id}
    names = {}
    if wf_ids:
        for wf in db.query(models.Workflow).filter(models.Workflow.id.in_(wf_ids)).all():
            names[wf.id] = wf.name
    return [
        {
            "run_id": rid,
            "workflow_id": r.workflow_id,
            "workflow_name": names.get(r.workflow_id, ""),
            "client_id": r.client_id,
        }
        for rid, r in runners
    ]


@router.get("/runs/status")
async def get_run_status(user=Depends(auth.get_current_user)):
    """Return concurrency lock capacity and active run summary."""
    runners = await list_active_runners()
    return {
        "maxConcurrent": MAX_CONCURRENT_WORKFLOWS,
        "activeCount": len(runners),
        "availableSlots": current_workflow_lock_capacity(),
        "activeRuns": [{"runId": rid, "clientId": r.client_id} for rid, r in runners],
    }


@router.post("/runs/active/stop", response_model=schemas.ActiveRunStopOut)
async def stop_active_run(user=Depends(auth.get_current_user)):
    """停止当前正在运行的扩展工作流（全局只有一个）。"""
    runners = await list_active_runners()
    stopped = []
    for rid, runner in runners:
        await runner.stop()
        stopped.append(rid)
    return {"success": True, "stopped": stopped}


# ---------- Workflow CRUD ----------

@router.get("", response_model=list[schemas.WorkflowListOut])
def list_workflows(db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    rows = db.query(models.Workflow).order_by(models.Workflow.created_at.desc()).all()
    return rows


@router.post("", response_model=schemas.WorkflowOut)
def create_workflow(payload: schemas.WorkflowCreate, db: Session = Depends(get_db),
                    user=Depends(auth.get_current_user)):
    wf = models.Workflow(
        name=payload.name,
        description=payload.description,
        url=payload.url,
        framework=payload.framework,
        parameters=json.dumps([p.model_dump() for p in (payload.parameters or [])], ensure_ascii=False),
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return wf


def _element_from_import_dict(workflow_id: int, e: dict) -> models.WorkflowElement:
    """把宽松的元素字典归一化为 WorkflowElement（DSH 导入用）。

    支持两种形态：
      {name, selector|web_selector, selector_family: css|xpath, ...}  最小形式
      {name, web_selector: "css:.x", css_candidates: [...], ...}     完整捕获结构
    selector 若未带 css:/xpath:/drission: 前缀且给了 selector_family，则补前缀
    （web_selector 的存储约定，见 _infer_selector_family）。
    """
    name = str(e.get("name") or "").strip()
    if not name:
        raise ValueError("元素缺少 name")
    selector = e.get("web_selector") or e.get("selector") or ""
    selector_family = e.get("selector_family") or e.get("selectorFamily") or ""
    if selector_family and selector and not str(selector).startswith(("css:", "xpath:", "drission:")):
        prefix = "xpath" if str(selector_family).lower() == "xpath" else "css"
        selector = f"{prefix}:{selector}"
    return models.WorkflowElement(
        workflow_id=workflow_id,
        name=name,
        element_type=str(e.get("element_type") or "web"),
        element_kind=str(e.get("element_kind") or "plain"),
        target_mode=str(e.get("target_mode") or "single"),
        css_candidates=json.dumps(e.get("css_candidates") or [], ensure_ascii=False),
        xpath_candidates=json.dumps(e.get("xpath_candidates") or [], ensure_ascii=False),
        drission_candidates=json.dumps(e.get("drission_candidates") or [], ensure_ascii=False),
        web_selector=str(selector),
        drission_selector=str(e.get("drission_selector") or ""),
        relative_selector=str(e.get("relative_selector") or ""),
        anchor_selector=str(e.get("anchor_selector") or ""),
        anchor_element_name=e.get("anchor_element_name"),
        anchor_mode=str(e.get("anchor_mode") or "none"),
        dom_path=json.dumps(e.get("dom_path") or [], ensure_ascii=False),
        attributes=json.dumps(e.get("attributes") or {}, ensure_ascii=False),
        screenshot=e.get("screenshot"),
        page_url=str(e.get("page_url") or ""),
    )


def _add_import_nodes(db: Session, workflow_id: int, nodes: list[dict]) -> None:
    """批量插入新节点并解析父引用（与 nodes/batch 同一套 temp_id 语义）。

    父引用优先级：temp_id（字符串）→ 同 payload 内 id（int）→ 未知则置顶层。
    任何缺失 cmd 或非法项抛 ValueError，由调用方回滚。
    """
    created: dict = {}  # str(temp_id) -> node；int(id) -> node
    for item in nodes:
        if not item.get("cmd"):
            raise ValueError(f"节点缺少 cmd: {item}")
        node = models.WorkflowNode(
            workflow_id=workflow_id,
            parent_id=None,  # 先置空，flush 后统一解析
            order=item.get("order", 0),
            cmd=item["cmd"],
            action=item.get("action"),
            element_name=item.get("element_name"),
            enabled=1 if item.get("enabled") is None else item["enabled"],
            extra=json.dumps(item.get("extra") or {}, ensure_ascii=False),
        )
        db.add(node)
        if item.get("temp_id") is not None:
            created[str(item["temp_id"])] = node
        if item.get("id") is not None:
            created[item["id"]] = node
    db.flush()  # 拿真实 id
    for item in nodes:
        ref = item.get("parent_id")
        if ref is None:
            continue
        target = created.get(str(ref)) if isinstance(ref, str) else created.get(ref)
        if target is None:
            continue  # 未知引用 → 保持顶层
        key = str(item["temp_id"]) if item.get("temp_id") is not None else item.get("id")
        node = created.get(key)
        if node is not None and node.id != target.id:
            node.parent_id = target.id


@router.post("/import", response_model=schemas.WorkflowOut)
def import_workflow(payload: schemas.WorkflowImportIn, db: Session = Depends(get_db),
                    user=Depends(auth.get_current_user)):
    """原子导入完整工作流定义（DSH 文件式构建入口）。

    一次提交 name/description/url/framework/parameters + elements + nodes，
    任何一步失败整体回滚，不产生半成品。nodes 的父引用用 temp_id 字符串。
    """
    wf = models.Workflow(
        name=payload.name,
        description=payload.description,
        url=payload.url,
        framework=payload.framework or "DrissionPage",
        parameters=json.dumps([p.model_dump() for p in (payload.parameters or [])], ensure_ascii=False),
    )
    db.add(wf)
    try:
        db.flush()
        for e in payload.elements or []:
            db.add(_element_from_import_dict(wf.id, e))
        _add_import_nodes(db, wf.id, payload.nodes or [])
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"导入失败（已回滚）：{exc}") from exc

    db.refresh(wf)
    for n in wf.nodes:
        _parse_node_fields(n)
    return wf


@router.get("/commands")
def list_commands(db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    """Return enabled commands for the workflow editor."""
    rows = db.query(models.WorkflowCommand).filter(
        models.WorkflowCommand.enabled == 1
    ).order_by(
        models.WorkflowCommand.category_order,
        models.WorkflowCommand.command_order,
    ).all()

    categories = []
    commands_by_cat = {}
    enabled_types = set()

    for row in rows:
        enabled_types.add(row.cmd)
        reg_cmd = get_command(row.cmd)
        if not reg_cmd:
            continue

        cat = row.category or reg_cmd.get("category", "其他")
        # Merge handler fields with DB customizations (label/group changes)
        handler_fields = reg_cmd.get("fields", [])
        if row.fields:
            try:
                db_fields = json.loads(row.fields)
                db_by_name = {f["name"]: f for f in db_fields if isinstance(f, dict)}
                handler_fields = [
                    {**h, **{k: v for k, v in db_by_name.get(h["name"], {}).items()
                             if k in ("label", "group", "required", "placeholder", "default")}}
                    for h in handler_fields
                ]
            except Exception:
                pass


        cmd = {
            **reg_cmd,
            "id": row.id,
            "cmd": row.cmd,
            "label": row.label or reg_cmd.get("label", row.cmd),
            "category": cat,
            "icon": row.icon or reg_cmd.get("icon", "fa-circle"),
            "iconColor": row.icon_color or reg_cmd.get("iconColor", "text-gray-500"),
            "bgColor": row.bg_color or reg_cmd.get("bgColor", "bg-gray-50"),
            "description": row.description or reg_cmd.get("description", ""),
            "isBuiltin": bool(row.is_builtin),
            "fields": handler_fields,
        }

        db_row = {"cmd": row.cmd, "handler": row.handler, "local": row.local}
        # 从 handler 注册表补充运行时元数据
        h = get_command(row.cmd)
        cmd["handler"] = db_row.get("handler") or (h["runtimes"]["extension"]["handler"] if h else None)
        cmd["local"] = db_row.get("local") or (h["runtimes"]["extension"]["local"] if h else None)
        cmd["hasRuntime"] = h["runtimes"]["extension"]["handler"] is not None if h else False

        if cat not in commands_by_cat:
            commands_by_cat[cat] = []
            categories.append(cat)
        commands_by_cat[cat].append(cmd)

    all_handlers = get_all_handlers()
    container_types = [t for t in enabled_types if all_handlers.get(t, {}).get("isContainer")]
    branch_types = [t for t in enabled_types if all_handlers.get(t, {}).get("isBranch")]

    return {
        "categories": categories,
        "commands": commands_by_cat,
        "containerTypes": container_types,
        "branchTypes": branch_types,
    }


@router.get("/commands-new")
def list_new_commands(user=Depends(auth.get_current_user)):
    """Return new-system commands defined in commands/*.json.

    The workflow editor renders these separately and marks them as 'new'
    during the migration period.
    """
    return load_new_catalog()


@router.get("/{wf_id}", response_model=schemas.WorkflowOut)
def get_workflow(wf_id: int, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    for n in wf.nodes:
        _parse_node_fields(n)
    return wf


@router.put("/{wf_id}", response_model=schemas.WorkflowOut)
def update_workflow(wf_id: int, payload: schemas.WorkflowUpdate, db: Session = Depends(get_db),
                    user=Depends(auth.get_current_user)):
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    data = payload.model_dump(exclude_unset=True)
    if "parameters" in data:
        data["parameters"] = json.dumps(data["parameters"] or [], ensure_ascii=False)
    for field, val in data.items():
        setattr(wf, field, val)
    db.commit()
    db.refresh(wf)
    for n in wf.nodes:
        _parse_node_fields(n)
    return wf


@router.delete("/{wf_id}")
def delete_workflow(wf_id: int, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    db.delete(wf)
    db.commit()
    return {"success": True}


# ---------- Node management ----------

@router.get("/{wf_id}/nodes", response_model=list[schemas.WorkflowNodeOut])
def list_nodes(wf_id: int, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    nodes = (db.query(models.WorkflowNode)
               .filter(models.WorkflowNode.workflow_id == wf_id)
               .order_by(models.WorkflowNode.order)
               .all())
    for n in nodes:
        _parse_node_fields(n)
    return nodes


def _parse_node_fields(node):
    """把数据库中的 JSON 字符串 extra/locator 反序列化为原生对象,供 Pydantic 输出。
    反序列化前将对象从 SQLAlchemy session 中 expunge，避免 dict 类型触发 dirty tracking
    导致后续 commit 时生成 UPDATE 语句（SQLite 不支持 dict 参数绑定）。"""
    from sqlalchemy.orm import object_session
    from sqlalchemy import inspect as sa_inspect

    sess = object_session(node)
    if sess and sa_inspect(node).persistent:
        sess.expunge(node)

    if node.extra and isinstance(node.extra, str):
        try:
            node.extra = json.loads(node.extra)
        except Exception:
            node.extra = {}
    return node


@router.post("/{wf_id}/nodes", response_model=schemas.WorkflowNodeOut)
def add_node(wf_id: int, payload: schemas.WorkflowNodeIn, db: Session = Depends(get_db),
             user=Depends(auth.get_current_user)):
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # auto-assign order if not provided
    order = payload.order
    if order == 0:
        last = (db.query(models.WorkflowNode)
                  .filter(models.WorkflowNode.workflow_id == wf_id)
                  .order_by(models.WorkflowNode.order.desc())
                  .first())
        order = (last.order + 1) if last else 1

    node = models.WorkflowNode(
        workflow_id=wf_id,
        parent_id=payload.parent_id,
        order=order,
        cmd=payload.cmd,
        action=payload.action,
        element_name=payload.element_name,
        enabled=1 if payload.enabled is None else payload.enabled,
        extra=json.dumps(payload.extra or {}),
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return _parse_node_fields(node)


@router.put("/{wf_id}/nodes/batch")
def batch_update_nodes(wf_id: int, payload: List[dict] = Body(...),
                       db: Session = Depends(get_db),
                       user=Depends(auth.get_current_user)):
    """Batch sync: replace entire node list for a workflow.
    Supports temp_id for new nodes (auto parent_id resolution).
    Payload: list of node dicts with optional 'id' or 'temp_id'.
    Existing nodes not in payload are deleted.
    """
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    existing = {n.id: n for n in db.query(models.WorkflowNode).filter(models.WorkflowNode.workflow_id == wf_id).all()}
    incoming_ids = {item.get("id") for item in payload if item.get("id")}
    deleted_ids = {nid for nid in existing.keys() if nid not in incoming_ids}

    # Delete nodes not in payload
    for nid in list(existing.keys()):
        if nid not in incoming_ids:
            db.delete(existing[nid])

    # Step 1: Create / update all nodes, record temp_id -> node mapping
    temp_id_map: dict[str, models.WorkflowNode] = {}
    new_id_map: dict[int, models.WorkflowNode] = {}   # track newly created nodes by their original id
    for item in payload:
        nid = item.get("id")
        temp_id = item.get("temp_id")

        if nid and nid in existing:
            # Update existing node
            node = existing[nid]
            fields = [
                "parent_id", "order", "type", "action",
                "element_name", "enabled",
            ]
            for field in fields:
                if field in item:
                    setattr(node, field, item[field])
            if "extra" in item:
                node.extra = json.dumps(item["extra"] or {})
        else:
            # Create new node
            node = models.WorkflowNode(
                workflow_id=wf_id,
                parent_id=item.get("parent_id"),
                order=item.get("order", 0),
                cmd=item["cmd"],
                action=item.get("action"),
                element_name=item.get("element_name"),
                enabled=1 if item.get("enabled") is None else item["enabled"],
                extra=json.dumps(item.get("extra") or {}),
            )
            db.add(node)
            if temp_id:
                temp_id_map[temp_id] = node
            if nid is not None:
                new_id_map[nid] = node

    db.flush()  # Flush to get real IDs assigned before fixing parent_id

    # Step 2: Fix parent_id references
    #   a) str  -> temp_id map (new node -> new node)
    #   b) int  -> pointing to deleted node -> set to None
    #   c) int  -> newly created node id -> map to real id
    for item in payload:
        temp_id = item.get("temp_id")
        nid = item.get("id")
        parent_ref = item.get("parent_id")

        # Resolve target node object
        if temp_id and temp_id in temp_id_map:
            target_node = temp_id_map[temp_id]
        elif nid and nid in existing:
            target_node = existing[nid]
        elif nid and nid in new_id_map:
            target_node = new_id_map[nid]
        else:
            continue

        if parent_ref is None:
            continue

        # Case A: parent_ref is a deleted node id -> orphan, promote to top-level
        if isinstance(parent_ref, int) and parent_ref in deleted_ids:
            target_node.parent_id = None
            continue

        # Case B: parent_ref is a temp_id -> map to real id
        if isinstance(parent_ref, str) and parent_ref in temp_id_map:
            target_node.parent_id = temp_id_map[parent_ref].id
            continue

        # Case C: parent_ref is an integer id of a newly created node -> map to real id
        if isinstance(parent_ref, int) and parent_ref in new_id_map:
            target_node.parent_id = new_id_map[parent_ref].id

    db.commit()

    # Refresh and return
    nodes = (db.query(models.WorkflowNode)
               .filter(models.WorkflowNode.workflow_id == wf_id)
               .order_by(models.WorkflowNode.order)
               .all())
    for n in nodes:
        _parse_node_fields(n)
    return nodes


@router.put("/{wf_id}/nodes/{node_id}", response_model=schemas.WorkflowNodeOut)
def update_node(wf_id: int, node_id: int, payload: schemas.WorkflowNodeIn,
                db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    node = db.get(models.WorkflowNode, node_id)
    if not node or node.workflow_id != wf_id:
        raise HTTPException(status_code=404, detail="Node not found")
    for field, val in payload.model_dump(exclude_unset=True).items():
        if field == "extra":
            setattr(node, field, json.dumps(val or {}))
        else:
            setattr(node, field, val)
    db.commit()
    db.refresh(node)
    return _parse_node_fields(node)


@router.delete("/{wf_id}/nodes/{node_id}")
def delete_node(wf_id: int, node_id: int, db: Session = Depends(get_db),
                user=Depends(auth.get_current_user)):
    node = db.get(models.WorkflowNode, node_id)
    if not node or node.workflow_id != wf_id:
        raise HTTPException(status_code=404, detail="Node not found")

    # Cascade delete all descendants
    def delete_children(nid):
        children = db.query(models.WorkflowNode).filter(models.WorkflowNode.parent_id == nid).all()
        for child in children:
            delete_children(child.id)
            db.delete(child)

    delete_children(node_id)
    db.delete(node)
    db.commit()
    return {"success": True}


# ---------- Anonymous node capture (for browser extension dev) ----------

@router.post("/{wf_id}/nodes/anonymous", response_model=schemas.WorkflowNodeOut)
def add_node_anonymous(wf_id: int, payload: schemas.WorkflowNodeIn, db: Session = Depends(get_db)):
    """免认证节点写入端点，仅供浏览器扩展开发阶段快速录入步骤使用。
    生产环境建议通过 /api/auth/login 获取 JWT 后调用认证端点。
    """
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    order = payload.order
    if order == 0:
        last = (db.query(models.WorkflowNode)
                  .filter(models.WorkflowNode.workflow_id == wf_id)
                  .order_by(models.WorkflowNode.order.desc())
                  .first())
        order = (last.order + 1) if last else 1

    node = models.WorkflowNode(
        workflow_id=wf_id,
        parent_id=payload.parent_id,
        order=order,
        cmd=payload.cmd,
        action=payload.action,
        element_name=payload.element_name,
        enabled=1 if payload.enabled is None else payload.enabled,
        extra=json.dumps(payload.extra or {}),
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return _parse_node_fields(node)


@router.get("/{wf_id}/nodes/anonymous", response_model=list[schemas.WorkflowNodeOut])
def list_nodes_anonymous(wf_id: int, db: Session = Depends(get_db)):
    """免认证节点查询端点，供浏览器扩展执行工作流时拉取节点列表。"""
    nodes = (db.query(models.WorkflowNode)
               .filter(models.WorkflowNode.workflow_id == wf_id)
               .order_by(models.WorkflowNode.order)
               .all())
    for n in nodes:
        _parse_node_fields(n)
    return nodes


@router.post("/{wf_id}/nodes/reorder")
def reorder_nodes(wf_id: int, orders: list[dict], db: Session = Depends(get_db),
                  user=Depends(auth.get_current_user)):
    """orders: [{"id": 1, "order": 2, "parent_id": null}, ...]"""
    for item in orders:
        node = db.get(models.WorkflowNode, item["id"])
        if node and node.workflow_id == wf_id:
            node.order = item.get("order", node.order)
            if "parent_id" in item:
                node.parent_id = item["parent_id"]
    db.commit()
    return {"success": True}


# ---------- Workflow Elements (per-workflow element library) ----------

@router.get("/{wf_id}/elements", response_model=list[schemas.WorkflowElementOut])
def list_workflow_elements(wf_id: int, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    """List all elements in a workflow's element library."""
    items = (
        db.query(models.WorkflowElement)
        .filter(models.WorkflowElement.workflow_id == wf_id)
        .order_by(models.WorkflowElement.created_at.desc())
        .all()
    )
    for item in items:
        try:
            item.css_candidates = json.loads(item.css_candidates) if item.css_candidates else []
        except Exception:
            item.css_candidates = []
        try:
            item.xpath_candidates = json.loads(item.xpath_candidates) if item.xpath_candidates else []
        except Exception:
            item.xpath_candidates = []
        try:
            item.drission_candidates = json.loads(item.drission_candidates) if item.drission_candidates else []
        except Exception:
            item.drission_candidates = []
        try:
            item.dom_path = json.loads(item.dom_path) if item.dom_path else []
        except Exception:
            item.dom_path = []
        try:
            item.attributes = json.loads(item.attributes) if item.attributes else {}
        except Exception:
            item.attributes = {}
    # Enrich tree/chain derived fields for the flat list.
    children_map: dict[str, list[str]] = {}
    for item in items:
        parent = item.anchor_element_name
        if parent:
            children_map.setdefault(parent, []).append(item.name)
    for item in items:
        item.parent_name = item.anchor_element_name or None
        item.children = children_map.get(item.name, [])
        # 列表接口剥离 base64 截图（单元素详情接口 by-name 仍返回），避免列表随元素数膨胀
        item.screenshot = None
    return items


def _resolve_element_payload(payload: schemas.WorkflowElementIn) -> dict:
    """Resolve DB field values from a WorkflowElementIn payload.

    When attributes is an ElementInfo-shaped capture (from the unified capture
    tool), normalize it into canonical columns so web_selector/candidates/dom_path
    are populated and desktop elements get a `path` the runtime can consume.
    """
    fields = {
        "name": payload.name,
        "element_type": payload.element_type,
        "element_kind": payload.element_kind,
        "target_mode": payload.target_mode,
        "css_candidates": payload.css_candidates,
        "xpath_candidates": payload.xpath_candidates,
        "drission_candidates": payload.drission_candidates,
        "web_selector": payload.web_selector,
        "drission_selector": payload.drission_selector,
        "relative_selector": payload.relative_selector,
        "anchor_selector": payload.anchor_selector,
        "anchor_element_name": payload.anchor_element_name,
        "anchor_mode": payload.anchor_mode,
        "dom_path": payload.dom_path,
        "attributes": payload.attributes,
        "screenshot": payload.screenshot,
        "page_url": payload.page_url,
    }
    if _looks_like_capture(payload.attributes):
        norm = normalize_element_capture(payload.attributes)
        fields.update({k: norm.get(k) for k in (
            "element_type", "element_kind", "web_selector", "drission_selector",
            "css_candidates", "xpath_candidates", "drission_candidates",
            "dom_path", "attributes", "screenshot", "page_url",
        )})
        if not fields["name"]:
            fields["name"] = norm.get("name") or "捕获元素"
    return fields


@router.post("/{wf_id}/elements", response_model=schemas.WorkflowElementOut)
def create_workflow_element(
    wf_id: int, payload: schemas.WorkflowElementIn,
    db: Session = Depends(get_db), user=Depends(auth.get_current_user)
):
    """Create a new element in the workflow's element library."""
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    f = _resolve_element_payload(payload)
    el = models.WorkflowElement(
        workflow_id=wf_id,
        name=f["name"],
        element_type=f["element_type"],
        element_kind=f["element_kind"],
        target_mode=f["target_mode"],
        css_candidates=json.dumps(f["css_candidates"]),
        xpath_candidates=json.dumps(f["xpath_candidates"]),
        drission_candidates=json.dumps(f["drission_candidates"]),
        web_selector=f["web_selector"],
        drission_selector=f["drission_selector"],
        relative_selector=f["relative_selector"],
        anchor_selector=f["anchor_selector"],
        anchor_element_name=f["anchor_element_name"],
        anchor_mode=f["anchor_mode"],
        dom_path=json.dumps(f["dom_path"]),
        attributes=json.dumps(f["attributes"]),
        screenshot=f["screenshot"],
        page_url=f["page_url"],
    )
    db.add(el)
    db.commit()
    db.refresh(el)
    try:
        el.css_candidates = json.loads(el.css_candidates) if el.css_candidates else []
    except Exception:
        el.css_candidates = []
    try:
        el.xpath_candidates = json.loads(el.xpath_candidates) if el.xpath_candidates else []
    except Exception:
        el.xpath_candidates = []
    try:
        el.drission_candidates = json.loads(el.drission_candidates) if el.drission_candidates else []
    except Exception:
        el.drission_candidates = []
    try:
        el.dom_path = json.loads(el.dom_path) if el.dom_path else []
    except Exception:
        el.dom_path = []
    try:
        el.attributes = json.loads(el.attributes) if el.attributes else {}
    except Exception:
        el.attributes = {}
    return el


@router.put("/{wf_id}/elements/{el_id}", response_model=schemas.WorkflowElementOut)
def update_workflow_element(
    wf_id: int, el_id: int, payload: schemas.WorkflowElementIn,
    db: Session = Depends(get_db), user=Depends(auth.get_current_user)
):
    """Update an element in the workflow's element library."""
    el = db.query(models.WorkflowElement).filter(
        models.WorkflowElement.id == el_id,
        models.WorkflowElement.workflow_id == wf_id,
    ).first()
    if not el:
        raise HTTPException(status_code=404, detail="Element not found")
    f = _resolve_element_payload(payload)
    el.name = f["name"]
    el.element_type = f["element_type"]
    el.element_kind = f["element_kind"]
    el.target_mode = f["target_mode"]
    el.css_candidates = json.dumps(f["css_candidates"])
    el.xpath_candidates = json.dumps(f["xpath_candidates"])
    el.drission_candidates = json.dumps(f["drission_candidates"])
    el.web_selector = f["web_selector"]
    el.drission_selector = f["drission_selector"]
    el.relative_selector = f["relative_selector"]
    el.anchor_selector = f["anchor_selector"]
    el.anchor_element_name = f["anchor_element_name"]
    el.anchor_mode = f["anchor_mode"]
    el.dom_path = json.dumps(f["dom_path"])
    el.attributes = json.dumps(f["attributes"])
    if f["screenshot"] is not None:
        el.screenshot = f["screenshot"]
    if f["page_url"] is not None:
        el.page_url = f["page_url"]
    db.commit()
    db.refresh(el)
    try:
        el.css_candidates = json.loads(el.css_candidates) if el.css_candidates else []
    except Exception:
        el.css_candidates = []
    try:
        el.xpath_candidates = json.loads(el.xpath_candidates) if el.xpath_candidates else []
    except Exception:
        el.xpath_candidates = []
    try:
        el.drission_candidates = json.loads(el.drission_candidates) if el.drission_candidates else []
    except Exception:
        el.drission_candidates = []
    try:
        el.dom_path = json.loads(el.dom_path) if el.dom_path else []
    except Exception:
        el.dom_path = []
    try:
        el.attributes = json.loads(el.attributes) if el.attributes else {}
    except Exception:
        el.attributes = {}
    return el


@router.delete("/{wf_id}/elements/{el_id}")
def delete_workflow_element(
    wf_id: int, el_id: int,
    db: Session = Depends(get_db), user=Depends(auth.get_current_user)
):
    """Delete an element from the workflow's element library."""
    el = db.query(models.WorkflowElement).filter(
        models.WorkflowElement.id == el_id,
        models.WorkflowElement.workflow_id == wf_id,
    ).first()
    if not el:
        raise HTTPException(status_code=404, detail="Element not found")
    db.delete(el)
    db.commit()
    return {"success": True}


@router.get("/{wf_id}/elements/by-name/{name}", response_model=schemas.WorkflowElementOut)
def get_workflow_element_by_name(
    wf_id: int, name: str,
    db: Session = Depends(get_db), user=Depends(auth.get_current_user)
):
    """Get an element by name from the workflow's element library."""
    el = db.query(models.WorkflowElement).filter(
        models.WorkflowElement.workflow_id == wf_id,
        models.WorkflowElement.name == name,
    ).first()
    if not el:
        raise HTTPException(status_code=404, detail="Element not found")
    try:
        el.css_candidates = json.loads(el.css_candidates) if el.css_candidates else []
    except Exception:
        el.css_candidates = []
    try:
        el.xpath_candidates = json.loads(el.xpath_candidates) if el.xpath_candidates else []
    except Exception:
        el.xpath_candidates = []
    try:
        el.drission_candidates = json.loads(el.drission_candidates) if el.drission_candidates else []
    except Exception:
        el.drission_candidates = []
    try:
        el.dom_path = json.loads(el.dom_path) if el.dom_path else []
    except Exception:
        el.dom_path = []
    try:
        el.attributes = json.loads(el.attributes) if el.attributes else {}
    except Exception:
        el.attributes = {}
    return el


@router.get("/{wf_id}/elements/tree")
def get_workflow_element_tree(
    wf_id: int,
    db: Session = Depends(get_db),
    user=Depends(auth.get_current_user),
):
    """Return the workflow's element library as a nested tree."""
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    items = (
        db.query(models.WorkflowElement)
        .filter(models.WorkflowElement.workflow_id == wf_id)
        .all()
    )
    tree, orphans = build_element_tree(items)
    return {"roots": tree, "orphans": orphans}


@router.get("/{wf_id}/elements/{name}/chain", response_model=schemas.WorkflowElementChainOut)
def get_workflow_element_chain(
    wf_id: int,
    name: str,
    db: Session = Depends(get_db),
    user=Depends(auth.get_current_user),
):
    """Compute the effective selector chain for an element."""
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    items = (
        db.query(models.WorkflowElement)
        .filter(models.WorkflowElement.workflow_id == wf_id)
        .all()
    )
    try:
        result = compute_selector_chain(items, name)
    except ValueError as e:
        return schemas.WorkflowElementChainOut(
            name=name, chain=[], error=str(e)
        )
    if not result:
        raise HTTPException(status_code=404, detail="Element not found")
    return schemas.WorkflowElementChainOut(**result)


# ---------- Export to Python ----------

@router.get("/{wf_id}/export/python")
def export_python(wf_id: int, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    """Export workflow as DrissionPage Python script."""
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    nodes = (db.query(models.WorkflowNode)
               .filter(models.WorkflowNode.workflow_id == wf_id)
               .order_by(models.WorkflowNode.order)
               .all())

    lines = build_python(wf, nodes, config.REPO_DIR)
    return {"success": True, "python": "\n".join(lines)}


# ---------- Run workflow ----------

@router.post("/{wf_id}/run")
def run_workflow(
    wf_id: int,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    user=Depends(auth.get_current_user)
):
    """Generate Python script from workflow and execute it in a subprocess.
    Returns stdout, stderr, and return code.
    Optional body: {"parameters": {"postUrl": "..."}}
    """
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    nodes = (db.query(models.WorkflowNode)
               .filter(models.WorkflowNode.workflow_id == wf_id)
               .order_by(models.WorkflowNode.order)
               .all())

    print(f"[run_workflow] wf_id={wf_id} name='{wf.name}' nodes={len(nodes)}")

    parameters = payload.get("parameters") or {}
    lines = build_python(wf, nodes, config.REPO_DIR, initial_params=parameters)
    code = "\n".join(lines)

    # Write to local_jobs/_generated/workflows/{uuid}/main.py (overwrite each run)
    wf_dir = os.path.join(_GENERATED_DIR, wf.uuid)
    os.makedirs(wf_dir, exist_ok=True)
    path = os.path.join(wf_dir, "main.py")
    print(f"[run_workflow] generated script: {path}")

    # Restore write permission if file exists from previous run
    if os.path.exists(path):
        os.chmod(path, 0o644)
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    # Make read-only so users don't accidentally edit generated files
    os.chmod(path, 0o444)

    try:
        # Run with a 120-second timeout, inject repo root so generated script can import shared.chrome_utils
        print("[run_workflow] executing subprocess...")
        env = {**os.environ, "RPA_REPO_ROOT": config.REPO_DIR}
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        print(
            f"[run_workflow] done returncode={result.returncode} "
            f"stdout_len={len(result.stdout)} stderr_len={len(result.stderr)}"
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        print("[run_workflow] timed out after 120s")
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "Workflow execution timed out (120s)",
        }
    except Exception as e:
        print(f"[run_workflow] error: {e}")
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
        }


@router.get("/{wf_id}/run/stream")
async def run_workflow_stream(wf_id: int, run_id: str = Query(...), user=Depends(auth.get_current_user)):
    """SSE stream of workflow execution progress.
    Connect before or concurrently with POST /run/extension.
    """
    queue = await run_progress.get(run_id)
    if not queue:
        # Poll up to 10s for the runner to start and register its queue
        for _ in range(200):
            queue = await run_progress.get(run_id)
            if queue:
                break
            await asyncio.sleep(0.05)
    if not queue:
        async def _empty():
            yield f"data: {json.dumps({'type': 'error', 'error': 'Run not found or already finished'})}\n\n"
        return StreamingResponse(_empty(), media_type="text/event-stream")

    async def event_generator():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=60.0)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "done":
                    break
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            except Exception:
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ─── Pause / Resume / Stop controls ───────────────────────────────

@router.post("/{wf_id}/run/{run_id}/pause")
async def pause_run(wf_id: int, run_id: str, user=Depends(auth.get_current_user)):
    runner = await get_active_runner(run_id)
    print(f"[pause_run] run_id={run_id} found={runner is not None}")
    if runner:
        runner.pause()
    return {"success": True, "runId": run_id, "action": "pause"}


@router.post("/{wf_id}/run/{run_id}/resume")
async def resume_run(wf_id: int, run_id: str, user=Depends(auth.get_current_user)):
    runner = await get_active_runner(run_id)
    print(f"[resume_run] run_id={run_id} found={runner is not None}")
    if runner:
        runner.resume()
    return {"success": True, "runId": run_id, "action": "resume"}


@router.post("/{wf_id}/run/{run_id}/stop")
async def stop_run(wf_id: int, run_id: str, user=Depends(auth.get_current_user)):
    runner = await get_active_runner(run_id)
    print(f"[stop_run] run_id={run_id} found={runner is not None}")
    if runner:
        await runner.stop()
    return {"success": True, "runId": run_id, "action": "stop", "found": runner is not None}


async def _run_extension_async(
    wf_id: int, *,
    run_id: str,
    log_dir: str,
    initial_table_data: dict | None,
    parameters: dict,
    trigger_type: str,
) -> None:
    """后台执行一次扩展运行（async 模式），完成后回写 Result 行。

    使用独立 DB 会话（请求会话已随响应关闭）；任何异常兜底标记失败，
    避免悬挂的 running 记录。容量不足时同样记失败（与阻塞模式 503 语义一致）。
    """
    result: dict = {}
    success = False
    error = None
    try:
        db = models.SessionLocal()
        try:
            wf = db.get(models.Workflow, wf_id)
            if wf is None:
                error = f"Workflow {wf_id} not found"
                return
            nodes = (db.query(models.WorkflowNode)
                     .filter(models.WorkflowNode.workflow_id == wf_id)
                     .order_by(models.WorkflowNode.order)
                     .all())
            for n in nodes:
                _parse_node_fields(n)
        finally:
            db.close()

        async with workflow_lock():
            result = await run_workflow_extension(
                wf, nodes,
                run_id=run_id,
                initial_table_data=initial_table_data,
                initial_parameters=parameters,
                trigger_type=trigger_type,
            )
        success = bool(result.get("success"))
        error = result.get("error")
    except WorkflowConcurrencyError as exc:
        error = f"Workflow execution capacity full: {exc}"
    except Exception as exc:  # noqa: BLE001 —— 后台任务必须兜底
        logger.exception("[async run] wf=%s run=%s failed", wf_id, run_id)
        error = f"Async run error: {exc}"

    db = models.SessionLocal()
    try:
        row = (db.query(models.Result)
               .filter(models.Result.workflow_id == wf_id, models.Result.run_id == run_id)
               .first())
        if row:
            row.total = result.get("completedSteps", 0)
            row.data = json.dumps({
                "workflow_id": wf_id,
                "mode": "extension",
                "async": True,
                "success": success,
                "total_steps": result.get("totalSteps"),
                "failed_steps": result.get("failedSteps"),
                "error": error,
                "outputs": result.get("outputs", {}),
            }, ensure_ascii=False)
            row.completed_at = datetime.now()
            db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("[async run] failed to persist Result wf=%s run=%s", wf_id, run_id)
    finally:
        db.close()


@router.post("/{wf_id}/run/extension")
async def run_workflow_extension_endpoint(
    wf_id: int,
    run_id: str = Query(default=""),
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    user=Depends(auth.get_current_user)
):
    """Run workflow via browser extension (WebSocket).
    Supply run_id (e.g. a UUID) so the matching SSE stream can receive progress.
    Optional body: {"initialTableData": {...}, "parameters": {"postUrl": "..."}}
    Body 带 "async": true 时立即返回 {runId, status:"started"}，后台执行；
    进度经 GET /{wf_id}/runs/{run_id}/log（或 SSE /run/stream）查询。
    """
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    nodes = (db.query(models.WorkflowNode)
               .filter(models.WorkflowNode.workflow_id == wf_id)
               .order_by(models.WorkflowNode.order)
               .all())
    for n in nodes:
        _parse_node_fields(n)

    initial_table_data = payload.get("initialTableData")
    parameters = payload.get("parameters") or {}
    trigger_type = payload.get("triggerType", "manual")

    # ---------- async 模式：立即返回，后台执行 ----------
    if payload.get("async"):
        if current_workflow_lock_capacity() <= 0:
            raise HTTPException(
                status_code=503,
                detail="Workflow execution capacity full. Please retry later.",
                headers={"Retry-After": str(math.ceil(WORKFLOW_LOCK_TIMEOUT_SECONDS))},
            )
        import time as _t
        _run_id = run_id or f"run_{int(_t.time() * 1000)}"
        log_root = os.environ.get("RPA_LOG_DIR") or config.DATA_DIR
        log_dir = os.path.join(log_root, "run_logs", str(wf.id), _run_id)
        os.makedirs(log_dir, exist_ok=True)
        # 预写 Result 行：运行期间 get_run_log 即可查到（running 状态）
        db.add(models.Result(
            workflow_id=wf.id,
            run_id=_run_id,
            url=wf.url or "",
            trigger_type=trigger_type,
            log_dir=log_dir,
            started_at=datetime.now(),
            data=json.dumps({"mode": "extension", "async": True, "success": None}, ensure_ascii=False),
        ))
        db.commit()
        asyncio.create_task(_run_extension_async(
            wf.id,
            run_id=_run_id,
            log_dir=log_dir,
            initial_table_data=initial_table_data,
            parameters=parameters,
            trigger_type=trigger_type,
        ))
        return {"runId": _run_id, "status": "started", "workflowId": wf.id, "logDir": log_dir}

    # ---------- 阻塞模式（原行为不变） ----------
    import datetime as _dt
    started_at = _dt.datetime.now()

    try:
        async with workflow_lock():
            result = await run_workflow_extension(
                wf, nodes,
                run_id=run_id or None,
                initial_table_data=initial_table_data,
                initial_parameters=parameters,
                trigger_type=trigger_type,
            )
    except WorkflowConcurrencyError:
        raise HTTPException(
            status_code=503,
            detail="Workflow execution capacity full. Please retry later.",
            headers={"Retry-After": str(math.ceil(WORKFLOW_LOCK_TIMEOUT_SECONDS))},
        )
    completed_at = _dt.datetime.now()

    # Save run log to Result table
    try:
        log = models.Result(
            task_id=None,
            workflow_id=wf_id,
            run_id=result.get("runId", run_id or ""),
            url=wf.url or "",
            total=result.get("completedSteps", 0),
            data=json.dumps({
                "workflow_id": wf_id,
                "mode": "extension",
                "success": result.get("success"),
                "total_steps": result.get("totalSteps"),
                "failed_steps": result.get("failedSteps"),
                "error": result.get("error"),
                "outputs": result.get("outputs", {}),
            }),
            client_id=None,
            trigger_type=trigger_type,
            log_dir=result.get("logDir", ""),
            started_at=started_at,
            completed_at=completed_at,
        )
        db.add(log)
        db.commit()
    except Exception as e:
        print(f"[WorkflowsRouter] failed to save run log: {e}")

    return result


@router.get("/{wf_id}/runs")
def list_workflow_runs(
    wf_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user=Depends(auth.get_current_user)
):
    """List run history for a workflow."""
    rows = (db.query(models.Result)
            .filter(models.Result.workflow_id == wf_id)
            .order_by(models.Result.started_at.desc())
            .limit(limit)
            .all())
    out = []
    for r in rows:
        d = json.loads(r.data) if r.data else {}
        out.append({
            "id": r.id,
            "runId": r.run_id,
            "workflowId": r.workflow_id,
            "triggerType": r.trigger_type,
            "startedAt": r.started_at.isoformat() if r.started_at else None,
            "completedAt": r.completed_at.isoformat() if r.completed_at else None,
            "success": d.get("success"),
            "totalSteps": d.get("total_steps", 0),
            "completedSteps": r.total,
            "error": d.get("error"),
            "outputs": d.get("outputs", {}),
            "logDir": r.log_dir,
        })
    return out


@router.get("/{wf_id}/runs/{run_id}/log")
def get_run_log(
    wf_id: int,
    run_id: str,
    db: Session = Depends(get_db),
    user=Depends(auth.get_current_user)
):
    """Read persisted run log file."""
    row = (db.query(models.Result)
           .filter(models.Result.workflow_id == wf_id, models.Result.run_id == run_id)
           .first())
    if not row or not row.log_dir:
        raise HTTPException(status_code=404, detail="Run log not found")
    log_path = os.path.join(row.log_dir, "run.log")
    if not os.path.exists(log_path):
        # async 模式：run.log 由 runner 启动后创建；尚未生成且未结束 → 运行中
        if row.completed_at is None:
            return {"events": [], "running": True, "runId": run_id}
        raise HTTPException(status_code=404, detail="Log file not found")
    with open(log_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except Exception:
            events.append({"raw": line})
    return {"events": events, "running": row.completed_at is None, "runId": run_id}


@router.get("/{wf_id}/runs/{run_id}/table")
def get_run_table(
    wf_id: int,
    run_id: str,
    db: Session = Depends(get_db),
    user=Depends(auth.get_current_user)
):
    """Read persisted run table file."""
    row = (db.query(models.Result)
           .filter(models.Result.workflow_id == wf_id, models.Result.run_id == run_id)
           .first())
    if not row or not row.log_dir:
        raise HTTPException(status_code=404, detail="Run table not found")
    table_path = os.path.join(row.log_dir, "table.json")
    if not os.path.exists(table_path):
        raise HTTPException(status_code=404, detail="Table file not found")
    with open(table_path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.post("/{wf_id}/runs/{run_id}/open-folder")
def open_run_folder(
    wf_id: int,
    run_id: str,
    db: Session = Depends(get_db),
    user=Depends(auth.get_current_user)
):
    """在文件资源管理器中打开日志所在文件夹（仅支持本地运行）。"""
    row = (db.query(models.Result)
           .filter(models.Result.workflow_id == wf_id, models.Result.run_id == run_id)
           .first())
    if not row or not row.log_dir:
        raise HTTPException(status_code=404, detail="Run log folder not found")
    if not os.path.exists(row.log_dir):
        raise HTTPException(status_code=404, detail="Log folder does not exist")
    if os.name == 'nt':
        os.startfile(row.log_dir)
    else:
        subprocess.Popen(['xdg-open', row.log_dir])
    return {"opened": True, "path": row.log_dir}


# ---------- Browser detection ----------

@router.get("/system/browser-paths")
def get_browser_paths(user=Depends(auth.get_current_user)):
    """检测系统中 Chrome 和 Edge 的安装路径。"""
    return detect_browser_paths()
