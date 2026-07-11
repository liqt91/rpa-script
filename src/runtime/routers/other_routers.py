"""结果 + 脚本 + 客户端 + AI 路由"""

import json
import logging
import os
import subprocess
import sys
import zipfile
import io
import importlib
import threading
import uuid
from datetime import timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import schemas, auth
from src.repo import runtime_models as models
from src.config import runtime_config as config
from src.repo.browser_utils import (
    get_chrome_path,
    get_edge_path,
    find_extension_dir,
    is_browser_running,
    focus_browser_window,
)
from ..utils import utcnow

logger = logging.getLogger(__name__)


def get_db():
    db = models.SessionLocal()
    try:
        yield db
    finally:
        db.close()
from ..job_registry import get_registry
from ..dify_client import get_dify_client


# 脚本测试结果缓存（内存）
_test_results: dict[str, dict] = {}


def _load_run(job_type: str):
    """服务端侧加载脚本 run 函数。"""
    mod_path = f"service.jobs.{job_type}.main"
    mod = importlib.import_module(mod_path)
    if not hasattr(mod, "run") or not callable(mod.run):
        raise ValueError(f"service.jobs.{job_type}.main is missing a run() callable")
    return mod.run

# ====== Results ======
result_router = APIRouter(prefix="/api/results", tags=["results"])


@result_router.get("")
def list_results(
    task_id: Optional[int] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(auth.get_db),
    _user=Depends(auth.get_current_user),
):
    query = db.query(models.Result, models.Task.job_type).join(
        models.Task, models.Result.task_id == models.Task.id, isouter=True
    )
    if task_id:
        query = query.filter(models.Result.task_id == task_id)

    total = query.count()
    rows = query.order_by(models.Result.extract_time.desc()).offset((page - 1) * per_page).limit(per_page).all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "items": [
            {
                "id": r.Result.id,
                "task_id": r.Result.task_id,
                "url": r.Result.url,
                "total": r.Result.total,
                "client_id": r.Result.client_id,
                "job_type": r.job_type,
                "extract_time": r.Result.extract_time.isoformat() if r.Result.extract_time else None,
            }
            for r in rows
        ],
    }


@result_router.get("/{result_id}")
def get_result(result_id: int, db: Session = Depends(auth.get_db), _user=Depends(auth.get_current_user)):
    result = db.get(models.Result, result_id)
    if not result:
        raise HTTPException(404, "结果不存在")
    return {
        "id": result.id,
        "task_id": result.task_id,
        "url": result.url,
        "total": result.total,
        "data": json.loads(result.data) if isinstance(result.data, str) else result.data,
        "client_id": result.client_id,
        "extract_time": result.extract_time.isoformat() if result.extract_time else None,
    }


@result_router.post("")
def upload_result(req: schemas.ResultUpload, db: Session = Depends(auth.get_db),
                  _user=Depends(auth.get_current_user)):
    # If client_id wasn't supplied, fall back to the task's client_id so audit isn't lost.
    client_id = req.client_id
    task = None
    if req.task_id:
        task = db.get(models.Task, req.task_id)
        if task:
            client_id = client_id or task.client_id

    result = models.Result(
        task_id=req.task_id,
        url=req.url,
        total=req.total,
        data=json.dumps(req.data, ensure_ascii=False),
        extract_time=utcnow(),
        client_id=client_id,
    )
    db.add(result)
    db.flush()

    if task:
        task.status = "done"
        task.updated_at = utcnow()

    db.commit()
    return {"ok": True, "result_id": result.id}


# ====== System / Update ======
system_router = APIRouter(prefix="/api/system", tags=["system"])


def _get_db_folder() -> str:
    """Return the folder containing the SQLite database file."""
    url = config.DATABASE_URL
    if url.startswith("sqlite:///"):
        db_path = url[len("sqlite:///"):]
        return os.path.dirname(os.path.abspath(db_path))
    return os.path.abspath(".")


def _parse_semver(tag: str):
    """Strip leading 'v' and return (major, minor, patch) integers."""
    ver = tag.strip().lstrip("vV")
    parts = ver.split(".")
    try:
        return tuple(int(p) for p in parts[:3])
    except ValueError:
        return (0, 0, 0)


