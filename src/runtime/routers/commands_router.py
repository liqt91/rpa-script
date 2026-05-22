"""
Workflow command CRUD + CSV export.
"""

import csv
import io
import json
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import auth
from src.repo import runtime_models as models

router = APIRouter(prefix="/api/commands", tags=["commands"])


def get_db():
    db = models.SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("")
def list_commands(
    category: str = Query(None),
    enabled_only: bool = Query(True),
    db: Session = Depends(get_db),
    user=Depends(auth.get_current_user),
):
    q = db.query(models.WorkflowCommand)
    if enabled_only:
        q = q.filter(models.WorkflowCommand.enabled == 1)
    if category:
        q = q.filter(models.WorkflowCommand.category == category)
    rows = q.order_by(models.WorkflowCommand.category, models.WorkflowCommand.id).all()
    return [
        {
            "id": r.id,
            "type": r.type,
            "label": r.label,
            "category": r.category,
            "icon": r.icon,
            "iconColor": r.icon_color,
            "bgColor": r.bg_color,
            "isContainer": bool(r.is_container),
            "isBranch": bool(r.is_branch),
            "isStructural": bool(r.is_structural),
            "fields": json.loads(r.fields) if r.fields else [],
            "isBuiltin": bool(r.is_builtin),
            "enabled": bool(r.enabled),
            "createdAt": r.created_at.isoformat() if r.created_at else None,
            "updatedAt": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


@router.post("/reload-emitters")
def reload_emitters(user=Depends(auth.get_current_user)):
    """Runtime reload of emit handlers without server restart."""
    from src.runtime.workflow.emitters import reload_handlers
    reload_handlers()
    return {"success": True}


@router.post("")
def create_command(payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    type_name = payload.get("type", "").strip()
    if not type_name:
        raise HTTPException(status_code=400, detail="type is required")
    existing = db.query(models.WorkflowCommand).filter(models.WorkflowCommand.type == type_name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Command '{type_name}' already exists")

    cmd = models.WorkflowCommand(
        type=type_name,
        label=payload.get("label", type_name),
        category=payload.get("category", "其他"),
        icon=payload.get("icon", "fa-circle"),
        icon_color=payload.get("iconColor", "text-gray-500"),
        bg_color=payload.get("bgColor", "bg-gray-50"),
        is_container=1 if payload.get("isContainer") else 0,
        is_branch=1 if payload.get("isBranch") else 0,
        is_structural=1 if payload.get("isStructural") else 0,
        fields=json.dumps(payload.get("fields", [])),
        is_builtin=0,
        enabled=1 if payload.get("enabled", True) else 0,
    )
    db.add(cmd)
    db.commit()
    db.refresh(cmd)
    return {"id": cmd.id, "type": cmd.type}


@router.put("/{cmd_id}")
def update_command(cmd_id: int, payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    cmd = db.get(models.WorkflowCommand, cmd_id)
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    # Built-in commands: restrict mutable fields
    if cmd.is_builtin:
        allowed = {"label", "category", "icon", "iconColor", "bgColor", "fields", "enabled"}
        payload = {k: v for k, v in payload.items() if k in allowed}

    for field, col in [
        ("label", "label"),
        ("category", "category"),
        ("icon", "icon"),
        ("iconColor", "icon_color"),
        ("bgColor", "bg_color"),
    ]:
        if field in payload:
            setattr(cmd, col, payload[field])

    if "isContainer" in payload:
        cmd.is_container = 1 if payload["isContainer"] else 0
    if "isBranch" in payload:
        cmd.is_branch = 1 if payload["isBranch"] else 0
    if "isStructural" in payload:
        cmd.is_structural = 1 if payload["isStructural"] else 0
    if "fields" in payload:
        cmd.fields = json.dumps(payload["fields"])
    if "enabled" in payload:
        cmd.enabled = 1 if payload["enabled"] else 0

    db.commit()
    db.refresh(cmd)
    return {"success": True}


@router.delete("/{cmd_id}")
def delete_command(cmd_id: int, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    cmd = db.get(models.WorkflowCommand, cmd_id)
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    if cmd.is_builtin:
        raise HTTPException(status_code=403, detail="Cannot delete built-in command")
    db.delete(cmd)
    db.commit()
    return {"success": True}


@router.get("/export/csv")
def export_csv(db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    rows = db.query(models.WorkflowCommand).order_by(
        models.WorkflowCommand.category,
        models.WorkflowCommand.id,
    ).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "分类", "指令类型", "显示名称", "是否容器", "是否分支", "是否结构标记",
        "参数定义(JSON)", "是否内置", "状态", "图标", "图标颜色", "背景颜色",
    ])
    for r in rows:
        writer.writerow([
            r.category,
            r.type,
            r.label,
            "是" if r.is_container else "否",
            "是" if r.is_branch else "否",
            "是" if r.is_structural else "否",
            r.fields or "[]",
            "是" if r.is_builtin else "否",
            "启用" if r.enabled else "禁用",
            r.icon,
            r.icon_color,
            r.bg_color,
        ])

    buf.seek(0)
    filename = f"workflow_commands_{models.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8-sig")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
