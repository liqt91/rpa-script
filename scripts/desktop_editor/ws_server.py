"""极简 WebSocket 服务器 — 仅托管浏览器扩展连接，不依赖 FastAPI。

替代方案：extension_router.extension_websocket (FastAPI)
"""

import asyncio
import json
import logging
import time

logger = logging.getLogger(__name__)


def _make_conn(ws, client_id: str):
    """创建一个模拟 ExtensionConnection 的对象，满足 ext_manager 的接口。"""

    class _ExtConn:
        def __init__(self):
            self.ws = ws
            self.client_id = client_id
            self.browser = ""
            self.extension_id = ""
            self.install_type = ""
            self.connected_at = time.time()
            self.tab_info = None

        async def send(self, message: dict):
            await ws.send(json.dumps(message, ensure_ascii=False))

    return _ExtConn()


async def _handle_connection(ws):
    """处理单个 WebSocket 连接，生命周期 = 浏览器扩展连接。"""
    from src.runtime.websocket_manager import ext_manager

    client_id = f"ext_{id(ws)}"
    conn = _make_conn(ws, client_id)

    # 注册
    async with ext_manager._lock:
        ext_manager._connections[client_id] = conn
    logger.info(f"[WsServer] 扩展已连接: {client_id}")

    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            action = msg.get("action", "")
            payload = msg.get("payload", {})

            # 注册消息：更新浏览器类型
            if action == "register":
                conn.browser = payload.get("browser", "")
                conn.extension_id = payload.get("extensionId", "")
                logger.info(f"[WsServer] {client_id} 注册: browser={conn.browser}")

            # 分发给 ext_manager（含 stepResult/stepError 唤醒 Future）
            await ext_manager.dispatch(action, payload, client_id)

    except Exception:
        pass
    finally:
        async with ext_manager._lock:
            ext_manager._connections.pop(client_id, None)
        logger.info(f"[WsServer] 扩展已断开: {client_id}")


async def run_ws_server(host: str = "127.0.0.1", port: int = 8000):
    """启动纯 WebSocket 服务（阻塞，在 daemon 线程中运行）。"""
    import websockets
    from websockets.asyncio.server import serve

    async with serve(_handle_connection, host, port):
        logger.info(f"[WsServer] 启动: ws://{host}:{port}")
        await asyncio.Future()  # 永远运行
