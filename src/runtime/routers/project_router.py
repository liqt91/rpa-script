"""
Project API router — RPA 流程工作区目录读写（目录为唯一真相）。

"一个 RPA 流程 = 一个目录 = 一个 DSH 工作区"：流程数据（workflow.json /
elements.json / data.json）存放在项目目录内，本 router 提供读写访问，
供 workflow-editor 在 ?project=<dir> 模式下编辑并保存到目录。

安全：仅允许读写白名单内的固定文件名（禁止路径穿越）；目录必须是已存在
的 RPA 流程工作区（含 rpa.json）才允许写入，防止对任意目录写入。
"""

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])

# 允许读写的目录内文件名（白名单，禁止任意路径穿越）
_READABLE_FILES = frozenset({"rpa.json", "workflow.json", "elements.json", "data.json"})
_WRITABLE_FILES = frozenset({"workflow.json", "elements.json", "data.json"})


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
