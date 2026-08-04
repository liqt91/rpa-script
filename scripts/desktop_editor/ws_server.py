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
    """处理单个 WebSocket 连接。"""
    from src.runtime.websocket_manager import ext_manager

    client_id = f"ext_{id(ws)}"
    conn = _make_conn(ws, client_id)
    is_extension = False

    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            action = msg.get("action", "")
            payload = msg.get("payload", {})

            if action == "register":
                is_extension = True
                async with ext_manager._lock:
                    ext_manager._connections[client_id] = conn
                conn.browser = payload.get("browser", "")
                conn.extension_id = payload.get("extensionId", "")
                logger.info(f"[WsServer] {client_id} 注册: browser={conn.browser}")
                continue

            if action == "launchBrowserCapture":
                # GUI → 要求扩展进入原生捕获模式，等待 Alt+Click 选取
                payload = msg.get("payload", {})
                result = await _launch_browser_capture(ext_manager, payload, timeout=20.0)
                await ws.send(json.dumps({
                    "action": "launchBrowserCaptureResult",
                    "payload": result,
                }, ensure_ascii=False))
                continue

            if action == "browserPickElement":
                # GUI → 转发给扩展 (保留兼容)
                x, y = msg.get("x", 0), msg.get("y", 0)
                request_id = msg.get("requestId", str(time.time()))
                result = await _pick_via_extension(ext_manager, x, y, request_id, timeout=5.0)
                await ws.send(json.dumps({
                    "action": "browserPickResult",
                    "requestId": request_id,
                    "payload": result,
                }, ensure_ascii=False))
                continue

            if is_extension:
                await ext_manager.dispatch(action, payload, client_id)

    except Exception:
        pass
    finally:
        if is_extension:
            async with ext_manager._lock:
                ext_manager._connections.pop(client_id, None)
        logger.info(f"[WsServer] 断开: {client_id}")


async def _pick_via_extension(ext_manager, x: int, y: int, request_id: str, timeout: float = 5.0) -> dict:
    """通过扩展拾取浏览器 DOM 元素。"""
    # 找一个活跃的扩展连接
    async with ext_manager._lock:
        if not ext_manager._connections:
            return {"error": "没有浏览器扩展连接"}
        ext_conn = next(iter(ext_manager._connections.values()))

    # 注册 Future
    fut = asyncio.get_event_loop().create_future()

    async def _on_result(payload, cid):
        if payload.get("requestId") == request_id and not fut.done():
            fut.set_result(payload.get("result", {}))

    ext_manager.on("browserPickResult", _on_result)

    try:
        await ext_conn.send({
            "action": "browserPickElement",
            "payload": {"x": x, "y": y, "requestId": request_id},
        })
        result = await asyncio.wait_for(fut, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        return {"error": "拾取超时"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        ext_manager.off("browserPickResult", _on_result)


async def _launch_browser_capture(ext_manager, payload: dict, timeout: float = 20.0) -> dict:
    """将扩展切到原生捕获模式，等待用户 Alt+Click 选取完成。"""
    async with ext_manager._lock:
        if not ext_manager._connections:
            return {"error": "没有浏览器扩展连接"}
        ext_conn = next(iter(ext_manager._connections.values()))

    request_id = payload.get("requestId", str(time.time()))
    fut = asyncio.get_event_loop().create_future()

    async def _on_result(payload, cid):
        if payload.get("requestId") == request_id and not fut.done():
            fut.set_result(payload.get("result", {}))

    ext_manager.on("browserCaptureComplete", _on_result)
    try:
        await ext_conn.send({
            "action": "launchBrowserCapture",
            "payload": {"requestId": request_id},
        })
        result = await asyncio.wait_for(fut, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        return {"error": "捕获超时 (20s)"}
    finally:
        ext_manager.off("browserCaptureComplete", _on_result)


async def run_ws_server(host: str = "127.0.0.1", port: int = 8000):
    """启动纯 WebSocket 服务（阻塞，在 daemon 线程中运行）。"""
    import websockets
    from websockets.asyncio.server import serve

    async with serve(_handle_connection, host, port):
        logger.info(f"[WsServer] 启动: ws://{host}:{port}")
        await asyncio.Future()  # 永远运行
