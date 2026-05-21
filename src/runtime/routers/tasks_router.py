"""任务路由"""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, auth
from src.repo import runtime_models as models
from ..utils import utcnow
from ..job_registry import get_registry

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# 注意：更具体的路径（如 /pending）必须放在 /{task_id} 之前，
# 否则 FastAPI 会把 "pending" 当作 task_id 参数匹配到 /{task_id} 路由。


@router.get("")
def list_tasks(
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(auth.get_db),
    _user=Depends(auth.get_current_user),
):
    query = db.query(models.Task)
    if status:
        query = query.filter(models.Task.status == status)
    if job_type:
        query = query.filter(models.Task.job_type == job_type)

    total = query.count()
    items = query.order_by(models.Task.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "items": [
            {
                "id": t.id,
                "job_type": t.job_type,
                "url": t.url,
                "status": t.status,
                "client_id": t.client_id,
                "params": json.loads(t.params) if t.params else {},
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in items
        ],
    }


@router.get("/pending")
def get_pending_tasks(client_id: str, db: Session = Depends(auth.get_db),
                      _user=Depends(auth.get_current_user)):
    tasks = db.query(models.Task).filter(
        models.Task.status == "pending",
        (models.Task.client_id == client_id) | (models.Task.client_id.is_(None))
    ).limit(20).all()

    result = []
    for t in tasks:
        t.status = "running"
        t.client_id = client_id
        t.updated_at = utcnow()
        result.append({
            "id": t.id,
            "job_type": t.job_type,
            "url": t.url,
            "params": json.loads(t.params) if t.params else {}
        })
    db.commit()
    return {"tasks": result}


@router.get("/{task_id}")
def get_task(task_id: int, db: Session = Depends(auth.get_db), _user=Depends(auth.get_current_user)):
    task = db.get(models.Task, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return {
        "id": task.id,
        "job_type": task.job_type,
        "url": task.url,
        "status": task.status,
        "client_id": task.client_id,
        "params": json.loads(task.params) if task.params else {},
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


@router.post("")
def create_tasks(req: schemas.TaskCreate, db: Session = Depends(auth.get_db),
                 _user=Depends(auth.get_current_user)):
    registry = get_registry()

    # 校验 job_type 存在
    if not registry.has_job(req.job_type):
        raise HTTPException(400, f"未知的脚本类型: {req.job_type}")

    # 校验参数
    params = req.params or {}
    ok, errors = registry.validate_params(req.job_type, params)
    if not ok:
        raise HTTPException(400, detail={"errors": errors})

    created = []
    for url in req.urls:
        task = models.Task(
            job_type=req.job_type,
            url=url,
            params=json.dumps(params) if params else None,
            client_id=req.client_id,
        )
        db.add(task)
        created.append(task)
    db.commit()
    return {"ok": True, "count": len(created), "ids": [t.id for t in created]}


@router.put("/{task_id}/status")
def update_task_status(task_id: int, status: str,
                       db: Session = Depends(auth.get_db),
                       _user=Depends(auth.get_current_user)):
    task = db.get(models.Task, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    task.status = status
    task.updated_at = utcnow()
    db.commit()
    return {"ok": True}
