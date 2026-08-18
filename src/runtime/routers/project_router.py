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
