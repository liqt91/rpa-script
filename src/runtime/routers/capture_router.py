"""
元素捕获 Web 前端 — 独立的纯 HTML/JS 捕获界面。
通过 WS 长连接与浏览器扩展通信，不受 HTTP 超时限制。
"""
import json
import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(tags=["capture"])

# 元素库路径
import sys
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

STORE_PATH = os.path.join(_project_root, "data", "captured_elements.json")


def _read_store():
    if not os.path.exists(STORE_PATH):
        return {"version": 1, "elements": []}
    with open(STORE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_store(data):
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@router.get("/capture", response_class=HTMLResponse)
async def capture_page():
    """返回捕获页面 HTML。"""
    page_path = os.path.join(_project_root, "static", "capture.html")
    if not os.path.exists(page_path):
        return HTMLResponse("<h1>capture.html not found</h1>", status_code=404)
    with open(page_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@router.get("/api/elements/list")
async def elements_list():
    return _read_store()


@router.post("/api/elements/update")
async def elements_update(request: dict):
    store = _read_store()
    idx = request.get("index", -1)
    if 0 <= idx < len(store["elements"]):
        for key in ("name", "css_selector", "xpath", "element_type"):
            if key in request:
                store["elements"][idx][key] = request[key]
        _write_store(store)
        return {"ok": True}
    return JSONResponse({"error": "index out of range"}, status_code=400)


@router.post("/api/elements/capture-result")
async def elements_capture_result(request: dict):
    """扩展捕获完成后，通过 WS 推送到此后端，再写入元素库。"""
    store = _read_store()
    store["elements"].append(request.get("element", {}))
    _write_store(store)
    return {"ok": True, "count": len(store["elements"])}