@system_router.get("/update")
def check_update():
    """Query the configured Gitea repo for the latest release and compare versions."""
    base = config.GITEA_BASE_URL.strip().rstrip("/")
    owner = config.GITEA_REPO_OWNER.strip()
    repo = config.GITEA_REPO_NAME.strip()

    try:
        with open(config.VERSION_FILE, encoding="utf-8") as f:
            current = f.read().strip()
    except Exception:
        current = "0.0.0"

    if not base or not owner or not repo:
        return {
            "current": current,
            "latest": current,
            "has_update": False,
            "download_url": "",
            "release_url": "",
            "published_at": "",
            "error": "Gitea 更新源未配置",
        }

    url = f"{base}/api/v1/repos/{owner}/{repo}/releases/latest"
    try:
        resp = httpx.get(url, timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        return {
            "current": current, "latest": current, "has_update": False,
            "download_url": "", "release_url": "", "published_at": "",
            "error": "请求 Gitea 超时",
        }
    except httpx.HTTPError as e:
        return {
            "current": current, "latest": current, "has_update": False,
            "download_url": "", "release_url": "", "published_at": "",
            "error": f"Gitea 请求失败: {e}",
        }
    except Exception as e:
        return {
            "current": current, "latest": current, "has_update": False,
            "download_url": "", "release_url": "", "published_at": "",
            "error": f"解析失败: {e}",
        }

    latest_tag = (data.get("tag_name") or "").strip()
    latest = latest_tag.lstrip("vV")
    release_url = data.get("html_url") or ""
    published_at = data.get("published_at") or ""
    assets = data.get("assets") or []
    download_url = ""
    if assets:
        download_url = assets[0].get("browser_download_url") or ""
    if not download_url:
        # Fall back to zipball / tarball URL patterns if no asset is attached
        download_url = data.get("zipball_url") or data.get("tarball_url") or release_url

    current_ver = _parse_semver(current)
    latest_ver = _parse_semver(latest_tag)
    has_update = latest_ver > current_ver

    return {
        "current": current,
        "latest": latest,
        "has_update": has_update,
        "download_url": download_url,
        "release_url": release_url,
        "published_at": published_at,
    }


@system_router.post("/open-db-folder")
def open_db_folder_api(user=Depends(auth.get_current_user)):
    """Open the local database folder in the system's file manager."""
    folder = _get_db_folder()
    try:
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
    except Exception as e:
        return {"error": f"无法打开文件夹: {e}", "path": folder}
    return {"opened": True, "path": folder}


@system_router.post("/open-extensions-page")
def open_extensions_page(browser: str = "chrome"):
    """启动浏览器并自动加载 RPA Script 扩展（仅当浏览器尚未运行时有效）。"""
    browser = (browser or "chrome").lower()
    exe = get_edge_path() if browser == "edge" else get_chrome_path()

    if not exe:
        return {"success": False, "error": f"未找到 {browser} 浏览器"}

    if is_browser_running(browser):
        if focus_browser_window(browser):
            return {"success": True, "browser": browser, "broughtToFront": True}
        return {
            "success": False,
            "error": f"{browser.title()} 已经在运行。",
        }

    ext_dir = find_extension_dir()
    if not ext_dir:
        return {
            "success": False,
            "error": "未找到 RPA Script 扩展目录，请确认 extension/ 或 dist/desktop/extension/ 存在",
        }

    try:
        subprocess.Popen(
            [
                exe,
                f"--load-extension={ext_dir}",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        return {"success": True, "browser": browser, "extensionDir": ext_dir}
    except Exception as e:
        return {"success": False, "error": f"打开失败: {e}"}


# ====== Scripts ======
script_router = APIRouter(prefix="/api", tags=["scripts"])


@script_router.get("/version")
def get_version():
    try:
        with open(config.VERSION_FILE) as f:
            ver = f.read().strip()
    except FileNotFoundError:
        ver = "0.0.0"
    return {"version": ver, "min_python": "3.10"}


@script_router.get("/scripts")
def list_scripts():
    """列出所有可用脚本类型（含完整元数据）。"""
    registry = get_registry()
    return {
        "scripts": [
            {
                "name": meta.name,
                "version": meta.version,
                "description": meta.description,
                "author": meta.author,
                "main": meta.main,
                "params": {
                    k: {
                        "type": v.type,
                        "description": v.description,
                        "default": v.default,
                        "required": v.required,
                        "constraints": v.constraints.model_dump() if v.constraints else None,
                    }
                    for k, v in meta.params.items()
                },
                "min_client_version": meta.min_client_version,
                "enabled": meta.enabled,
                "requirements_file": meta.requirements_file,
                "requirements": meta.requirements,
            }
            for meta in registry.list_jobs()
        ]
    }


@script_router.get("/scripts/{job_name}")
def get_script_detail(job_name: str):
    """获取单个脚本的详细元数据。"""
    registry = get_registry()
    meta = registry.get_job(job_name)
    if not meta:
        raise HTTPException(404, f"脚本 {job_name} 不存在")
    return {
        "name": meta.name,
        "version": meta.version,
        "description": meta.description,
        "author": meta.author,
        "main": meta.main,
        "params": {
            k: {
                "type": v.type,
                "description": v.description,
                "default": v.default,
                "required": v.required,
                "constraints": v.constraints.model_dump() if v.constraints else None,
            }
            for k, v in meta.params.items()
        },
        "min_client_version": meta.min_client_version,
        "requirements_file": meta.requirements_file,
        "requirements": meta.requirements,
    }


@script_router.get("/scripts/{job_name}/source")
def get_script_source(job_name: str, _user=Depends(auth.get_current_user)):
    """获取脚本源码（job.yaml + main.py）。"""
    job_dir = os.path.join(config.JOBS_DIR, job_name)
    if not os.path.isdir(job_dir):
        raise HTTPException(404, f"脚本 {job_name} 不存在")

    yaml_path = os.path.join(job_dir, "job.yaml")
    py_path = os.path.join(job_dir, "main.py")

    yaml_content = ""
    if os.path.exists(yaml_path):
        with open(yaml_path, encoding="utf-8") as f:
            yaml_content = f.read()

    py_content = ""
    if os.path.exists(py_path):
        with open(py_path, encoding="utf-8") as f:
            py_content = f.read()

    return {"job_yaml": yaml_content, "main_py": py_content}


@script_router.put("/scripts/{job_name}/meta")
def update_script_meta(
    job_name: str,
    req: schemas.ScriptMeta,
    _user=Depends(auth.get_current_user),
):
    """更新脚本元数据（写回 job.yaml）。"""
    job_dir = os.path.join(config.JOBS_DIR, job_name)
    if not os.path.isdir(job_dir):
        raise HTTPException(404, f"脚本 {job_name} 不存在")

    yaml_path = os.path.join(job_dir, "job.yaml")

    # 构建 yaml 内容（requirements 是从文件读取的，不写入 yaml）
    import yaml as pyyaml
    data = req.model_dump(exclude_none=True)
    data.pop("requirements", None)
    with open(yaml_path, "w", encoding="utf-8") as f:
        pyyaml.dump(data, f, allow_unicode=True, sort_keys=False)

    # 触发热加载
    get_registry().check_reload()
    return {"ok": True}


@script_router.post("/scripts/{job_name}/test")
def test_script(
    job_name: str,
    url: str = Form(...),
    params_json: str = Form("{}"),
    _user=Depends(auth.get_current_user),
):
    """后台线程中快速测试脚本。强制限制 scrolls <= 3。"""
    registry = get_registry()
    if not registry.has_job(job_name):
        raise HTTPException(404, f"脚本 {job_name} 不存在")

    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError:
        raise HTTPException(400, "params_json 格式错误")

    # 强制限制 scrolls，避免长时间阻塞
    if "scrolls" in params:
        params["scrolls"] = min(int(params.get("scrolls", 1)), 3)
    else:
        params["scrolls"] = 1

    task_id = f"test-{uuid.uuid4().hex[:8]}"
    _test_results[task_id] = {"status": "running"}

    def _run():
        try:
            run_fn = _load_run(job_name)
            result = run_fn(url, **params)
            _test_results[task_id] = {"status": "done", "result": result}
        except Exception as e:
            _test_results[task_id] = {"status": "failed", "error": str(e)}

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "task_id": task_id}


@script_router.get("/scripts/test/{task_id}")
def get_test_result(task_id: str, _user=Depends(auth.get_current_user)):
    """查询脚本测试结果。"""
    result = _test_results.get(task_id, {"status": "unknown"})
    return {"ok": True, **result}


@script_router.post("/scripts")
def create_script(
    name: str = Form(...),
    main_py: str = Form(...),
    job_yaml: str = Form(...),
    _user=Depends(auth.get_current_user),
):
    """创建新脚本：创建目录并写入 main.py + job.yaml。"""
    import yaml as pyyaml

    # 验证脚本名
    if not name or not name.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(400, "脚本名只能包含字母、数字、下划线和连字符")

    # 验证 job_yaml 格式
    try:
        pyyaml.safe_load(job_yaml) or {}
    except Exception as e:
        raise HTTPException(400, f"job.yaml 格式错误: {e}")

    # 创建目录
    job_dir = os.path.join(config.JOBS_DIR, name)
    if os.path.exists(job_dir):
        raise HTTPException(400, f"脚本 {name} 已存在")
    os.makedirs(job_dir, exist_ok=True)

    # 写入文件
    try:
        with open(os.path.join(job_dir, "main.py"), "w", encoding="utf-8") as f:
            f.write(main_py)
        with open(os.path.join(job_dir, "job.yaml"), "w", encoding="utf-8") as f:
            f.write(job_yaml)
    except Exception as e:
        # 清理
        import shutil
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(500, f"写入文件失败: {e}")

    # 验证脚本可加载
    try:
        _load_run(name)
    except Exception as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(400, f"脚本无法加载: {e}")

    # 触发热加载
    get_registry().check_reload()
    return {"ok": True, "name": name}


@script_router.get("/script/download")
def download_scripts():
    """打包并下载 jobs/ 和 shared/ 目录，以及 client.py / requirements.txt / VERSION
    (供客户端 update 命令一并自我更新)。"""
    buf = io.BytesIO()
    # 项目根目录（REPO_DIR 的父目录，即包含 src/ 的目录）
    project_root = os.path.dirname(config.REPO_DIR)

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. jobs: 从 src/service/jobs/ 打包，zip 内路径为 jobs/
        jobs_src = config.JOBS_DIR
        if os.path.isdir(jobs_src):
            for root, dirs, files in os.walk(jobs_src):
                for fn in files:
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, jobs_src)
                    arcname = os.path.join("jobs", rel)
                    zf.write(full, arcname)

        # 2. shared 模块
        # 2a. 保留在 src/shared/ 的模块（ai_bridge.py, extraction_engine.py）
        # 注意：排除 chrome_utils.py（shim），实际代码在 src/repo/
        shared_src = os.path.join(config.REPO_DIR, "shared")
        if os.path.isdir(shared_src):
            for fn in os.listdir(shared_src):
                full = os.path.join(shared_src, fn)
                if os.path.isfile(full) and fn.endswith(".py") and fn != "chrome_utils.py":
                    arcname = os.path.join("shared", fn)
                    zf.write(full, arcname)

        # 2b. chrome_utils 从 src/config/ 打包到 shared/（客户端 import shared.chrome_utils）
        chrome_utils_src = os.path.join(config.REPO_DIR, "repo", "chrome_utils.py")
        if os.path.isfile(chrome_utils_src):
            zf.write(chrome_utils_src, "shared/chrome_utils.py")

        # 3. 额外文件：从项目根目录查找
        for extra in ["client.py", "client_menu.py", "start.bat", "requirements.txt", "VERSION"]:
            epath = os.path.join(project_root, extra)
            if os.path.exists(epath):
                zf.write(epath, extra)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": "attachment; filename=scripts.zip"})


# ====== Clients ======
client_router = APIRouter(prefix="/api/clients", tags=["clients"])


@client_router.get("")
def list_clients(db: Session = Depends(auth.get_db), _user=Depends(auth.get_current_user)):
    clients = db.query(models.Client).all()
    threshold = utcnow() - timedelta(minutes=2)
    return {
        "clients": [
            {
                "id": c.id,
                "hostname": c.hostname,
                "ip": c.ip,
                "os": c.os,
                "version": c.version,
                "status": c.status,
                "last_heartbeat": c.last_heartbeat.isoformat() if c.last_heartbeat else None,
                "online": bool(c.last_heartbeat and c.last_heartbeat >= threshold),
            }
            for c in clients
        ]
    }


@client_router.post("/register")
def register_client(req: schemas.ClientRegister, db: Session = Depends(auth.get_db),
                    _user=Depends(auth.get_current_user)):
    import uuid
    cid = str(uuid.uuid4())[:12]
    client = models.Client(id=cid, hostname=req.hostname, ip=req.ip, os=req.os,
                           status="online", last_heartbeat=utcnow())
    db.add(client)
    db.commit()
    return {"client_id": cid}


@client_router.post("/heartbeat")
def heartbeat(req: schemas.ClientHeartbeat, db: Session = Depends(auth.get_db),
              _user=Depends(auth.get_current_user)):
    client = db.get(models.Client, req.client_id)
    if client:
        client.status = req.status
        client.version = req.version or client.version
        client.last_heartbeat = utcnow()
    else:
        client = models.Client(id=req.client_id, status="online",
                               last_heartbeat=utcnow())
        db.add(client)
    db.commit()
    # 检查是否有推送任务
    push_tasks = db.query(models.Task).filter(
        models.Task.status == "pending",
        models.Task.client_id == req.client_id
    ).all()
    return {"ok": True, "push_tasks": [{"id": t.id, "job_type": t.job_type, "url": t.url} for t in push_tasks]}


# ====== AI ======
ai_router = APIRouter(prefix="/api/ai", tags=["ai"])

# 各类型必填/禁止字段（透传校验用）
_AI_REQUIRED = {
    "text": {"user"},
    "chat": {"user"},
    "agent": {"user"},
    "chatflow": {"user"},
    "workflow": {"user"},
}
_AI_FORBIDDEN = {
    "text": {"conversation_id"},
    "workflow": {"query", "conversation_id"},
}


@ai_router.get("/capabilities")
def list_capabilities(_user=Depends(auth.get_current_user)):
    """列出所有已配置的 AI 能力。"""
    dify = get_dify_client()
    if not dify.is_configured():
        return {"capabilities": []}

    return {"capabilities": dify.list_capabilities()}


@ai_router.post("/invoke")
def ai_invoke(req: schemas.AIInvokeRequest, _user=Depends(auth.get_current_user)):
    """
    Dify 透传入口。
    服务端只做：参数校验 → 加 appkey → 转发 → 返回原始响应。
    """
    dify = get_dify_client()
    if not dify.is_configured():
        raise HTTPException(400, "AI 功能未配置（缺少 DIFY_BASE_URL）")

    cap_type = req.capability
    if cap_type not in config.DIFY_APPS:
        raise HTTPException(400, f"未知的 AI 能力: {cap_type}")

    app_cfg = config.DIFY_APPS[cap_type]
    if not app_cfg.get("api_key"):
        raise HTTPException(400, f"能力 {cap_type} 未配置 API Key")

    app_type = app_cfg.get("app_type", "chat")
    payload = req.payload

    # 透传校验
    errors = []
    for field in _AI_REQUIRED.get(app_type, set()):
        if field not in payload:
            errors.append(f"缺少必填字段: {field}")
    for field in _AI_FORBIDDEN.get(app_type, set()):
        if field in payload:
            errors.append(f"{app_type} 类型不支持 {field} 字段")
    if app_type in ("text", "chat", "agent", "chatflow"):
        if not payload.get("query") and not payload.get("inputs"):
            errors.append(f"{app_type} 类型需要 query 或 inputs 至少一个非空")
    if app_type == "workflow" and not payload.get("inputs"):
        errors.append("workflow 类型需要 inputs 字段")

    # inputs 字段 schema 校验
    input_schema = app_cfg.get("input_schema", {})
    inputs = payload.get("inputs") or {}
    if input_schema and isinstance(inputs, dict):
        for field_name, schema in input_schema.items():
            if schema.get("required") and field_name not in inputs:
                errors.append(f"inputs 缺少必填字段: {field_name}")
                continue
            if field_name in inputs:
                expected_type = schema.get("type", "string")
                val = inputs[field_name]
                type_checkers = {
                    "string": lambda v: isinstance(v, str),
                    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
                    "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
                    "boolean": lambda v: isinstance(v, bool),
                    "array": lambda v: isinstance(v, list),
                    "object": lambda v: isinstance(v, dict),
                }
                checker = type_checkers.get(expected_type)
                if checker and not checker(val):
                    errors.append(f"inputs.{field_name} 应为 {expected_type}，得到 {type(val).__name__}")

    if errors:
        raise HTTPException(400, "; ".join(errors))

    try:
        result = dify.invoke(app_cfg, payload)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Dify API 调用失败: {e}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"AI 调用失败: {e}")

    return result


