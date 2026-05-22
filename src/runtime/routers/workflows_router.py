"""
Workflow CRUD + Node management + Python export
"""

import json
import os
import subprocess
import sys
import time
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

from .. import schemas, auth
from src.repo import runtime_models as models
from src.config import runtime_config as config
from ..workflow.commands import COMMAND_REGISTRY, list_categories, list_commands_by_category, get_container_types, get_branch_types
from ..workflow.exporter import build_python
from ..workflow.extension_runner import run_workflow_extension

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
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return wf


@router.get("/commands")
def list_commands(user=Depends(auth.get_current_user)):
    """Return the full command registry for the workflow editor."""
    return {
        "categories": list_categories(),
        "commands": list_commands_by_category(),
        "containerTypes": get_container_types(),
        "branchTypes": get_branch_types(),
    }


@router.get("/{wf_id}", response_model=schemas.WorkflowOut)
def get_workflow(wf_id: int, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    for n in wf.nodes:
        _parse_node_extra(n)
    return wf


@router.put("/{wf_id}", response_model=schemas.WorkflowOut)
def update_workflow(wf_id: int, payload: schemas.WorkflowUpdate, db: Session = Depends(get_db),
                    user=Depends(auth.get_current_user)):
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(wf, field, val)
    db.commit()
    db.refresh(wf)
    for n in wf.nodes:
        _parse_node_extra(n)
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
        _parse_node_extra(n)
    return nodes


def _parse_node_extra(node):
    """把数据库中的 JSON 字符串 extra 反序列化为 dict,供 Pydantic 输出"""
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
        type=payload.type,
        locator=payload.locator,
        locator_type=payload.locator_type,
        method=payload.method,
        action=payload.action,
        element_id=payload.element_id,
        extra=json.dumps(payload.extra or {}),
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return _parse_node_extra(node)


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
    for item in payload:
        nid = item.get("id")
        temp_id = item.get("temp_id")

        if nid and nid in existing:
            # Update existing node
            node = existing[nid]
            for field in ["parent_id", "order", "type", "locator", "locator_type", "method", "action", "element_id"]:
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
                locator=item.get("locator"),
                locator_type=item.get("locator_type"),
                method=item.get("method"),
                action=item.get("action"),
                element_id=item.get("element_id"),
                extra=json.dumps(item.get("extra") or {}),
            )
            db.add(node)
            if temp_id:
                temp_id_map[temp_id] = node

    db.flush()  # Flush to get real IDs assigned before fixing parent_id

    # Step 2: Fix parent_id references
    #   a) str  -> temp_id map (new node -> new node)
    #   b) int  -> pointing to deleted node -> set to None
    for item in payload:
        temp_id = item.get("temp_id")
        nid = item.get("id")
        parent_ref = item.get("parent_id")

        # Resolve target node object
        if temp_id and temp_id in temp_id_map:
            target_node = temp_id_map[temp_id]
        elif nid and nid in existing:
            target_node = existing[nid]
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

    db.commit()

    # Refresh and return
    nodes = (db.query(models.WorkflowNode)
               .filter(models.WorkflowNode.workflow_id == wf_id)
               .order_by(models.WorkflowNode.order)
               .all())
    for n in nodes:
        _parse_node_extra(n)
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
    return _parse_node_extra(node)


@router.delete("/{wf_id}/nodes/{node_id}")
def delete_node(wf_id: int, node_id: int, db: Session = Depends(get_db),
                user=Depends(auth.get_current_user)):
    node = db.get(models.WorkflowNode, node_id)
    if not node or node.workflow_id != wf_id:
        raise HTTPException(status_code=404, detail="Node not found")
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
        type=payload.type,
        locator=payload.locator,
        locator_type=payload.locator_type,
        method=payload.method,
        action=payload.action,
        element_id=payload.element_id,
        extra=json.dumps(payload.extra or {}),
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return _parse_node_extra(node)


@router.get("/{wf_id}/nodes/anonymous", response_model=list[schemas.WorkflowNodeOut])
def list_nodes_anonymous(wf_id: int, db: Session = Depends(get_db)):
    """免认证节点查询端点，供浏览器扩展执行工作流时拉取节点列表。"""
    nodes = (db.query(models.WorkflowNode)
               .filter(models.WorkflowNode.workflow_id == wf_id)
               .order_by(models.WorkflowNode.order)
               .all())
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


# ---------- Run workflow ----------


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
def run_workflow(wf_id: int, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    """Generate Python script from workflow and execute it in a subprocess.
    Returns stdout, stderr, and return code.
    """
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    nodes = (db.query(models.WorkflowNode)
               .filter(models.WorkflowNode.workflow_id == wf_id)
               .order_by(models.WorkflowNode.order)
               .all())

    print(f"[run_workflow] wf_id={wf_id} name='{wf.name}' nodes={len(nodes)}")

    lines = build_python(wf, nodes, config.REPO_DIR)
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
        print(f"[run_workflow] executing subprocess...")
        env = {**os.environ, "RPA_REPO_ROOT": config.REPO_DIR}
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        print(f"[run_workflow] done returncode={result.returncode} stdout_len={len(result.stdout)} stderr_len={len(result.stderr)}")
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        print(f"[run_workflow] timed out after 120s")
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


@router.post("/{wf_id}/run/extension")
async def run_workflow_extension_endpoint(wf_id: int, db: Session = Depends(get_db),
                                           user=Depends(auth.get_current_user)):
    """Run workflow via browser extension (WebSocket).
    Requires an active extension connection.
    """
    wf = db.get(models.Workflow, wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    nodes = (db.query(models.WorkflowNode)
               .filter(models.WorkflowNode.workflow_id == wf_id)
               .order_by(models.WorkflowNode.order)
               .all())

    result = await run_workflow_extension(wf, nodes)
    return result
