"""
Project API router — RPA 流程工作区目录读写（目录为唯一真相）。

"一个 RPA 流程 = 一个目录 = 一个 DSH 工作区"：流程数据（workflow.json /
elements.json / data.json）存放在项目目录内，本 router 提供读写访问，
供 workflow-editor 在 ?project=<dir> 模式下编辑并保存到目录。

安全：仅允许读写白名单内的固定文件名（禁止路径穿越）；目录必须是已存在
的 RPA 流程工作区（含 rpa.json）才允许写入，防止对任意目录写入。
"""

import base64
import json
import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, UploadFile

from src.config import runtime_config as config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])

# 允许读写的目录内文件名（白名单，禁止任意路径穿越）
_READABLE_FILES = frozenset({"rpa.json", "workflow.json", "elements.json", "data.json"})
_WRITABLE_FILES = frozenset({"workflow.json", "elements.json", "data.json"})


def _rpa_home() -> Path:
    """RPA 流程根的绝对路径（集中所有流程目录）。"""
    return Path(config.RPA_HOME).expanduser().resolve()


def _flow_marker_meta(root: Path) -> dict:
    try:
        return json.loads((root / "rpa.json").read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def _list_rpa_flows() -> list[dict]:
    """枚举 RPA_HOME 下所有流程目录（含 rpa.json 的子目录）。"""
    home = _rpa_home()
    flows = []
    if not home.is_dir():
        return flows
    for child in sorted(home.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if not (child / "rpa.json").is_file():
            continue
        meta = _flow_marker_meta(child)
        node_count = 0
        has_workflow = (child / "workflow.json").is_file()
        if has_workflow:
            try:
                wf = json.loads((child / "workflow.json").read_text(encoding="utf-8-sig"))
                node_count = len(wf.get("nodes") or [])
            except Exception:
                pass
        flows.append({
            "name": meta.get("name") or child.name,
            "slug": child.name,
            "path": str(child),
            "hasWorkflow": has_workflow,
            "nodeCount": node_count,
        })
    return flows


def _init_flow_dir(root: Path, name: str, description: str = "") -> Path:
    """在一个（新）流程目录内初始化 rpa.json + 空 workflow.json（缺则建，幂等）。

    目录名 = 流程名（OS 层天然唯一；同名即幂等复用，不做复杂去重）。
    """
    root.mkdir(parents=True, exist_ok=True)
    marker = root / "rpa.json"
    if not marker.is_file():
        marker.write_text(json.dumps({
            "name": name,
            "version": 1,
            "description": description,
            "created_at": __import__("datetime").datetime.now().isoformat(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    wf = root / "workflow.json"
    if not wf.is_file():
        wf.write_text(json.dumps({
            "name": name,
            "description": description,
            "url": "",
            "parameters": [],
            "nodes": [],
            "elements": [],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    # 补齐流程目录结构：元素库(空) + images/ + run_logs/（data.json 留给写表格时再建）
    els = root / "elements.json"
    if not els.is_file():
        els.write_text(json.dumps({"version": 1, "elements": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "images").mkdir(exist_ok=True)
    (root / "run_logs").mkdir(exist_ok=True)
    return root


@router.get("/home")
def project_home():
    """返回 RPA 流程根路径（集中根，用户可感知目录）。"""
    home = _rpa_home()
    return {"ok": True, "rpaHome": str(home)}


@router.get("/list")
def project_list():
    """枚举 RPA 流程根下所有流程（集中管理页的数据源）。"""
    flows = _list_rpa_flows()
    return {"ok": True, "count": len(flows), "flows": flows}


@router.post("/create")
def project_create(payload: dict = Body(...)):
    """在 RPA 流程根下创建一个新流程目录（缺则建 rpa.json + 空 workflow.json，幂等）。

    payload: {name(必填), description?}。目录名 = 流程名。
    """
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="缺少流程名 name")
    # 目录名只保留安全字符，避免非法路径/穿越
    slug = "".join(c for c in name if c.isalnum() or c in ("_", "-", " ")).strip() or "flow"
    root = _rpa_home() / slug
    # 允许路径穿越：slug 已过滤，仍做一次安全校验
    resolved = root.resolve()
    if not str(resolved).startswith(str(_rpa_home())):
        raise HTTPException(status_code=400, detail="非法流程名")
    _init_flow_dir(resolved, name, payload.get("description") or "")
    return {"ok": True, "name": name, "path": str(resolved), "rpaHome": str(_rpa_home())}


@router.get("/read")
def project_read(
    path: str = Query(..., description="项目目录绝对路径"),
    file: str = Query("rpa.json", description="要读取的文件名（白名单内）"),
):
    """读取项目目录内白名单文件。目录不存在或文件不存在返回 exists=false。"""
    if file not in _READABLE_FILES:
        raise HTTPException(status_code=400, detail=f"file 必须在白名单内: {sorted(_READABLE_FILES)}")
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        return {"ok": True, "path": str(root), "file": file, "exists": False, "isRpa": False}
    target = root / file
    exists = target.is_file()
    data = None
    if exists:
        try:
            data = json.loads(target.read_text(encoding="utf-8-sig"))
        except Exception as e:
            logger.warning("[projects] 解析 %s 失败: %s", target, e)
            data = None
    return {
        "ok": True,
        "path": str(root),
        "file": file,
        "exists": exists,
        "isRpa": (root / "rpa.json").is_file(),
        "data": data,
    }


@router.put("/write")
def project_write(
    path: str = Query(..., description="项目目录绝对路径"),
    file: str = Query(..., description="要写入的文件名（白名单内）"),
    payload: dict = Body(..., description="要写入的 JSON 对象"),
):
    """写入项目目录内白名单文件（原子写：先写临时文件再 rename）。

    仅允许写入含 rpa.json 的 RPA 流程工作区目录，防止对任意目录写入。
    """
    if file not in _WRITABLE_FILES:
        raise HTTPException(status_code=400, detail=f"file 必须在白名单内: {sorted(_WRITABLE_FILES)}")
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=f"目录不存在: {root}")
    if not (root / "rpa.json").is_file():
        raise HTTPException(status_code=403, detail="该目录不是 RPA 流程工作区（缺少 rpa.json），拒绝写入")
    target = root / file
    try:
        raw = json.dumps(payload, ensure_ascii=False, indent=2)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"payload 不是合法 JSON: {e}")
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        tmp.write_text(raw, encoding="utf-8")
        tmp.replace(target)
    except OSError as e:
        logger.error("[projects] 写入 %s 失败: %s", target, e)
        raise HTTPException(status_code=500, detail=f"写入失败: {e}")
    return {"ok": True, "path": str(root), "file": file, "written": True}


@router.post("/run/extension")
async def run_project_extension(
    path: str = Query(..., description="项目目录绝对路径（RPA 流程工作区）"),
    run_id: str = Query(default=""),
    payload: dict = Body(default={}),
):
    """项目模式运行：从目录 workflow.json/elements.json 加载后走浏览器扩展执行。

    Body: {"initialTableData": {...}, "parameters": {...}, "async": true}
    async 模式立即返回 {runId, status:"started"}，后台执行；
    进度经 GET /api/workflows/{wf_id}/runs/{run_id}/log 查询（wf_id 为目录伪 id）。
    """
    import asyncio
    import time as _t

    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=f"目录不存在: {root}")
    if not (root / "rpa.json").is_file():
        raise HTTPException(status_code=403, detail="该目录不是 RPA 流程工作区（缺少 rpa.json）")
    if not (root / "workflow.json").is_file():
        raise HTTPException(status_code=404, detail=f"目录缺少 workflow.json: {root}")

    # 目录伪 id（与 extension_runner.load_project_workflow 一致，供 log 查询定位）
    import hashlib
    wf_id = int(hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:8], 16)
    initial_table_data = payload.get("initialTableData")
    parameters = payload.get("parameters") or {}
    trigger_type = payload.get("triggerType", "manual")

    _run_id = run_id or f"run_{int(_t.time() * 1000)}"
    log_dir = str(root / "run_logs" / str(wf_id) / _run_id)  # 2.3：日志写回目录
    os.makedirs(log_dir, exist_ok=True)

    async def _bg():
        try:
            from src.runtime.workflow.extension_runner import run_workflow_project as _rwp
            await _rwp(
                str(root),
                run_id=_run_id,
                initial_table_data=initial_table_data,
                initial_parameters=parameters,
                trigger_type=trigger_type,
            )
        except Exception:  # noqa: BLE001 —— 后台任务必须兜底
            logger.exception("[project run] path=%s run=%s failed", root, _run_id)

    asyncio.create_task(_bg())
    return {"runId": _run_id, "status": "started", "workflowId": wf_id, "logDir": log_dir}


@router.get("/run/log")
def get_project_run_log(
    path: str = Query(..., description="项目目录绝对路径"),
    run_id: str = Query(..., description="运行 id"),
):
    """读取项目模式运行的进度日志（目录 run_logs/{wf_id}/{run_id}/run.log）。"""
    import hashlib
    import time as _t

    root = Path(path).expanduser().resolve()
    wf_id = int(hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:8], 16)
    log_dir = root / "run_logs" / str(wf_id) / run_id
    log_path = log_dir / "run.log"
    if not log_path.is_file():
        # 尚未生成（runner 启动中）→ 视为运行中；但启动超 2 分钟仍无日志 → 判失败
        if (root / "run_logs" / str(wf_id) / run_id).exists():
            age = _t.time() - (root / "run_logs" / str(wf_id) / run_id).stat().st_mtime
            if age > 120:
                return {"events": [], "running": False, "error": "run.log 未生成（运行启动超时）",
                        "runId": run_id, "workflowId": wf_id}
        return {"events": [], "running": True, "runId": run_id, "workflowId": wf_id}
    lines = []
    with open(log_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except Exception:
            events.append({"raw": line})
    # 结束判定：done/error/failed 事件，或日志文件超过 2 分钟未更新（runner 异常退出兜底）
    running = True
    for ev in reversed(events):
        if isinstance(ev, dict) and ev.get("type") in ("done", "error", "failed"):
            running = False
            break
    if running:
        age = _t.time() - log_path.stat().st_mtime
        if age > 120:
            running = False
            events.append({"type": "done", "success": False,
                           "error": "运行超时（runner 可能因扩展断开异常退出）"})
    return {"events": events, "running": running, "runId": run_id, "workflowId": wf_id}


# ---------------------------------------------------------------------------
# 项目模式元素库（捕获/截图 → 目录为唯一真相）
# ---------------------------------------------------------------------------

def _load_workflow_data(root: Path) -> dict:
    """读目录 workflow.json（不存在返回空结构）。"""
    wf_path = root / "workflow.json"
    if wf_path.is_file():
        try:
            return json.loads(wf_path.read_text(encoding="utf-8-sig"))
        except Exception as e:
            logger.warning("[projects] 解析 workflow.json 失败: %s", e)
    return {"name": "", "description": "", "url": "", "parameters": [], "nodes": [], "elements": []}


def _save_workflow_data(root: Path, data: dict) -> None:
    """原子写回 workflow.json（含 elements）。"""
    target = root / "workflow.json"
    raw = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(raw, encoding="utf-8")
    tmp.replace(target)


def _atomic_write_json(target: Path, data: dict) -> None:
    """原子写 JSON（先写临时文件再 rename）。"""
    raw = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(raw, encoding="utf-8")
    tmp.replace(target)


def _load_project_elements(root: Path) -> list:
    """读项目元素库：elements.json 优先 + workflow.json 遗留 elements[] 合并。

    elements.json 拆分（capture-unification-plan v2.2）：捕获/保存的统一落点是
    elements.json（workflow.json 只有编辑器整文档写，写进去会被旧内存副本覆盖）。
    遗留 workflow.json 内嵌元素按名合并兜底（elements.json 同名优先），不强制迁移。
    """
    primary = []
    el_path = root / "elements.json"
    if el_path.is_file():
        try:
            data = json.loads(el_path.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict) and isinstance(data.get("elements"), list):
                primary = data["elements"]
            elif isinstance(data, list):
                primary = data
        except Exception as e:
            logger.warning("[projects] 解析 elements.json 失败: %s", e)
    legacy = _load_workflow_data(root).get("elements") or []
    if not legacy:
        return list(primary)
    seen = {e.get("name") for e in primary if isinstance(e, dict) and e.get("name")}
    merged = list(primary)
    for e in legacy:
        if isinstance(e, dict) and e.get("name") and e["name"] not in seen:
            merged.append(e)
    return merged


def _save_project_elements(root: Path, elements: list) -> None:
    """原子写回 elements.json（捕获/保存的唯一落点；不碰 workflow.json）。"""
    _atomic_write_json(root / "elements.json", {"version": 1, "elements": elements})


def _persist_element_screenshot(root: Path, name: str, screenshot) -> str | None:
    """把捕获 payload 的截图（base64 dataURL 或裸 base64）落盘到 目录/images/<safe>.png。

    返回相对路径（形如 "images/x.png"）或 None（无截图/非图像数据）。元素库"含 image"
    的目录化要求：截图随元素存入流程目录，而非只嵌在 workflow.json 的 base64 里。
    """
    if not screenshot or not isinstance(screenshot, str):
        return None
    s = screenshot.strip()
    if s.startswith("data:"):
        # data:image/png;base64,xxxx → 取逗号后 base64
        m = re.match(r"^data:[^;]+;base64,(.*)$", s, re.S)
        if not m:
            return None
        raw = m.group(1)
    else:
        raw = s
    try:
        file_bytes = base64.b64decode(raw, validate=False) if "," not in raw else None
        if file_bytes is None:
            return None
    except Exception:
        return None
    if not file_bytes or not file_bytes.startswith(b"\x89PNG") and not file_bytes.startswith(b"\xff\xd8"):
        return None  # 非 PNG/JPEG 数据，丢弃
    safe = "".join(c for c in name if c.isalnum() or c in ("_", "-")) or "element"
    images_dir = root / "images"
    images_dir.mkdir(exist_ok=True)
    rel = f"images/{safe}.png"
    (root / rel).write_bytes(file_bytes)
    return rel


def _project_root(path: str) -> Path:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=f"目录不存在: {root}")
    if not (root / "rpa.json").is_file():
        raise HTTPException(status_code=403, detail="该目录不是 RPA 流程工作区（缺少 rpa.json）")
    return root


@router.post("/elements/save")
def project_save_element(path: str = Query(...), payload: dict = Body(...)):
    """保存捕获元素到目录元素库 elements.json（web/桌面统一；复用 normalize_element_capture）。

    写入域分离：元素只写 elements.json，不碰 workflow.json（编辑器对它整文档
    读-改-写，元素写进去会被编辑器下次保存覆盖）。
    """
    from src.service.elements_service import normalize_element_capture

    root = _project_root(path)
    elements = _load_project_elements(root)  # elements.json + workflow.json 遗留合并

    # 规范化捕获 payload（纯函数，输出 web/win32/uia 规范化字段）
    norm = normalize_element_capture(payload.get("attributes") or payload)
    name = (payload.get("name") or payload.get("attributes", {}).get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="元素名不能为空")

    # 同名替换
    idx = next((i for i, e in enumerate(elements) if e.get("name") == name), None)
    # 截图落盘到 目录/images/<name>.png（元素库"含 image"的目录化要求）
    img_rel = _persist_element_screenshot(root, name, payload.get("screenshot"))
    attrs = dict(norm.get("attributes", {}) or {})
    if img_rel:
        attrs["imagePath"] = img_rel
    entry = {
        "name": name,
        "element_type": norm.get("element_type", "web"),
        "element_kind": norm.get("element_kind", "plain"),
        "web_selector": norm.get("web_selector", ""),
        "css_candidates": norm.get("css_candidates", []),
        "xpath_candidates": norm.get("xpath_candidates", []),
        "drission_candidates": norm.get("drission_candidates", []),
        "dom_path": norm.get("dom_path", []),
        "attributes": attrs,
        "page_url": norm.get("page_url", ""),
        "image": img_rel,                       # 目录内相对路径（含 image）
        "screenshot": norm.get("screenshot"),   # base64 供编辑器即时预览（可选）
        "anchor_element_name": payload.get("anchorElementName") or payload.get("anchor_element_name"),
        "relative_selector": payload.get("relativeSelector") or payload.get("relative_selector", ""),
    }
    if idx is not None:
        elements[idx] = entry
    else:
        elements.append(entry)
    _save_project_elements(root, elements)
    return {"ok": True, "name": name, "count": len(elements)}


@router.post("/elements/image")
async def project_register_image(
    path: str = Query(...),
    name: str = Form(...),
    similarity: float = Form(0.8),
    scope: str = Form("screen"),
    file: UploadFile = File(...),
):
    """上传截图注册为图像元素：参考图存 目录/images/<name>.png，元素写入 elements.json。"""
    root = _project_root(path)
    name = (name or "").strip()[:128]
    if not name:
        raise HTTPException(status_code=400, detail="元素名不能为空")
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="参考图内容为空")

    # 参考图落盘（同名校验：已有同名非图像元素拒绝）
    elements = _load_project_elements(root)
    existing = next((e for e in elements if e.get("name") == name), None)
    if existing and existing.get("element_type") != "image":
        raise HTTPException(status_code=400, detail=f"元素名 '{name}' 已被非图像元素占用")

    safe_name = "".join(c for c in name if c.isalnum() or c in ("_", "-")) or "image"
    images_dir = root / "images"
    images_dir.mkdir(exist_ok=True)
    rel_path = f"images/{safe_name}.png"
    (root / rel_path).write_bytes(file_bytes)

    entry = {
        "name": name,
        "element_type": "image",
        "element_kind": "plain",
        "web_selector": "",
        "css_candidates": [],
        "xpath_candidates": [],
        "drission_candidates": [],
        "dom_path": [],
        "attributes": {
            "imagePath": rel_path,
            "similarity": similarity,
            "scope": scope,
            "source": "project-upload",
        },
        "page_url": "",
        "screenshot": None,
        "anchor_element_name": None,
        "relative_selector": "",
    }
    if existing:
        elements[elements.index(existing)] = entry
    else:
        elements.append(entry)
    _save_project_elements(root, elements)
    return {"ok": True, "name": name, "imagePath": rel_path, "count": len(elements)}


@router.put("/elements/update")
def project_update_element(path: str = Query(...), payload: dict = Body(...)):
    """按 name 更新元素库某个元素（重命名 / 改选择器 / 改锚点等），写回 elements.json。

    payload: {name: 原元素名, updates: {要合并的字段...}}；重命名传 updates.name=新名。
    不填 name 冲突校验——新名若与既有元素重名则合并到那个元素（同名即去重）。
    """
    root = _project_root(path)
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="缺少元素 name")
    updates = payload.get("updates") or {}
    if not isinstance(updates, dict):
        raise HTTPException(status_code=400, detail="updates 必须是对象")
    elements = _load_project_elements(root)
    idx = next((i for i, e in enumerate(elements) if e.get("name") == name), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"元素不存在: {name}")
    merged = dict(elements[idx])
    merged.update(updates)
    merged["name"] = (updates.get("name") or name).strip()
    # 重命名目标换名后再按名去重：新名已存在则覆盖它，否则原位替换
    new_name = merged["name"]
    dup = next((i for i, e in enumerate(elements)
                if i != idx and e.get("name") == new_name), None)
    if dup is not None:
        elements[dup] = merged
        elements.pop(idx)
    else:
        elements[idx] = merged
    _save_project_elements(root, elements)
    return {"ok": True, "name": new_name, "count": len(elements)}


@router.delete("/elements/delete")
def project_delete_element(path: str = Query(...), name: str = Query(...)):
    """按 name 删除元素库元素，写回 elements.json。"""
    root = _project_root(path)
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="缺少元素 name")
    elements = _load_project_elements(root)
    idx = next((i for i, e in enumerate(elements) if e.get("name") == name), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"元素不存在: {name}")
    elements.pop(idx)
    _save_project_elements(root, elements)
    return {"ok": True, "name": name, "count": len(elements)}