# ─── LLM direct configuration (DeepSeek/OpenAI) ─────────────────────


# --- AI Prompt Templates ---
# NOTE: use chr(10) for newlines to avoid backslash-escape corruption

PROMPT_BACKEND = """
你是 RPA 后端开发专家。下面是一份已经写好的 Python handler 代码，import、注册、参数读取、结果上报都已正确。
你只需要把 `# TODO: 业务逻辑` 区域替换成真实可执行的业务代码，然后输出完整文件。

=== 当前代码（你只能修改 # TODO 区域）===

```python
{{scaffold}}
```

=== 项目 API 清单（按需选用，不要编造）===

浏览器操作：
  from src.repo.browser_utils import is_browser_running, launch_browser_with_extension
  # launch_browser_with_extension(browser_type) -> bool  自动加载 RPA 扩展启动浏览器

  from src.runtime.workflow.extension_runner import wait_for_extension_connection, ext_manager
  # client_id = await wait_for_extension_connection(browser_type, ext_manager, timeout=10.0)
  # 连接建立后必须设置: runner.client_id = client_id

工具函数：
  from src.runtime.workflow.handlers.utils import clean_var_ref, convert_value
  # clean_var_ref("{{var}}") -> "var"
  # convert_value(value, type, runner.vars) -> 转换后的值

HTTP 请求：
  import httpx  # 项目已安装
  async with httpx.AsyncClient() as client:
      resp = await client.get(url, headers={...})

=== 架构规则 ===
- backend 指令: execute() 完成全部工作，不涉及浏览器扩展
- extension 指令: execute() 只做前置工作（启动浏览器、建立 WebSocket 连接）。扩展通信和窗口管理由 Runner 负责，不要在 execute() 里调用 _send_and_wait
- 输出变量：如果参数 group="output" 且 type="str-var"，其值代表写入 runner.vars 的键名，执行后写入 runner.vars[键名]

=== 硬性要求 ===
1. 只能改 # TODO 之后、result_summary 之前的代码，其他地方一个字符都不准动
2. 保留 result_summary、runner.completed、runner.results、runner._emit 结果上报代码
3. 不要重写整个文件，不要改 import/register/params/extra 读取
4. result_summary 必须是 dict
5. 不确定的 API 不要编造，说明"需确认"
6. 直接输出完整文件，不要代码块包裹，不要说明文字
"""

