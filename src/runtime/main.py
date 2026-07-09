"""
分布式脚本执行平台 - 服务端
FastAPI 入口
"""

import json
import logging
import os
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session

from .auth import get_current_user_from_cookie, get_db

from src.repo import runtime_models as models
from .routers.auth_router import router as auth_router
from .routers.tasks_router import router as tasks_router
from .routers.workflows_router import router as workflows_router
from .routers.extension_router import router as extension_router
from .routers.commands_router import router as commands_router, cat_router
from .routers.data_tables_router import router as data_tables_router
from .routers.other_routers import (
    result_router, script_router, client_router, ai_router, system_router, admin_api_router,
    health_router,
)
from .routers.public_router import router as public_router
from .admin_router import router as admin_router
from src.config.runtime_config import HOST, PORT
from src.config import runtime_config as config


def _sync_ai_apps_to_db(db):
    """首次启动时：将环境变量中的 DIFY_APPS 默认配置同步到数据库。"""
    from src.config import runtime_config as config
    import json

    existing_types = {row.type for row in db.query(models.AIAppConfig.type).all()}
    for cap_type, app_cfg in config.DIFY_APPS.items():
        if cap_type in existing_types:
            continue
        db.add(models.AIAppConfig(
            type=cap_type,
            name=app_cfg.get("name", cap_type),
            api_key=app_cfg.get("api_key", ""),
            app_type=app_cfg.get("app_type", "chat"),
            input_schema=json.dumps(app_cfg.get("input_schema") or {}),
            enabled=1,
        ))
    db.commit()


def _load_ai_apps_from_db(db):
    """从数据库读取 AI 配置，注入到 config.DIFY_APPS（内存）。"""
    from src.config import runtime_config as config
    from .dify_client import _default_endpoint
    import json

    for row in db.query(models.AIAppConfig).all():
        config.DIFY_APPS[row.type] = {
            "name": row.name or row.type,
            "api_key": row.api_key or "",
            "app_type": row.app_type or "chat",
            "endpoint": _default_endpoint(row.app_type or "chat"),
            "input_schema": json.loads(row.input_schema) if row.input_schema else {},
        }


def _seed_commands_to_db(db):
    """将 handler 系统中的内置指令种子同步到数据库。

    - 首次安装：插入所有内置指令。
    - 后续启动：用代码种子更新已有内置指令（保持自定义指令不变）。
    - 自定义指令（is_builtin=0）永远不会被覆盖。
    """
    from .workflow.handlers.registry import build_command_registry

    registry = build_command_registry()
    existing = {row.type: row for row in db.query(models.WorkflowCommand).all()}
    for type_name, cmd in registry.items():
        row = existing.get(type_name)
        if row is not None and not row.is_builtin:
            continue

        ext = cmd.get("runtimes", {}).get("extension")
        fields = {
            "label": cmd.get("label", type_name),
            "category": cmd.get("category", "其他"),
            "icon": cmd.get("icon", "fa-circle"),
            "icon_color": cmd.get("iconColor", "text-gray-500"),
            "bg_color": cmd.get("bgColor", "bg-gray-50"),
            "is_container": 1 if cmd.get("isContainer") else 0,
            "is_branch": 1 if cmd.get("isBranch") else 0,
            "is_structural": 1 if cmd.get("isStructural") else 0,
            "closes_with": cmd.get("closesWith"),
            "fields": json.dumps(cmd.get("fields", []), ensure_ascii=False),
            "description": cmd.get("description", ""),
            "is_builtin": 1,
            "enabled": 1 if cmd.get("enabled", True) else 0,
            "handler": ext.get("handler") if ext else None,
            "local": 1 if ext and ext.get("local") else 0,
            "category_order": cmd.get("categoryOrder", 0),
            "command_order": cmd.get("commandOrder", 0),
        }
        if row is None:
            db.add(models.WorkflowCommand(type=type_name, **fields))
        else:
            for key, value in fields.items():
                setattr(row, key, value)
    db.commit()


