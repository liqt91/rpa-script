"""GUI 侧 HTTP 客户端 — 通过 FastAPI 调用浏览器扩展的 DOM 拾取。

使用方式:
    from scripts.capture_gui.ws_client import launch_browser_capture
    result = launch_browser_capture(x=100, y=200)
"""
import json
import urllib.request
import uuid

API_URL = "http://127.0.0.1:8000/api/extension/gui-browser-capture"
HOVER_URL = "http://127.0.0.1:8000/api/extension/gui-browser-hover"
CANCEL_URL = "http://127.0.0.1:8000/api/extension/gui-browser-cancel"


def launch_browser_capture(x: int, y: int, timeout: float = 20.0, request_id: str | None = None,
                           web_only: bool = False) -> dict:
    """激活浏览器插件的原生捕获模式，阻塞等待用户点击选取。

    web_only=True → 网页专用模式：content 禁用 Tab/移出页面的切回桌面，仅 Alt+点击 与 Esc。
    """
    data = json.dumps({
        "requestId": request_id or str(uuid.uuid4())[:8],
        "x": x, "y": y,
        "timeout": timeout,
        "webOnly": web_only,
    }).encode()
    try:
        req = urllib.request.Request(API_URL, data=data,
            headers={"Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=int(timeout) + 5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def poll_capture_hover(request_id: str) -> dict:
    """轮询当前捕获会话的悬停元素信息与提示（悬浮窗实时显示）。返回 {hover, note}。"""
    if not request_id:
        return {}
    data = json.dumps({"requestId": request_id}).encode()
    try:
        req = urllib.request.Request(HOVER_URL, data=data,
            headers={"Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode()) or {}
    except Exception:
        return {}


def cancel_browser_capture(request_id: str):
    """立即取消当前浏览器捕获（overlay Esc 兜底，不依赖 content 脚本）。"""
    if not request_id:
        return
    data = json.dumps({"requestId": request_id}).encode()
    try:
        req = urllib.request.Request(CANCEL_URL, data=data,
            headers={"Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return {"error": "cancel failed"}
