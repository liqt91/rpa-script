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
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session

from .auth import get_current_user_from_cookie, get_db

from src.repo import runtime_models as models
from .routers.auth_router import router as auth_router
from .routers.tasks_router import router as tasks_router
from .routers.workflows_router import router as workflows_router
from .routers.extension_router import router as extension_router
from .routers.commands_router import router as commands_router
from .routers.data_tables_router import router as data_tables_router
from .routers.other_routers import result_router, script_router, client_router, ai_router
from .admin_router import router as admin_router
from src.config.runtime_config import HOST, PORT


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


def _sync_commands_to_db(db):
    """启动时：将 commands.py 中的内置指令同步到数据库。
    新指令默认停用（enabled=0），已存在的指令不覆盖启停状态。"""
    from .workflow import commands
    import json

    existing = {row.type: row for row in db.query(models.WorkflowCommand).all()}
    for type_name, cmd in commands.COMMAND_REGISTRY.items():
        ext = cmd.get("runtimes", {}).get("extension")
        if type_name in existing:
            row = existing[type_name]
            row.label = cmd.get("label", type_name)
            row.category = cmd.get("category", "其他")
            row.icon = cmd.get("icon", "fa-circle")
            row.icon_color = cmd.get("iconColor", "text-gray-500")
            row.bg_color = cmd.get("bgColor", "bg-gray-50")
            row.is_container = 1 if cmd.get("isContainer") else 0
            row.is_branch = 1 if cmd.get("isBranch") else 0
            row.is_structural = 1 if cmd.get("isStructural") else 0
            row.fields = json.dumps(cmd.get("fields", []))
            row.description = cmd.get("description", "")
            row.is_builtin = 1
            # Sync runtime metadata from registry (allow DB to override later)
            if ext:
                row.handler = ext.get("handler")
                row.local = 1 if ext.get("local") else 0
            # DO NOT overwrite enabled — user controls activation
        else:
            db.add(models.WorkflowCommand(
                type=type_name,
                label=cmd.get("label", type_name),
                category=cmd.get("category", "其他"),
                icon=cmd.get("icon", "fa-circle"),
                icon_color=cmd.get("iconColor", "text-gray-500"),
                bg_color=cmd.get("bgColor", "bg-gray-50"),
                is_container=1 if cmd.get("isContainer") else 0,
                is_branch=1 if cmd.get("isBranch") else 0,
                is_structural=1 if cmd.get("isStructural") else 0,
                fields=json.dumps(cmd.get("fields", [])),
                description=cmd.get("description", ""),
                is_builtin=1,
                enabled=0,  # new commands default disabled
                handler=ext.get("handler") if ext else None,
                local=1 if ext and ext.get("local") else 0,
            ))
    db.commit()


def _load_commands_from_db(db):
    """从数据库读取指令配置，合并到 COMMAND_REGISTRY（保留代码中定义的额外字段如 runtimes）。"""
    from .workflow import commands
    import json

    for row in db.query(models.WorkflowCommand).filter(models.WorkflowCommand.enabled == 1).all():
        existing = commands.COMMAND_REGISTRY.get(row.type, {})
        commands.COMMAND_REGISTRY[row.type] = {
            **existing,
            "label": row.label,
            "category": row.category,
            "icon": row.icon,
            "iconColor": row.icon_color,
            "bgColor": row.bg_color,
            "isContainer": bool(row.is_container),
            "isBranch": bool(row.is_branch),
            "isStructural": bool(row.is_structural),
            "fields": json.loads(row.fields) if row.fields else [],
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.init_db()
    from src.repo.migrations import run_migrations
    run_migrations()

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
        # 工作流指令：首次同步内置指令到数据库，再从数据库加载到内存
        _sync_commands_to_db(db)
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

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 注册路由
app.include_router(auth_router)
app.include_router(tasks_router)
app.include_router(workflows_router)
app.include_router(data_tables_router)
app.include_router(extension_router)
app.include_router(commands_router)
app.include_router(result_router)
app.include_router(script_router)
app.include_router(client_router)
app.include_router(ai_router)
app.include_router(admin_router)

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
