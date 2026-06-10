"""结果 + 脚本 + 客户端 + AI 路由"""

import json
import os
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
from ..utils import utcnow
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
        return {"current": current, "latest": current, "has_update": False, "download_url": "", "release_url": "", "published_at": "", "error": "请求 Gitea 超时"}
    except httpx.HTTPError as e:
        return {"current": current, "latest": current, "has_update": False, "download_url": "", "release_url": "", "published_at": "", "error": f"Gitea 请求失败: {e}"}
    except Exception as e:
        return {"current": current, "latest": current, "has_update": False, "download_url": "", "release_url": "", "published_at": "", "error": f"解析失败: {e}"}

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
