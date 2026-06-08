"""
管理后台页面路由（TemplateResponse）。
所有页面需要 Cookie 认证（JWT token 存 cookie）。

注意：Starlette 1.0+ TemplateResponse 签名：TemplateResponse(request, name, context)
"""

import json
import os
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import auth
from src.repo import runtime_models as models
from .auth import get_current_user_from_cookie
from src.config.utils import utcnow

router = APIRouter(prefix="/admin", tags=["admin"])
_templates_dir = os.path.join(os.path.dirname(__file__), "admin_templates")
templates = Jinja2Templates(directory=_templates_dir)

# 注册自定义 Jinja2 过滤器
templates.env.filters["fromjson"] = lambda s: json.loads(s) if s else []


# ---------- Auth helpers ----------

def _set_cookie(response: RedirectResponse, token: str) -> None:
    """设置 access_token cookie。"""
    max_age = int(timedelta(days=365*10).total_seconds())
    response.set_cookie(
        key="access_token",
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
    )


def _clear_cookie(response: RedirectResponse) -> None:
    response.delete_cookie(key="access_token")


# ---------- Login / Logout ----------

@router.get("/login", response_class=HTMLResponse)
def admin_login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "login.html", {"error": error})


@router.post("/login")
def admin_login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    db = models.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == username).first()
        if not user or not auth.verify_password(password, user.hashed_password):
            return templates.TemplateResponse(request, "login.html", {"error": "用户名或密码错误"})

        token = auth.create_access_token(user.id, user.username)
        resp = RedirectResponse(url="/workflow-editor/", status_code=302)
        _set_cookie(resp, token)
        return resp
    finally:
        db.close()


@router.get("/logout")
def admin_logout():
    resp = RedirectResponse(url="/admin/login", status_code=302)
    _clear_cookie(resp)
    return resp


# ---------- Dashboard ----------

@router.get("/", response_class=HTMLResponse)
def admin_dashboard(request: Request, user=Depends(get_current_user_from_cookie)):
    db = models.SessionLocal()
    try:
        stats = {
            "tasks_total": db.query(models.Task).count(),
            "tasks_pending": db.query(models.Task).filter(models.Task.status == "pending").count(),
            "tasks_running": db.query(models.Task).filter(models.Task.status == "running").count(),
            "tasks_done": db.query(models.Task).filter(models.Task.status == "done").count(),
            "tasks_failed": db.query(models.Task).filter(models.Task.status == "failed").count(),
            "clients_total": db.query(models.Client).count(),
            "results_total": db.query(models.Result).count(),
        }
        # 在线客户端：心跳在 2 分钟内
        threshold = utcnow() - timedelta(minutes=2)
        stats["clients_online"] = db.query(models.Client).filter(
            models.Client.last_heartbeat >= threshold
        ).count()
    finally:
        db.close()

    return templates.TemplateResponse(request, "dashboard.html", {
        "user": user,
        "active": "dashboard",
        "stats": stats,
    })


# ---------- Tasks ----------

@router.get("/tasks", response_class=HTMLResponse)
def admin_tasks(request: Request, user=Depends(get_current_user_from_cookie)):
    return templates.TemplateResponse(request, "tasks.html", {
        "user": user,
        "active": "tasks",
    })


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def admin_task_detail(request: Request, task_id: int, user=Depends(get_current_user_from_cookie)):
    db = models.SessionLocal()
    try:
        task = db.get(models.Task, task_id)
        result = db.query(models.Result).filter(models.Result.task_id == task_id).first()
    finally:
        db.close()

    return templates.TemplateResponse(request, "task_detail.html", {
        "user": user,
        "active": "tasks",
        "task": task,
        "result": result,
    })


# ---------- Results ----------

@router.get("/results", response_class=HTMLResponse)
def admin_results(request: Request, user=Depends(get_current_user_from_cookie)):
    return templates.TemplateResponse(request, "results.html", {
        "user": user,
        "active": "results",
    })


@router.get("/results/{result_id}", response_class=HTMLResponse)
def admin_result_detail(request: Request, result_id: int, user=Depends(get_current_user_from_cookie)):
    import json as _json
    db = models.SessionLocal()
    try:
        result = db.get(models.Result, result_id)
        data_dict = _json.loads(result.data) if result and result.data else {}
    finally:
        db.close()

    return templates.TemplateResponse(request, "result_detail.html", {
        "user": user,
        "active": "results",
        "result": result,
        "data_dict": data_dict,
    })