PROMPT_EXTENSION_JS = """
你是 Chrome 扩展开发专家。请根据下面的指令定义，编写浏览器扩展的 JS handler。

=== 指令定义 ===
{{definition_json}}

=== Handler 上下文 ===
{{context}}

=== 可用 API ===
注册方式（根据上下文选择其一）：
  registerHandler(name, handler)          — DOM handler（content script 中运行）
  registerBackgroundHandler(name, handler) — background handler（Service Worker 中运行）

DOM handler 可用工具（content.js 中已定义）：
  findElement(elementDef, scope, visibilityMode) → DOM Element | null
    elementDef: args.elements[elementName]
    scope: "local" | "global"
    visibilityMode: "visible" | "any"
  resolveSelector(selectors) → 最佳选择器字符串
  sleep(ms) → Promise

参数读取：
  args.extra — 用户填写的参数 {paramName: value}，参数名与 JSON 定义一致
  args.elements — 元素选择器 {elementName: {selectors: [...]}}

Background handler 可用：
  chrome.windows / chrome.tabs — 扩展后台 API
  agent.workWindowId / agent.workTabId — 当前工作窗口/标签
  agent._injectContentScript(tabId) — 注入 content script
  agent._send(type, payload) — 通过 WebSocket 发送消息到后端

=== 返回值规范 ===
  { ok: true }                           — 成功
  { ok: true, result: {...} }            — 带结果
  { ok: true, vars: {key: val} }         — 写变量
  { ok: false, error: "原因" }            — 失败

=== 要求 ===
1. 根据上下文选择正确的注册方式（registerHandler 或 registerBackgroundHandler）
2. 代码必须真实可执行，正确处理错误情况
3. DOM 操作前检查元素是否存在（findElement 可能返回 null）
4. 直接输出完整 JS 代码，不要 markdown 代码块，不要说明文字
"""

