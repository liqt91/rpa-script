"""
Project API router — RPA 流程工作区目录读写（最小原型）。

"一个 RPA 流程 = 一个目录 = 一个 DSH 工作区"：流程数据（workflow.json /
elements.json / data.json）存放在项目目录内，本 router 提供最小只读访问，
供 workflow-editor 在 ?project=<dir> 模式下展示项目信息与流程文件状态。

安全：仅允许读取路径白名单（文件名必须是白名单内的固定名），不暴露任意文件。
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])

# 允许读取的目录内文件名（白名单，禁止任意路径穿越）
_ALLOWED_FILES = frozenset({"rpa.json", "workflow.json", "elements.json", "data.json"})


@router.get("/read")
def project_read(
    path: str = Query(..., description="项目目录绝对路径"),
    file: str = Query("rpa.json", description="要读取的文件名（白名单内）"),
):
    """读取项目目录内白名单文件。目录不存在或文件不存在返回 exists=false。"""
    if file not in _ALLOWED_FILES:
        raise HTTPException(status_code=400, detail=f"file 必须在白名单内: {sorted(_ALLOWED_FILES)}")
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