# ---------- Clients ----------

@router.get("/clients", response_class=HTMLResponse)
def admin_clients(request: Request, user=Depends(get_current_user_from_cookie)):
    return templates.TemplateResponse(request, "clients.html", {
        "user": user,
        "active": "clients",
    })


# ---------- AI ----------

@router.get("/ai", response_class=HTMLResponse)
def admin_ai(request: Request, user=Depends(get_current_user_from_cookie)):
    return templates.TemplateResponse(request, "ai.html", {
        "user": user,
        "active": "ai",
    })


# ---------- AI Apps ----------

@router.get("/ai-apps", response_class=HTMLResponse)
def admin_ai_apps(request: Request, user=Depends(get_current_user_from_cookie)):
    return templates.TemplateResponse(request, "ai_apps.html", {
        "user": user,
        "active": "ai-apps",
    })


# ---------- Scripts ----------

@router.get("/scripts", response_class=HTMLResponse)
def admin_scripts(request: Request, user=Depends(get_current_user_from_cookie)):
    from .job_registry import get_registry
    scripts = get_registry().list_jobs()
    return templates.TemplateResponse(request, "scripts.html", {
        "user": user,
        "active": "scripts",
        "scripts": scripts,
    })


# ---------- Elements ----------

@router.get("/elements", response_class=HTMLResponse)
def admin_elements(request: Request, user=Depends(get_current_user_from_cookie)):
    db = models.SessionLocal()
    try:
        hosts = (
            db.query(models.CapturedElement.hostname)
            .filter(models.CapturedElement.user_id == user.id)
            .distinct()
            .all()
        )
        host_list = sorted([h[0] for h in hosts if h[0]])
    finally:
        db.close()
    return templates.TemplateResponse(request, "elements.html", {
        "user": user,
        "active": "elements",
        "hosts": host_list,
    })


# ---------- Password Change ----------

@router.get("/password", response_class=HTMLResponse)
def admin_password_page(
    request: Request,
    user=Depends(get_current_user_from_cookie),
    success: str = "",
    error: str = "",
):
    return templates.TemplateResponse(request, "password.html", {
        "user": user,
        "active": "password",
        "success": success,
        "error": error,
    })


@router.post("/password")
def admin_password_post(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user=Depends(get_current_user_from_cookie),
):
    if new_password != confirm_password:
        return templates.TemplateResponse(request, "password.html", {
            "user": user,
            "active": "password",
            "error": "两次输入的新密码不一致",
        })

    if len(new_password) < 6:
        return templates.TemplateResponse(request, "password.html", {
            "user": user,
            "active": "password",
            "error": "新密码长度至少为 6 位",
        })

    if not auth.verify_password(old_password, user.hashed_password):
        return templates.TemplateResponse(request, "password.html", {
            "user": user,
            "active": "password",
            "error": "原密码错误",
        })

    db = models.SessionLocal()
    try:
        db_user = db.get(models.User, user.id)
        db_user.hashed_password = auth.hash_password(new_password)
        db.commit()
    finally:
        db.close()

    resp = RedirectResponse(url="/admin/password?success=1", status_code=302)
    return resp


# ---------- Commands ----------

@router.get("/commands", response_class=HTMLResponse)
def admin_commands(request: Request, user=Depends(get_current_user_from_cookie)):
    return templates.TemplateResponse(request, "commands.html", {
        "user": user,
        "active": "commands",
    })


# ---------- Workflows ----------

@router.get("/workflows", response_class=HTMLResponse)
def admin_workflows(request: Request, user=Depends(get_current_user_from_cookie)):
    return templates.TemplateResponse(request, "workflows.html", {
        "user": user,
        "active": "workflows",
    })


@router.get("/workflows/{wf_id}/edit")
def admin_workflow_editor(request: Request, wf_id: int, user=Depends(get_current_user_from_cookie)):
    """工作流编辑器已迁移到 React SPA，重定向到前端应用。"""
    return RedirectResponse(url=f"/workflow-editor/?wf_id={wf_id}", status_code=302)