PROMPT_CONTROL = """
你是 RPA 工作流引擎开发专家。请填充控制流 handler 的 # TODO 区域。

=== 当前代码 ===

```python
{{scaffold}}
```

=== 控制流语义 ===
- is_container=True — 容器指令（for/if/try），子节点由 emitter 展开执行
- is_structural=True — 结束标记（endFor/endIf），仅语法闭合
- is_branch=True — 分支路径（else/catch）
- 控制流 handler 的 execute() 只做条件判断/状态更新，不需要 I/O 或浏览器通信

=== Runner 可用 API ===
- runner.vars: dict — 工作流变量空间
- runner.current_loop_index: int | None — 循环索引
- runner.get_parent_vars() -> dict: 父级变量
- instr.get("extra"): dict — 用户填写的参数值

=== 要求 ===
1. 只能改 # TODO 区域，不能改其他地方
2. 控制流逻辑必须正确处理嵌套场景
3. 不写 pass 或占位代码
4. 直接输出完整代码，不要代码块，不要说明文字
"""

REVIEW_PROMPT = """
你是 RPA 代码审查专家。请审查下面的 handler 代码，逐项检查以下规则，返回 JSON 格式的问题清单。

=== JSON 定义 ===
{{definition_json}}

=== Handler 源码 ===
{{source_code}}

=== value_types.json ===
{{value_types_json}}

=== 检查清单 ===
1. @register_handler 的 type/label/category/runtime 是否与 JSON 定义一致
2. params 列表是否与 JSON 定义完全匹配（name、type、default、group）
3. execute() 签名是否正确：@staticmethod async def execute(runner, cmd_type, step_id, instr)
4. 参数是否从 instr.get("extra") 读取（不是 instr.get("paramName")）
5. group="output" 的参数是否正确跳过预执行解析
6. extension 指令的 execute() 是否没有调用 _send_and_wait（由 Runner 负责）
7. backend 指令的 execute() 是否完成全部工作且有结果上报
8. result_summary 是否是 dict
9. 是否编造了不存在的模块或 API
10. 输出变量是否写入了 runner.vars[键名]

=== 返回格式 ===
只返回 JSON 数组，不要任何其他文字：
[
  {
    "level": "error|warning|info",
    "line": 行号或null,
    "check": "检查项名称",
    "message": "具体问题和建议"
  }
]

没有问题时返回空数组 []
"""

