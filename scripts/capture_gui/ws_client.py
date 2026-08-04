"""GUI 侧 HTTP 客户端 — 通过 FastAPI 调用浏览器扩展的 DOM 拾取。

使用方式:
    from scripts.capture_gui.ws_client import launch_browser_capture
    result = launch_browser_capture(x=100, y=200)
"""
import json, uuid, urllib.request

API_URL = "http://127.0.0.1:8000/api/extension/gui-browser-capture"


def launch_browser_capture(x: int, y: int, timeout: float = 20.0) -> dict:
    """激活浏览器插件的原生捕获模式，阻塞等待用户点击选取。"""
    data = json.dumps({
        "requestId": str(uuid.uuid4())[:8],
        "x": x, "y": y,
        "timeout": timeout,
    }).encode()
    try:
        req = urllib.request.Request(API_URL, data=data,
            headers={"Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=int(timeout) + 5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}
