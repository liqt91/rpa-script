"""
分布式脚本执行平台 - 服务端
FastAPI 入口
"""

import json
import logging
import os
import re
import secrets
import socket
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session

from .auth import get_db, get_current_user_from_cookie

from src.repo import runtime_models as models
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
from .routers.project_router import router as project_router
from src.config import runtime_config as config
from src.config import runtime_config


def _pick_free_port(lo: int = 8100, hi: int = 8199) -> int:
    """在 [lo, hi] 内找一个空闲端口（避免与其他服务冲突）；全占用则返回 0 由 OS 分配。"""
    for port in range(lo, hi + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return 0


# 监听地址：默认仅回环（本机工具，防局域网暴露）；RPA_HOST 可显式覆盖（如 0.0.0.0 远程访问）。
RPA_HOST = os.environ.get("RPA_HOST", "127.0.0.1")
# 端口：RPA_PORT 显式固定优先；否则在 8100-8199 随机选空闲（兼容旧 .env 的 PORT=8000 不生效）。
_env_port = os.environ.get("RPA_PORT", "")
PORT = int(_env_port) if _env_port.strip() else _pick_free_port()


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




def _read_handler_from_json(type_name):
    from .workflow.command_sync import read_handler_from_json as _rhj
    return _rhj(type_name)


def _seed_categories_from_json():
    """从 types/categories.json 同步分类到数据库。slug 冲突时更新。"""
    import json as _json3
    from pathlib import Path as _Path3
    fp = _Path3(__file__).resolve().parent / "commands" / "types" / "categories.json"
    if not fp.exists():
        return
    with open(fp, encoding="utf-8") as f:
        data = _json3.load(f)
    db = models.SessionLocal()
    try:
        for cat in data.get("categories", []):
            slug = cat["slug"]
            row = db.query(models.CommandCategory).filter_by(slug=slug).first()
            if row:
                row.name = cat["name"]
                row.icon = cat.get("icon", "fa-folder")
                row.sort_order = cat.get("sortOrder", 0)
            else:
                db.add(models.CommandCategory(
                    slug=slug,
                    name=cat["name"],
                    icon=cat.get("icon", "fa-folder"),
                    sort_order=cat.get("sortOrder", 0),
                ))
        db.commit()
    finally:
        db.close()


def _seed_commands_to_db(db):
    """将 handler 系统中的内置指令种子同步到数据库（实现移至 command_sync 供热重载共用）。"""
    from .workflow.command_sync import seed_commands_to_db as _seed
    _seed(db)


def _load_commands_from_db(db):
    """从数据库加载指令配置到内存，数据库为唯一事实来源。"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # SECRET_KEY 兜底：无配置（缺 .env）时生成随机值并持久化到 data/secret.key，
    # 避免 JWT 用空/默认密钥签名（.env 模板占位 your-secret-key-change-me 同样视为弱）。
    if not config.SECRET_KEY or config.SECRET_KEY in ("your-secret-key-change-me", "change-me"):
        secret_file = os.path.join(config.DATA_DIR, "secret.key")
        try:
            with open(secret_file, "r", encoding="utf-8") as f:
                generated = f.read().strip()
            if not generated:
                raise OSError
        except OSError:
            generated = secrets.token_hex(32)
            try:
                with open(secret_file, "w", encoding="utf-8") as f:
                    f.write(generated)
            except OSError:
                pass
        config.SECRET_KEY = generated
        runtime_config.SECRET_KEY = generated
        os.environ["SECRET_KEY"] = generated
    models.init_db()
    from src.repo.migrations import run_migrations
    run_migrations()

    # Auto-register new-system command handlers
    from src.runtime.commands import auto_register
    auto_register()

    # Re-populate LOCAL_HANDLERS now that new handlers are registered
    from src.runtime.workflow.extension_runner import _populate_local_handlers
    _populate_local_handlers()

    # Seed categories from JSON
    _seed_categories_from_json()

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


# CORS 收窄：仅允许本机页面（127.0.0.1 / localhost / [::1]，任意端口，含 DSH web），
# 拒绝外部站点的浏览器跨源读取（防恶意网页打本机 API）。
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def host_guard(request: Request, call_next):
    """Host 头白名单校验：仅接受本机主机名（含任意端口），防 DNS rebinding。"""
    host = request.headers.get("host", "").lower()
    if not re.match(r"^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$", host):
        return JSONResponse({"detail": "forbidden host"}, status_code=400)
    return await call_next(request)

# 注册路由
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
app.include_router(public_router)
app.include_router(project_router)

# Workflow-editor SPA directory
_static_dir = os.path.join(os.path.dirname(__file__), "static", "workflow-editor")

# RPA 控制台（本地工具页，免认证）：流程列表 + 图像元素注册 + 运行控制
@app.get("/tools/rpa-console")
def rpa_console_page():
    from fastapi.responses import FileResponse
    p = os.path.join(os.path.dirname(__file__), "static", "rpa_console.html")
    if os.path.isfile(p):
        return FileResponse(p)
    return HTMLResponse("控制台页面缺失", status_code=404)

# Serve static assets (js/css) without auth
if os.path.isdir(_static_dir):
    app.mount("/workflow-editor/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="wf-assets")

# 图像元素参考图静态访问（元素库缩略图 / 图像详情预览；免认证，本机素材）
_images_root = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "images",
)
if os.path.isdir(_images_root):
    app.mount("/api/images", StaticFiles(directory=_images_root), name="rpa-images")


def _inject_user_to_index(user):
    """Read index.html and inject window.__USER__ before serving.

    本机工具免登录：user 为 None 时注入 null（前端有占位兜底），
    已登录（有效 cookie）时注入真实用户信息。
    """
    index_path = os.path.join(_static_dir, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    if user is None:
        user_data = "null"
    else:
        user_data = json.dumps({"id": user.id, "username": user.username}, ensure_ascii=False)
    inject = f'<script>window.__USER__={user_data}</script>'
    return html.replace("<head>", f"<head>\n    {inject}")


@app.get("/workflow-editor/")
@app.get("/workflow-editor/{path:path}")
def workflow_editor_spa(request: Request, path: str = "", db: Session = Depends(get_db)):
    """Serve workflow-editor SPA（本机工具：免登录，不重定向登录页）。

    有效 cookie 则注入用户信息（右上角显示用户名）；无 cookie 直接进入
    （前端以占位显示）。静态文件与 SPA 入口逻辑不变。
    """
    user = None
    try:
        user = get_current_user_from_cookie(request, db)
    except HTTPException:
        user = None

    # If path looks like a static file, serve it directly
    if path and "." in path:
        file_path = os.path.join(_static_dir, path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        raise HTTPException(status_code=404)

    # Return index.html with injected user data
    html = _inject_user_to_index(user)
    resp = HTMLResponse(content=html)
    # SPA entry must never be cached: it references hashed, immutable assets,
    # so always revalidate it or users keep loading a stale build.
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.get("/")
def root():
    return RedirectResponse(url="/workflow-editor/")


if __name__ == "__main__":
    import uvicorn
    # 端口落盘：扩展/DSH 插件等客户端通过 data/backend.port 发现实际端口
    try:
        port_file = os.path.join(config.DATA_DIR, "backend.port")
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(port_file, "w", encoding="utf-8") as f:
            f.write(str(PORT))
    except OSError:
        pass
    print(f"[startup] binding {RPA_HOST}:{PORT} (backend.port written to {config.DATA_DIR})")
    uvicorn.run("src.runtime.main:app", host=RPA_HOST, port=PORT, reload=False, timeout_graceful_shutdown=2)