NL = chr(10)


def _load_value_types_json() -> str:
    """Load commands/value_types.json as string for review prompts."""
    import os as _os
    root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
    fp = _os.path.join(root, "commands", "value_types.json")
    if _os.path.exists(fp):
        with open(fp, encoding="utf-8") as f:
            return f.read()
    return "{}"


def _extract_json_from_text(text: str) -> list:
    """Try to extract a JSON array from LLM text response."""
    import re
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return []


def _build_params_and_reads(params):
    param_lines = []
    param_read_lines = []
    for p in params:
        pname = p.get("name", "")
        plabel = p.get("label", pname)
        ptype = p.get("type", "str-input")
        pgroup = p.get("group", "主属性")
        parts = [f'        Param("{pname}", "{plabel}", "{ptype}"']
        if p.get("required"):
            parts.append(", required=True")
        if p.get("options"):
            parts.append(f", options={json.dumps(p['options'], ensure_ascii=False)}")
        if "default" in p and p["default"] is not None and p["default"] != "":
            parts.append(f", default={json.dumps(p['default'], ensure_ascii=False)}")
        if pgroup and pgroup != "主属性":
            parts.append(f', group="{pgroup}"')
        if p.get("placeholder"):
            parts.append(f', placeholder="{p["placeholder"]}"')
        if p.get("description"):
            parts.append(f', description="{p["description"]}"')
        parts.append("),")
        param_lines.append("".join(parts))
        default = p.get("default")
        if default is not None and default != "":
            param_read_lines.append(f'        {pname} = extra.get("{pname}", {json.dumps(default, ensure_ascii=False)})')
        elif p.get("required"):
            param_read_lines.append(f'        {pname} = extra["{pname}"]  # 必填')
        else:
            param_read_lines.append(f'        {pname} = extra.get("{pname}")')
    pb = NL.join(param_lines) if param_lines else "        pass"
    pr = NL.join(param_read_lines) if param_read_lines else "        pass"
    return pb, pr


def _build_backend_scaffold(definition):
    type_name = definition.get("type", "example")
    label = definition.get("label", type_name)
    category = definition.get("category", "其他")
    class_name = "".join(p.capitalize() for p in type_name.replace("-", "_").split("_")) + "Handler"
    icon = definition.get("icon", "fa-circle")
    icon_color = definition.get("iconColor", "text-gray-500")
    bg_color = definition.get("bgColor", "bg-gray-50")
    description = definition.get("description", "")
    runtime = definition.get("runtime", "backend")
    params_block, param_reads_block = _build_params_and_reads(definition.get("params", []))
    desc_line = f', description="{description}"' if description else ""
    return f"""# {label}
from src.runtime.workflow.handlers.registry import register_handler, Param
{NL}
@register_handler(
    type="{type_name}",
    label="{label}",
    category="{category}",
    runtime="{runtime}",
    icon="{icon}",
    icon_color="{icon_color}",
    bg_color="{bg_color}"{desc_line}
)
class {class_name}:
    params = [
{params_block}
    ]
{NL}
    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {{}}
{param_reads_block}
{NL}
        # TODO: 业务逻辑 — 在下方编写真实可执行的代码
{NL}
        result_summary = {{"{type_name}": True}}
{NL}
        runner.completed += 1
        runner.results.append({{"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "success", "result": result_summary}})
        await runner._emit({{"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"), "result": result_summary}})
        return True
"""


def _build_extension_js_context(definition):
    handler = definition.get("handler", {})
    source = handler.get("source", "")
    is_background = "background_handlers" in source
    context = "[background handler — Service Worker 中运行]" if is_background else "[DOM handler — content script 中运行]"
    if is_background:
        context += f"{NL}使用 registerBackgroundHandler 注册。可访问 chrome.windows、chrome.tabs、agent 对象。"
    else:
        context += f"{NL}使用 registerHandler 注册。可访问 DOM API、findElement、args.elements。"
    return context, json.dumps(definition, ensure_ascii=False, indent=2)


DEFAULT_LLM_SCENARIOS = [
    {
        "id": "command_backend",
        "name": "backend — Python handler 生成",
        "prompt": PROMPT_BACKEND,
        "enabled": True,
    },
    {
        "id": "command_extension_js",
        "name": "extension — JS handler 生成",
        "prompt": PROMPT_EXTENSION_JS,
        "enabled": True,
    },
    {
        "id": "command_control",
        "name": "control — 控制流 handler 生成",
        "prompt": PROMPT_CONTROL,
        "enabled": True,
    },
    {
        "id": "command_review",
        "name": "handler 代码审查",
        "prompt": REVIEW_PROMPT,
        "enabled": True,
    },
]

_PROVIDER_ENDPOINTS = {
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
}

_PROVIDER_DEFAULT_MODELS = {
    "deepseek": "deepseek-v4-flash",
}


