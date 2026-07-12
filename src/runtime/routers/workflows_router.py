"""
Workflow CRUD + Node management + Python export
"""

import asyncio
import json
import math
import os
import subprocess
import sys
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
from src.service.elements_service import build_element_tree, compute_selector_chain

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
        parameters=json.dumps(payload.parameters or [], ensure_ascii=False),
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
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
                type=item["type"],
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
    return items


@router.post("/{wf_id}/elements", response_model=schemas.WorkflowElementOut)
def create_workflow_element(
    wf_id: int, payload: schemas.WorkflowElementIn,
    db: Session = Depends(get_db), user=Depends(auth.get_current_user)
):
    """Create a new element in the workflow's element library."""
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    el = models.WorkflowElement(
        workflow_id=wf_id,
        name=payload.name,
        target_mode=payload.target_mode,
        css_candidates=json.dumps(payload.css_candidates),
        xpath_candidates=json.dumps(payload.xpath_candidates),
        drission_candidates=json.dumps(payload.drission_candidates),
        web_selector=payload.web_selector,
        drission_selector=payload.drission_selector,
        relative_selector=payload.relative_selector,
        anchor_selector=payload.anchor_selector,
        anchor_element_name=payload.anchor_element_name,
        anchor_mode=payload.anchor_mode,
        dom_path=json.dumps(payload.dom_path),
        attributes=json.dumps(payload.attributes),
        screenshot=payload.screenshot,
        page_url=payload.page_url,
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
    el.name = payload.name
    el.target_mode = payload.target_mode
    el.css_candidates = json.dumps(payload.css_candidates)
    el.xpath_candidates = json.dumps(payload.xpath_candidates)
    el.drission_candidates = json.dumps(payload.drission_candidates)
    el.web_selector = payload.web_selector
    el.drission_selector = payload.drission_selector
    el.relative_selector = payload.relative_selector
    el.anchor_selector = payload.anchor_selector
    el.anchor_element_name = payload.anchor_element_name
    el.anchor_mode = payload.anchor_mode
    el.dom_path = json.dumps(payload.dom_path)
    el.attributes = json.dumps(payload.attributes)
    if payload.screenshot is not None:
        el.screenshot = payload.screenshot
    if payload.page_url is not None:
        el.page_url = payload.page_url
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
    import datetime as _dt
    started_at = _dt.datetime.now()

    try:
        async with workflow_lock():
            result = await run_workflow_extension(
                wf, nodes,
                run_id=run_id or None,
                initial_table_data=initial_table_data,
                initial_parameters=parameters,
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
            trigger_type=payload.get("triggerType", "manual"),
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
        raise HTTPException(status_code=404, detail="Log file not found")
    with open(log_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except Exception:
            events.append({"raw": line})
    return {"events": events}


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
