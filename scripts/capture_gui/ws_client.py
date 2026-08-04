"""GUI 侧 WebSocket 客户端 — 同步调用浏览器扩展的 DOM 拾取。

使用方式:
    from scripts.capture_gui.ws_client import launch_browser_capture
    result = launch_browser_capture(x=100, y=200)
"""
import asyncio, json, uuid

try:
    import websockets
except ImportError:
    websockets = None

WS_URL = "ws://127.0.0.1:8000"


async def _ws_call_async(action: str, payload: dict, timeout: float = 10.0) -> dict:
    if websockets is None:
        return {"error": "websockets not installed"}
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"action": action, "payload": payload}))
            response = await asyncio.wait_for(ws.recv(), timeout=timeout)
            data = json.loads(response)
            return data.get("payload", {})
    except asyncio.TimeoutError:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": str(e)}


def _ws_call(action: str, payload: dict, timeout: float = 10.0) -> dict:
    try:
        return asyncio.run(_ws_call_async(action, payload, timeout))
    except RuntimeError:
        import threading
        result = {}
        def _run():
            nonlocal result
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(_ws_call_async(action, payload, timeout))
            loop.close()
        t = threading.Thread(target=_run, daemon=True)
        t.start(); t.join(timeout + 2)
        return result


def launch_browser_capture(x: int, y: int, timeout: float = 15.0) -> dict:
    """激活浏览器插件的原生捕获模式，阻塞等待用户 Alt+Click 选取。"""
    return _ws_call("launchBrowserCapture", {"x": x, "y": y, "requestId": str(uuid.uuid4())[:8]}, timeout=timeout)