def _get_or_create_llm_config(db: Session):
    row = db.query(models.AILLMConfig).first()
    if not row:
        row = models.AILLMConfig(
            provider="deepseek",
            api_key="",
            scenarios=json.dumps(DEFAULT_LLM_SCENARIOS, ensure_ascii=False),
            enabled=1,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@ai_router.get("/llm-config")
def get_llm_config(db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    """Return the singleton LLM config (provider, apiKey masked, scenarios)."""
    row = _get_or_create_llm_config(db)
    scenarios = json.loads(row.scenarios or "[]")
    return {
        "provider": row.provider,
        "model": row.model or _PROVIDER_DEFAULT_MODELS.get(row.provider, "deepseek-v4-flash"),
        "apiKey": row.api_key or "",
        "enabled": bool(row.enabled),
        "scenarios": scenarios,
    }


@ai_router.put("/llm-config")
def update_llm_config(payload: dict, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    """Update LLM config and scenarios."""
    row = _get_or_create_llm_config(db)
    if "provider" in payload:
        row.provider = payload["provider"]
    if "model" in payload:
        row.model = payload["model"]
    if "apiKey" in payload:
        row.api_key = payload["apiKey"].strip() if payload["apiKey"] else ""
    if "enabled" in payload:
        row.enabled = 1 if payload["enabled"] else 0
    if "scenarios" in payload:
        row.scenarios = json.dumps(payload["scenarios"], ensure_ascii=False)
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return {"success": True}


@ai_router.post("/llm-config/scenarios/{scenario_id}/generate")
def generate_with_scenario(
    scenario_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(auth.get_current_user),
):
    """Run a configured scenario prompt against an LLM.

    payload: {"definition": {...}}  or other context fields.
    """
    row = _get_or_create_llm_config(db)
    if not row.api_key:
        raise HTTPException(400, "LLM API Key 未配置")
    if not row.enabled:
        raise HTTPException(400, "LLM 功能已禁用")

    scenarios = json.loads(row.scenarios or "[]")
    scenario = next((s for s in scenarios if s.get("id") == scenario_id), None)
    if not scenario:
        raise HTTPException(404, f"未知场景: {scenario_id}")
    if not scenario.get("enabled", True):
        raise HTTPException(400, f"场景 {scenario_id} 已禁用")

    prompt_template = scenario.get("prompt", "")
    if not prompt_template:
        raise HTTPException(400, "场景 prompt 为空")

    # Build complete handler scaffold, then inject into prompt
    definition = payload.get("definition", {})
    if scenario_id in ("command_backend", "command_control"):
        scaffold = _build_backend_scaffold(definition)
        prompt = prompt_template.replace("{{scaffold}}", scaffold)
    elif scenario_id == "command_extension_js":
        context, def_json = _build_extension_js_context(definition)
        prompt = prompt_template.replace("{{definition_json}}", def_json).replace("{{context}}", context)
    elif scenario_id == "command_review":
        def_json = json.dumps(definition, ensure_ascii=False, indent=2)
        source = payload.get("source", "")
        vt = _load_value_types_json()
        prompt = prompt_template.replace("{{definition_json}}", def_json).replace("{{source_code}}", source).replace("{{value_types_json}}", vt)
    else:
        scaffold = _build_backend_scaffold(definition)
        prompt = prompt_template.replace("{{scaffold}}", scaffold)

    provider = row.provider or "deepseek"
    endpoint = _PROVIDER_ENDPOINTS.get(provider)
    model = row.model or _PROVIDER_DEFAULT_MODELS.get(provider)
    if not endpoint:
        raise HTTPException(400, f"不支持的 provider: {provider}")

    try:
        resp = httpx.post(
            endpoint,
            headers={"Authorization": f"Bearer {row.api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except httpx.HTTPError as e:
        raise HTTPException(502, f"LLM API 调用失败: {e}")
    except (KeyError, IndexError) as e:
        raise HTTPException(502, f"LLM 响应格式异常: {e}")

    # LLMs often wrap code in markdown fences; strip them.
    code = _extract_code_from_markdown(content)
    logger.info("[ai generate] scenario=%s model=%s raw_len=%d code_len=%d", scenario_id, model, len(content), len(code))
    logger.info("[ai generate] raw response:\n%s", content)
    logger.info("[ai generate] extracted code:\n%s", code)

    # Safety: syntax check if it looks like Python
    if "class " in code or "def " in code:
        try:
            compile(code, f"<ai-generated-{scenario_id}>", "exec")
        except SyntaxError as e:
            logger.error("[ai generate] syntax error: %s\n%s", e, code)
            raise HTTPException(400, f"生成代码语法错误: {e}")

    # LLM response specific to review
    if scenario_id == "command_review":
        try:
            findings = json.loads(content)
            if not isinstance(findings, list):
                findings = []
        except json.JSONDecodeError:
            findings = _extract_json_from_text(content)
        return {"findings": findings, "provider": provider, "model": model}

    return {"code": code, "prompt": prompt, "provider": provider, "model": model, "scenario": scenario_id}


def _extract_code_from_markdown(text: str) -> str:
    """Strip markdown code fences and leading/trailing explanation text."""
    text = text.strip()
    # fenced code block: ```python ... ```
    if text.startswith("```"):
        lines = text.splitlines()
        # drop opening fence
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        # drop closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    # inline single backtick
    if text.startswith("`") and text.endswith("`"):
        return text[1:-1].strip()
    return text


def _app_to_dict(row: models.AIAppConfig) -> dict:
    """将 AIAppConfig ORM 对象转为字典。"""
    return {
        "type": row.type,
        "name": row.name,
        "api_key": row.api_key or "",
        "app_type": row.app_type,
        "input_schema": json.loads(row.input_schema) if row.input_schema else {},
        "enabled": bool(row.enabled),
    }


def _sync_app_to_config(row: models.AIAppConfig) -> None:
    """将数据库中的 AIAppConfig 同步到内存 config.DIFY_APPS。"""
    from ..dify_client import _default_endpoint
    config.DIFY_APPS[row.type] = {
        "name": row.name or row.type,
        "api_key": row.api_key or "",
        "app_type": row.app_type or "chat",
        "endpoint": _default_endpoint(row.app_type or "chat"),
        "input_schema": json.loads(row.input_schema) if row.input_schema else {},
    }


@ai_router.get("/apps")
def list_ai_apps(db: Session = Depends(auth.get_db), _user=Depends(auth.get_current_user)):
    """列出所有 AI 应用配置（api_key 脱敏）。"""
    rows = db.query(models.AIAppConfig).all()
    return {"apps": [_app_to_dict(r) for r in rows]}


@ai_router.post("/apps")
def create_ai_app(req: schemas.AIAppConfigIn, db: Session = Depends(auth.get_db),
                  _user=Depends(auth.get_current_user)):
    """新增 AI 应用配置。"""
    if db.query(models.AIAppConfig).filter(models.AIAppConfig.type == req.type).first():
        raise HTTPException(400, f"AI 应用 {req.type} 已存在")

    row = models.AIAppConfig(
        type=req.type,
        name=req.name,
        api_key=req.api_key,
        app_type=req.app_type,
        input_schema=json.dumps({k: v.model_dump() for k, v in req.input_schema.items()}),
        enabled=1 if req.enabled else 0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    _sync_app_to_config(row)
    return {"ok": True, "app": _app_to_dict(row)}


@ai_router.put("/apps/{cap_type}")
def update_ai_app(cap_type: str, req: schemas.AIAppConfigIn, db: Session = Depends(auth.get_db),
                  _user=Depends(auth.get_current_user)):
    """更新 AI 应用配置。支持修改 type（改名）。"""
    row = db.query(models.AIAppConfig).filter(models.AIAppConfig.type == cap_type).first()
    if not row:
        raise HTTPException(404, f"AI 应用 {cap_type} 不存在")

    if req.type != cap_type:
        existing = db.query(models.AIAppConfig).filter(models.AIAppConfig.type == req.type).first()
        if existing:
            raise HTTPException(400, f"AI 应用 {req.type} 已存在")
        row.type = req.type

    row.name = req.name
    row.api_key = req.api_key
    row.app_type = req.app_type
    row.input_schema = json.dumps({k: v.model_dump() for k, v in req.input_schema.items()})
    row.enabled = 1 if req.enabled else 0
    db.commit()
    db.refresh(row)

    if req.type != cap_type:
        config.DIFY_APPS.pop(cap_type, None)
    _sync_app_to_config(row)
    return {"ok": True, "app": _app_to_dict(row)}


@ai_router.get("/apps/{cap_type}/parameters")
def get_app_parameters(cap_type: str, _user=Depends(auth.get_current_user)):
    """从 Dify 获取应用参数配置，解析为 input_schema。"""
    if cap_type not in config.DIFY_APPS:
        raise HTTPException(404, f"AI 应用 {cap_type} 不存在")

    app_cfg = config.DIFY_APPS[cap_type]
    if not app_cfg.get("api_key"):
        raise HTTPException(400, f"能力 {cap_type} 未配置 API Key")

    dify = get_dify_client()
    try:
        raw = dify.get_parameters(app_cfg)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Dify API 调用失败: {e}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"获取参数失败: {e}")

    # 解析 user_input_form 为 input_schema
    input_schema = {}
    user_input_form = raw.get("user_input_form") or []
    for item in user_input_form:
        # item 格式: {"text-input": {"label": "...", "variable": "...", "required": true, ...}}
        for control_type, cfg in item.items():
            var_name = cfg.get("variable", "")
            if not var_name:
                continue
            # 映射 Dify 控件类型到我们的类型
            type_map = {
                "text-input": "string",
                "paragraph": "string",
                "select": "string",
                "number": "float",
            }
            input_schema[var_name] = {
                "type": type_map.get(control_type, "string"),
                "required": bool(cfg.get("required")),
                "description": cfg.get("label", ""),
            }

    return {
        "ok": True,
        "raw": raw,
        "input_schema": input_schema,
    }


@ai_router.delete("/apps/{cap_type}")
def delete_ai_app(cap_type: str, db: Session = Depends(auth.get_db),
                  _user=Depends(auth.get_current_user)):
    """删除 AI 应用配置。"""
    row = db.query(models.AIAppConfig).filter(models.AIAppConfig.type == cap_type).first()
    if not row:
        raise HTTPException(404, f"AI 应用 {cap_type} 不存在")

    db.delete(row)
    db.commit()
    config.DIFY_APPS.pop(cap_type, None)
    return {"ok": True}


# ====== Health ======
health_router = APIRouter(tags=["health"])


@health_router.get("/health")
def get_health():
    from src.service.health_service import get_health as _get_health
    return _get_health()

admin_api_router = APIRouter(prefix="/api/admin", tags=["admin"])


@admin_api_router.get("/dashboard")
def admin_dashboard_stats(
    db: Session = Depends(auth.get_db),
    _user=Depends(auth.get_current_user),
):
    """管理后台仪表盘统计。"""
    return {
        "workflow_count": db.query(models.Workflow).count(),
        "run_count": db.query(models.Result).count(),
    }
