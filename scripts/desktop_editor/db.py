"""桌面编辑器 DB 访问层 — 直接操作 SQLAlchemy，不经过 HTTP。"""

from src.repo.models import SessionLocal, Workflow, WorkflowNode, WorkflowElement
import json


def list_workflows() -> list[dict]:
    db = SessionLocal()
    try:
        wfs = db.query(Workflow).order_by(Workflow.updated_at.desc()).all()
        return [{"id": w.id, "name": w.name, "node_count": len(w.nodes)} for w in wfs]
    finally:
        db.close()


def get_workflow(wf_id: int) -> Workflow | None:
    db = SessionLocal()
    try:
        return db.query(Workflow).filter(Workflow.id == wf_id).first()
    finally:
        db.close()


def create_workflow(name: str) -> Workflow:
    db = SessionLocal()
    try:
        wf = Workflow(name=name)
        db.add(wf)
        db.commit()
        db.refresh(wf)
        return wf
    finally:
        db.close()


def delete_workflow(wf_id: int):
    db = SessionLocal()
    try:
        wf = db.query(Workflow).filter(Workflow.id == wf_id).first()
        if wf:
            db.delete(wf)
            db.commit()
    finally:
        db.close()


def get_nodes(wf_id: int) -> list[WorkflowNode]:
    db = SessionLocal()
    try:
        return (
            db.query(WorkflowNode)
            .filter(WorkflowNode.workflow_id == wf_id, WorkflowNode.enabled == 1)
            .order_by(WorkflowNode.order)
            .all()
        )
    finally:
        db.close()


def get_all_nodes(wf_id: int) -> list[WorkflowNode]:
    """含被禁用的节点。"""
    db = SessionLocal()
    try:
        return (
            db.query(WorkflowNode)
            .filter(WorkflowNode.workflow_id == wf_id)
            .order_by(WorkflowNode.order)
            .all()
        )
    finally:
        db.close()


def add_node(wf_id: int, cmd: str, extra: dict = None,
             parent_id: int = None, order: int = None) -> WorkflowNode:
    db = SessionLocal()
    try:
        if order is None:
            max_order = (
                db.query(WorkflowNode.order)
                .filter(WorkflowNode.workflow_id == wf_id)
                .order_by(WorkflowNode.order.desc())
                .first()
            )
            order = (max_order[0] + 1) if max_order else 0

        extra_str = json.dumps(extra or {}, ensure_ascii=False)
        node = WorkflowNode(
            workflow_id=wf_id, cmd=cmd, extra=extra_str,
            parent_id=parent_id, order=order,
        )
        db.add(node)
        db.commit()
        db.refresh(node)
        return node
    finally:
        db.close()


def update_node(node_id: int, **kwargs) -> WorkflowNode | None:
    db = SessionLocal()
    try:
        node = db.query(WorkflowNode).filter(WorkflowNode.id == node_id).first()
        if not node:
            return None
        for key, val in kwargs.items():
            if key == "extra" and isinstance(val, dict):
                val = json.dumps(val, ensure_ascii=False)
            if hasattr(node, key):
                setattr(node, key, val)
        db.commit()
        db.refresh(node)
        return node
    finally:
        db.close()


def remove_node(node_id: int):
    db = SessionLocal()
    try:
        node = db.query(WorkflowNode).filter(WorkflowNode.id == node_id).first()
        if node:
            db.delete(node)
            db.commit()
    finally:
        db.close()


def reorder_nodes(wf_id: int, node_ids: list[int]):
    """按 node_ids 的顺序批量更新 order。"""
    db = SessionLocal()
    try:
        for i, nid in enumerate(node_ids):
            db.query(WorkflowNode).filter(WorkflowNode.id == nid).update({"order": i})
        db.commit()
    finally:
        db.close()


def list_elements(wf_id: int) -> list[dict]:
    db = SessionLocal()
    try:
        els = (
            db.query(WorkflowElement)
            .filter(WorkflowElement.workflow_id == wf_id)
            .all()
        )
        return [
            {
                "name": e.name,
                "element_kind": e.element_kind or "plain",
                "web_selector": e.web_selector or "",
                "target_mode": e.target_mode or "single",
            }
            for e in els
        ]
    finally:
        db.close()