def _load_commands_from_db(db):
    """从数据库加载指令配置到内存，数据库为唯一事实来源。"""
    from .workflow import commands
    commands.load_commands_from_db(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not config.SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY environment variable is required. "
            "Set a strong random secret before starting the server."
        )
    models.init_db()
    from src.repo.migrations import run_migrations
    run_migrations()

    # Auto-register new-system command handlers
    from src.runtime.commands import auto_register
    auto_register()

    from . import auth
    db = models.SessionLocal()
    try:
        # 创建默认 admin 用户
        existing = db.query(models.User).filter(models.User.username == "admin").first()
        if not existing:
            db.add(models.User(username="admin", hashed_password=auth.hash_password("admin123"), is_admin=1))
            db.commit()
        # AI 应用配置：首次同步环境变量到数据库，再从数据库加载到内存
        _sync_ai_apps_to_db(db)
        _load_ai_apps_from_db(db)
        # 工作流指令：首次安装时从代码种子导入数据库，之后运行时以数据库为唯一来源
        _seed_commands_to_db(db)
        _load_commands_from_db(db)
    finally:
        db.close()

    # 打印 runs 相关路由顺序（调试用）
    print("[startup] runs-related routes:")
    for r in app.routes:
        if hasattr(r, 'methods') and 'GET' in r.methods and 'workflows' in str(r.path) and 'runs' in str(r.path):
            print(f"  {r.path} -> {r.name}")

    yield


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="分布式脚本执行平台", version="1.0", lifespan=lifespan)


@app.exception_handler(StarletteHTTPException)
async def not_found_handler(request: Request, exc: StarletteHTTPException):
    """Return a custom 404 page for unmatched non-API paths; preserve headers for other errors."""
    if exc.status_code == 404 and not request.url.path.startswith("/api/"):
        return HTMLResponse(
            content="<html><body><h1>404 - Page Not Found</h1><p>The requested page does not exist.</p></body></html>",
            status_code=404,
        )
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)


app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 注册路由
app.include_router(auth_router)
app.include_router(tasks_router)
app.include_router(workflows_router)
app.include_router(data_tables_router)
app.include_router(extension_router)
app.include_router(commands_router)
app.include_router(cat_router)
app.include_router(result_router)
app.include_router(script_router)
app.include_router(client_router)
app.include_router(ai_router)
app.include_router(system_router)
app.include_router(health_router)
app.include_router(admin_api_router)
app.include_router(admin_router)
app.include_router(public_router)

# Workflow-editor SPA directory
_static_dir = os.path.join(os.path.dirname(__file__), "static", "workflow-editor")

# Serve static assets (js/css) without auth
if os.path.isdir(_static_dir):
    app.mount("/workflow-editor/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="wf-assets")


def _inject_user_to_index(user):
    """Read index.html and inject window.__USER__ before serving."""
    index_path = os.path.join(_static_dir, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    user_data = json.dumps({"id": user.id, "username": user.username}, ensure_ascii=False)
    inject = f'<script>window.__USER__={user_data}</script>'
    return html.replace("<head>", f"<head>\n    {inject}")


@app.get("/workflow-editor/")
@app.get("/workflow-editor/{path:path}")
def workflow_editor_spa(request: Request, path: str = "", db: Session = Depends(get_db)):
    """Serve workflow-editor SPA with cookie auth. Inject user info into HTML."""
    try:
        user = get_current_user_from_cookie(request, db)
    except HTTPException:
        return RedirectResponse(url="/admin/login?next=" + str(request.url))

    # If path looks like a static file, serve it directly
    if path and "." in path:
        file_path = os.path.join(_static_dir, path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        raise HTTPException(status_code=404)

    # Return index.html with injected user data
    html = _inject_user_to_index(user)
    return HTMLResponse(content=html)


@app.get("/")
def root():
    return RedirectResponse(url="/workflow-editor/")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.runtime.main:app", host=HOST, port=PORT, reload=False, timeout_graceful_shutdown=2)
