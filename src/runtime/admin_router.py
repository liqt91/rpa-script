"""
管理后台页面路由。
仅保留登录页/登录表单提交/登出；其余全部重定向到 React SPA。
"""

import os
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import auth
from src.repo import runtime_models as models
from .auth import get_current_user_from_cookie

router = APIRouter(prefix="/admin", tags=["admin"])
_templates_dir = os.path.join(os.path.dirname(__file__), "admin_templates")
templates = Jinja2Templates(directory=_templates_dir)


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
def admin_login_logout():
    resp = RedirectResponse(url="/admin/login", status_code=302)
    _clear_cookie(resp)
    return resp


# ---------- Catch-all redirect ----------

@router.get("/{path:path}", response_class=HTMLResponse)
def admin_catch_all(
    request: Request,
    path: str,
    user=Depends(get_current_user_from_cookie),
):
    """所有非 login/logout 的旧后台 URL 统一重定向到 React SPA。"""
    return RedirectResponse(url="/workflow-editor/#/admin/dashboard", status_code=302)
