"""
浏览器扩展通信路由
WebSocket 长连接 + HTTP 命令下发
本地模式，无需认证
"""

import asyncio
from fastapi import APIRouter, WebSocket
from typing import Optional

from ..websocket_manager import ext_manager
from src.service.elements_service import save_captured_element
from src.service.extension_scanner import scan_installed_extensions
from src.repo import runtime_models as models
from src.repo.models import SessionLocal
import json

router = APIRouter(prefix="/api/extension", tags=["extension"])


# ── WebSocket 消息回调 ──

async def _on_capture_element(payload: dict, client_id: str):
    """处理扩展上报的捕获元素，委托 service 层保存"""
    el = await save_captured_element(payload)
    if el:
        print(f"[Extension] 捕获元素已保存: {el.id} {el.name}")
    else:
        print("[Extension] 保存捕获元素失败")


ext_manager.on("captureElement", _on_capture_element)


# ── WebSocket 长连接 ──

@router.websocket("/ws")
async def extension_websocket(websocket: WebSocket):
    """
    浏览器扩展 WebSocket 接入点
    扩展 background.js 连接: ws://host:port/api/extension/ws
    """
    conn = await ext_manager.connect(websocket)
    try:
        await ext_manager.heartbeat_loop(conn)
    except Exception:
        pass


# ── HTTP API ──

@router.post("/command")
async def send_command(
    action: str,
    payload: Optional[dict] = None,
    client_id: Optional[str] = None,
    browser_type: Optional[str] = None,  # chrome / edge
):
    """
    向指定扩展（或所有扩展）下发命令

    示例:
        POST /api/extension/command?action=enterCaptureMode&browser_type=chrome
        {"tabId": 123}
    """
    if not ext_manager.is_any_online:
        return {"success": False, "error": "没有在线的浏览器扩展"}

    if client_id:
        ok = await ext_manager.send_to(client_id, action, payload or {})
        if not ok:
            return {"success": False, "error": f"扩展 {client_id} 不在线"}
    else:
        await ext_manager.broadcast(action, payload or {}, browser_type=browser_type)

    return {
        "success": True,
        "action": action,
        "target": client_id or (browser_type or "all"),
        "online_count": ext_manager.connection_count,
    }


@router.get("/status")
async def get_status():
    """查询扩展连接状态 + 本地安装状态（扫描用户数据目录）"""
    connections = []
    for cid, conn in ext_manager._connections.items():
        connections.append({
            "client_id": cid,
            "browser": conn.browser,
            "connected_at": conn.connected_at,
            "tab_info": conn.tab_info,
            "extension_id": conn.extension_id,
            "install_type": conn.install_type,
        })

    installed = await asyncio.to_thread(scan_installed_extensions)

    # 补充：已连接但文件扫描未发现的扩展（如未打包扩展、自定义用户数据目录）
    scanned_ids = {i.get("extension_id", "") for i in installed}
    for cid, conn in ext_manager._connections.items():
        if conn.extension_id and conn.extension_id not in scanned_ids:
            installed.append({
                "browser": conn.browser,
                "profile": "",
                "extension_id": conn.extension_id,
                "version": "",
                "manifest_version": None,
                "source": f"websocket_{conn.install_type or 'unknown'}",
                "path": "",
            })

    return {
        "online": ext_manager.is_any_online,
        "count": ext_manager.connection_count,
        "browsers": ext_manager.browser_summary,
        "connections": connections,
        "installed": installed,
    }


@router.get("/workflows")
def list_extension_workflows():
    """供扩展拉取所有流程列表（免认证，扩展内部使用）"""
    db = SessionLocal()
    try:
        rows = db.query(models.Workflow).order_by(models.Workflow.created_at.desc()).all()
        return [
            {"id": wf.id, "name": wf.name, "url": wf.url or ""}
            for wf in rows
        ]
    finally:
        db.close()


@router.get("/elements")
def list_extension_elements(workflow_id: int):
    """供扩展拉取指定流程的元素库（免认证，扩展内部使用）"""
    db = SessionLocal()
    try:
        items = (
            db.query(models.WorkflowElement)
            .filter(models.WorkflowElement.workflow_id == workflow_id)
            .order_by(models.WorkflowElement.created_at.desc())
            .all()
        )
        result = []
        for item in items:
            result.append({
                "id": item.id,
                "name": item.name,
                "targetMode": item.target_mode,
                "webSelector": item.web_selector,
                "drissionSelector": item.drission_selector,
                "cssCandidates": json.loads(item.css_candidates) if item.css_candidates else [],
                "xpathCandidates": json.loads(item.xpath_candidates) if item.xpath_candidates else [],
                "drissionCandidates": json.loads(item.drission_candidates) if item.drission_candidates else [],
                "domPath": json.loads(item.dom_path) if item.dom_path else [],
                "attributes": json.loads(item.attributes) if item.attributes else {},
                "screenshot": item.screenshot,
                "pageUrl": item.page_url,
            })
        return result
    finally:
        db.close()
