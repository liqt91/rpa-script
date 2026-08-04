"""GUI 侧 WebSocket 客户端 — 同步调用浏览器扩展的 DOM 拾取。

使用方式:
    from scripts.capture_gui.ws_client import pick_browser_element
    result = pick_browser_element(x=100, y=200)
    # → {"css": "...", "xpath": "...", "rect": {...}, "tagName": "...", "text": "..."}
"""
import asyncio
import json
import uuid

try:
    import websockets
except ImportError:
    websockets = None

WS_URL = "ws://127.0.0.1:8000"


async def _pick_browser_element_async(x: int, y: int, timeout: float = 5.0) -> dict:
    """异步：通过 WS 请求扩展拾取 DOM 元素。"""
    if websockets is None:
        return {"error": "websockets not installed (pip install websockets)"}

    request_id = str(uuid.uuid4())[:8]
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({
                "action": "browserPickElement",
                "x": x, "y": y,
                "requestId": request_id,
            }))
            response = await asyncio.wait_for(ws.recv(), timeout=timeout)
            data = json.loads(response)
            return data.get("payload", {})
    except asyncio.TimeoutError:
        return {"error": "pick timeout"}
    except Exception as e:
        return {"error": str(e)}


def pick_browser_element(x: int, y: int, timeout: float = 5.0) -> dict:
    """同步：阻塞等待浏览器 DOM 拾取结果。"""
    try:
        return asyncio.run(_pick_browser_element_async(x, y, timeout))
    except RuntimeError:
        # 已有 event loop（如 tkinter 中异步调用）
        import threading
        result = {}

        def _run():
            nonlocal result
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(_pick_browser_element_async(x, y, timeout))
            loop.close()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout + 2)
        return result
