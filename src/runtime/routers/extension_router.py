"""
浏览器扩展通信路由
WebSocket 长连接 + HTTP 命令下发
本地模式，无需认证
"""

import asyncio
import json
from fastapi import APIRouter, WebSocket, Path, Query, HTTPException, Form, File, UploadFile
from fastapi.responses import HTMLResponse
from typing import Optional

from ..websocket_manager import ext_manager
from src.service.elements_service import (
    save_captured_element,
    compute_selector_chain,
    get_element_by_name,
)
from src.service.extension_scanner import scan_installed_extensions
from src.repo import runtime_models as models
from src.repo.models import SessionLocal
from src.dtypes.schemas import ExtensionWorkflowElementOut

def _safe_json_loads(value, default=None):
    """Safely parse a JSON column string; return default on any failure."""
    if not value:
        return default if default is not None else []
    try:
        return json.loads(value)
    except Exception:
        return default if default is not None else []


router = APIRouter(prefix="/api/extension", tags=["extension"])

# GUI 浏览器捕获期间的悬停元素信息（requestId -> info），供悬浮窗轮询
_gui_hover_store: dict = {}
# GUI 浏览器捕获的挂起 future（requestId -> (fut, conn)），供 overlay Esc 兜底取消
_gui_capture_futs: dict = {}
# GUI 浏览器捕获的提示文案（受限页/载入中等），供悬浮窗显示
_gui_capture_notes: dict = {}

# /exec 单指令执行的互斥锁与超时上限：浏览器是单实例资源，串行化防止并发争用
_exec_lock = asyncio.Lock()
MAX_EXEC_TIMEOUT = 120.0


# ── GUI 浏览器捕获（阻塞等待 Alt+Click） ──

@router.post("/electron-capture")
async def electron_capture(request: dict = None):
    """GUI 调用：在 Electron 应用页面激活 Alt+Click 捕获模式，阻塞等待选取。"""
    import uuid
    request_id = (request or {}).get("requestId", str(uuid.uuid4())[:8])
    timeout = (request or {}).get("timeout", 20)
    title_fragment = (request or {}).get("titleFragment", "")

    from src.runtime.workflow.electron_manager import electron_manager
    if not electron_manager.is_running:
        return {"error": "Electron 应用未运行，请先执行「启动 Electron 应用」", "requestId": request_id}
    result = await electron_manager.start_capture(title_fragment, timeout)
    result["requestId"] = request_id
    return result


@router.post("/gui-browser-capture")
async def gui_browser_capture(request: dict = None):
    """GUI 调用：激活插件捕获模式，阻塞等待用户选取元素。"""
    import uuid
    request_id = (request or {}).get("requestId", str(uuid.uuid4())[:8])
    timeout = (request or {}).get("timeout", 20)
    web_only = bool((request or {}).get("webOnly"))
    browser = (request or {}).get("browser") or ""  # chrome/edge/firefox：按连接分发

    # 找活跃扩展连接（指定浏览器时取对应连接，避免 Chrome 委托错发到 Edge 窗口）
    async with ext_manager._lock:
        if not ext_manager._connections:
            return {"error": "没有浏览器扩展连接", "requestId": request_id}
        if browser:
            conn = next((c for c in ext_manager._connections.values() if c.browser == browser), None)
            if conn is None:
                return {"error": f"浏览器扩展未在线: {browser}", "requestId": request_id}
        else:
            conn = next(iter(ext_manager._connections.values()))

    fut = asyncio.get_event_loop().create_future()

    async def _on_result(payload, cid):
        if payload.get("requestId") == request_id and not fut.done():
            fut.set_result(payload.get("result", {}))

    def _on_hover(payload, cid):
        # 悬停元素信息 → 供 GUI 轮询显示到悬浮窗；收到悬停说明已进入可捕获页面，清提示
        if payload.get("requestId") == request_id:
            _gui_capture_notes.pop(request_id, None)
            _gui_hover_store[request_id] = payload.get("info", {})

    def _on_note(payload, cid):
        # 受限页/载入中等启动提示 → 供悬浮窗显示
        if payload.get("requestId") == request_id:
            _gui_capture_notes[request_id] = payload.get("note", "")

    ext_manager.on("browserCaptureComplete", _on_result)
    ext_manager.on("guiHoverInfo", _on_hover)
    ext_manager.on("browserCaptureNote", _on_note)
    _gui_capture_futs[request_id] = (fut, conn)
    try:
        await conn.send({
            "action": "launchBrowserCapture",
            "payload": {"requestId": request_id, "webOnly": web_only},
        })
        result = await asyncio.wait_for(fut, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        # 通知扩展退出浏览器捕获模式，避免页面高亮残留
        try:
            await conn.send({
                "action": "exitBrowserCapture",
                "payload": {"requestId": request_id},
            })
        except Exception:
            pass
        return {"error": "捕获超时", "requestId": request_id}
    finally:
        ext_manager.off("browserCaptureComplete", _on_result)
        ext_manager.off("guiHoverInfo", _on_hover)
        ext_manager.off("browserCaptureNote", _on_note)
        _gui_hover_store.pop(request_id, None)
        _gui_capture_futs.pop(request_id, None)
        _gui_capture_notes.pop(request_id, None)


@router.post("/gui-browser-cancel")
async def gui_browser_cancel(request: dict = None):
    """GUI 调用：立即取消当前捕获（overlay Esc 兜底，不依赖 content 脚本）。

    即使当前标签页是受限页/载入中（content 脚本不可用），也能立刻解除 overlay 阻塞，
    并通过 exitBrowserCapture 通知扩展清理捕获模式，避免框选残留。
    """
    request_id = (request or {}).get("requestId", "")
    entry = _gui_capture_futs.get(request_id)
    if not entry:
        return {"ok": False, "error": "未找到捕获会话", "requestId": request_id}
    fut, conn = entry
    if not fut.done():
        fut.set_result({"error": "已取消", "requestId": request_id})
    # 通知扩展退出浏览器捕获模式（清理 content 捕获模式/高亮）
    try:
        await conn.send({
            "action": "exitBrowserCapture",
            "payload": {"requestId": request_id},
        })
    except Exception:
        pass
    return {"ok": True, "requestId": request_id}


@router.post("/gui-browser-hover")
async def gui_browser_hover(request: dict = None):
    """GUI 轮询：获取当前捕获会话的悬停元素信息与提示文案（悬浮窗实时显示）。"""
    request_id = (request or {}).get("requestId", "")
    return {
        "hover": _gui_hover_store.get(request_id) or {},
        "note": _gui_capture_notes.get(request_id) or "",
    }


# ── 验证选择器 ──

@router.post("/verify-selector")
async def verify_selector(request: dict = None):
    """GUI 调用：验证 CSS/XPath 选择器是否匹配页面元素。

    跨所有已连接的浏览器扩展 fan-out；任一浏览器在可见页面命中即成功。
    """
    import uuid
    selector = (request or {}).get("selector", "")
    if not selector:
        return {"error": "选择器为空"}
    request_id = (request or {}).get("requestId", str(uuid.uuid4())[:8])
    async with ext_manager._lock:
        conns = list(ext_manager._connections.values())
    if not conns:
        return {"error": "没有浏览器扩展连接", "requestId": request_id}

    futures: dict = {}

    async def _on_result(payload, cid):
        if payload.get("requestId") != request_id:
            return
        fut = futures.get(cid)
        if fut and not fut.done():
            fut.set_result(payload.get("result", {}))

    def _conn_browser(cid):
        return next((c.browser for c in conns if c.client_id == cid), "")

    ext_manager.on("verifySelectorResult", _on_result)
    try:
        loop = asyncio.get_event_loop()
        for conn in conns:
            fut = loop.create_future()
            futures[conn.client_id] = fut
            await conn.send({
                "action": "verifySelector",
                "payload": {"requestId": request_id, "selector": selector},
            })
        pending = list(futures.values())
        deadline = loop.time() + 15.0
        scanned = []
        while pending:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            done, pending = await asyncio.wait(pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
            for fut in done:
                cid = next((cid for cid, f in futures.items() if f is fut), None)
                result = fut.result() or {}
                if result.get("found"):
                    return {**result, "browser": _conn_browser(cid)}
                for item in result.get("scanned") or []:
                    item.setdefault("browser", _conn_browser(cid))
                    scanned.append(item)
        if scanned:
            return {"found": False, "count": 0, "visible": 0, "invisible": 0, "scanned": scanned}
        return {"found": False, "count": 0, "visible": 0, "invisible": 0, "error": "验证超时"}
    finally:
        ext_manager.off("verifySelectorResult", _on_result)


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
                "elementType": item.element_type,
                "elementKind": item.element_kind,
                "webSelector": item.web_selector,
                "drissionSelector": item.drission_selector,
                "relativeSelector": item.relative_selector,
                "anchorSelector": item.anchor_selector,
                "anchorElementName": item.anchor_element_name,
                "anchorMode": item.anchor_mode,
                "cssCandidates": _safe_json_loads(item.css_candidates),
                "xpathCandidates": _safe_json_loads(item.xpath_candidates),
                "drissionCandidates": _safe_json_loads(item.drission_candidates),
                "domPath": _safe_json_loads(item.dom_path),
                "attributes": _safe_json_loads(item.attributes, {}),
                # 列表不带 base64 截图；编辑时由 /elements/{name} 详情接口返回
                "screenshot": "",
                "pageUrl": item.page_url,
            })
        return result
    finally:
        db.close()


def _prepare_element(item):
    """Parse JSON text columns on a WorkflowElement ORM object in place."""
    for col in ("css_candidates", "xpath_candidates", "drission_candidates", "dom_path"):
        value = getattr(item, col, None)
        try:
            setattr(item, col, json.loads(value) if value else [])
        except Exception:
            setattr(item, col, [])
    try:
        item.attributes = json.loads(item.attributes) if item.attributes else {}
    except Exception:
        item.attributes = {}
    return item


@router.get("/elements/{name}")
def get_extension_element(
    name: str = Path(..., max_length=255),
    workflow_id: int = Query(..., gt=0),
):
    """供扩展拉取单个元素的完整数据（用于编辑现有元素）。"""
    item = get_element_by_name(workflow_id, name)
    if not item:
        return {"error": "元素不存在"}
    return ExtensionWorkflowElementOut.model_validate(_prepare_element(item))


@router.post("/elements")
async def save_extension_element(payload: dict):
    """供扩展通过 HTTP 保存/更新元素，返回实际保存结果或错误。"""
    try:
        el = await save_captured_element(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not el:
        raise HTTPException(status_code=400, detail="保存元素失败")
    return ExtensionWorkflowElementOut.model_validate(_prepare_element(el))


@router.get("/elements/{name}/chain")
def get_extension_element_chain(name: str, workflow_id: int):
    """供扩展查询某个元素的有效选择器链（支持 child-as-anchor）。"""
    db = SessionLocal()
    try:
        items = (
            db.query(models.WorkflowElement)
            .filter(models.WorkflowElement.workflow_id == workflow_id)
            .all()
        )
        try:
            result = compute_selector_chain(items, name)
        except ValueError as e:
            return {"error": str(e)}
        if not result:
            return {"error": f"元素 '{name}' 不存在"}
        return result
    finally:
        db.close()


# ── 单指令执行（MCP / 外部调用，ADR-0011） ──

@router.get("/commands")
def list_extension_commands():
    """透出可在扩展侧执行的指令目录（供 MCP 自动生成工具 schema）。

    仅含 runtime=extension 的指令（local=True 的后端本地指令与 control 流程
    控制指令无法通过 executeStep 在浏览器内单步执行）。
    """
    from src.runtime.commands import auto_register
    from ..workflow.handlers.registry import build_command_registry

    auto_register()  # 幂等；裸进程/测试环境下注册表可能尚未填充

    out = []
    for cmd_type, cmd in build_command_registry().items():
        rt = cmd.get("runtimes", {}).get("extension", {})
        if not rt.get("handler") or rt.get("local"):
            continue
        out.append({
            "type": rt["handler"],
            "cmd": cmd_type,
            "label": cmd.get("label", cmd_type),
            "category": cmd.get("category", ""),
            "description": cmd.get("description", ""),
            "fields": cmd.get("fields", []),
        })
    return {"commands": out}


@router.post("/exec")
async def exec_extension_command(request: dict = None):
    """单指令执行：透传一个扩展指令并同步等待结果。

    与运行中的工作流互斥（浏览器是单实例资源）；allowDuringRun=true 可强制。
    Body: {"type": "getText", "locator": "...", "selectorFamily": "css",
           "action": null, "extra": {...}, "timeout": 30, "clientId": null}
    """
    import uuid

    req = request or {}
    handler = req.get("type")
    if not handler:
        raise HTTPException(status_code=400, detail="缺少指令类型 type")
    timeout = float(req.get("timeout", 30) or 30)
    timeout = max(1.0, min(timeout, MAX_EXEC_TIMEOUT))
    client_id = req.get("clientId")

    async with _exec_lock:
        async with ext_manager._lock:
            if not ext_manager._connections:
                raise HTTPException(status_code=409, detail="没有浏览器扩展连接")
            if client_id:
                conn = ext_manager._connections.get(client_id)
                if not conn:
                    raise HTTPException(status_code=409, detail=f"扩展连接不存在: {client_id}")
            else:
                conn = next(iter(ext_manager._connections.values()))
            target_client_id = conn.client_id

        from ..workflow.extension_runner import list_active_runners
        runners = await list_active_runners()
        if runners and not req.get("allowDuringRun"):
            raise HTTPException(
                status_code=409,
                detail="有工作流正在运行，为避免争用浏览器已拒绝单指令执行（allowDuringRun=true 可强制）",
            )

        step_id = f"exec_{uuid.uuid4().hex[:12]}"
        instr = {
            "stepId": step_id,
            "nodeId": None,
            "type": handler,
            "cmdType": req.get("cmdType") or handler,
            "cmdLabel": req.get("cmdLabel") or handler,
            "locator": req.get("locator") or "",
            "selectorFamily": req.get("selectorFamily") or "css",
            "action": req.get("action"),
            "extra": req.get("extra") or {},
        }
        fut = await ext_manager.register_step_future(step_id)
        try:
            ok = await ext_manager.send_to(target_client_id, "executeStep", instr)
            if not ok:
                raise HTTPException(status_code=409, detail=f"发送到扩展失败: {target_client_id}")
            resp = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.CancelledError:
            await ext_manager.cancel_step_future(step_id)
            raise
        except asyncio.TimeoutError:
            await ext_manager.cancel_step_future(step_id)
            raise HTTPException(status_code=504, detail=f"指令 {handler} 超时（{timeout}s）")
        except BaseException:
            await ext_manager.cancel_step_future(step_id)
            raise

    if resp.get("status") == "error":
        return {"success": False, "error": resp.get("error"), "clientId": resp.get("client_id")}
    return {"success": True, "result": resp.get("result"), "clientId": resp.get("client_id")}


@router.post("/elements/image")
async def register_image_element_endpoint(
    workflow_id: int = Form(...),
    name: str = Form(...),
    file: UploadFile = File(...),
    similarity: float = Form(0.8),
    scope: str = Form("screen"),
    source: str = Form(""),
):
    """注册 image 元素：上传参考图 → 复制到 data/images/<wf>/ 并建元素库行。

    Body: multipart/form-data（workflow_id, name, file, similarity?, scope?, source?）
    """
    from src.service.elements_service import register_image_element

    file_bytes = await file.read()
    try:
        el = register_image_element(
            workflow_id=workflow_id, name=name, file_bytes=file_bytes,
            similarity=similarity, scope=scope, source=source,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "element": {"id": el.id, "name": el.name,
                                     "elementType": el.element_type,
                                     "attributes": json.loads(el.attributes or "{}")}}


# ── 现场截图（图像元素参考图）：启动系统截图工具 + 轮询剪贴板取新图 ──

def _clipboard_image_fingerprint():
    """读剪贴板图片并返回内容指纹（无图返回 None）。"""
    from PIL import Image, ImageGrab
    try:
        img = ImageGrab.grabclipboard()
    except Exception:
        return None
    if not isinstance(img, Image.Image):
        return None
    small = img.convert("RGB").resize((64, 64))
    import hashlib
    return hashlib.md5(small.tobytes()).hexdigest()


@router.post("/screenshot-tool/start")
def screenshot_tool_start():
    """启动系统截图工具（SnippingTool，Win11 区域截图，框选完自动复制到剪贴板）。

    返回 baseline：启动时剪贴板图片指纹（"" 表示启动时无图）。
    前端随后轮询 /screenshot-tool/poll 取新截图。
    """
    import subprocess
    baseline = _clipboard_image_fingerprint()
    try:
        subprocess.Popen(["SnippingTool.exe"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法启动系统截图工具: {e}")
    return {"ok": True, "baseline": baseline if baseline else ""}


@router.get("/screenshot-tool/poll")
def screenshot_tool_poll(baseline: str = Query("")):
    """轮询剪贴板：出现与基线不同的图片视为新截图，返回 base64 dataUrl。

    :param baseline: start 接口返回的指纹（"" 表示启动时无图）。
    """
    import base64
    import hashlib
    import io
    from PIL import Image, ImageGrab
    try:
        img = ImageGrab.grabclipboard()
    except Exception:
        return {"ready": False}
    if not isinstance(img, Image.Image):
        return {"ready": False}
    small = img.convert("RGB").resize((64, 64))
    fp = hashlib.md5(small.tobytes()).hexdigest()
    if baseline and fp == baseline:
        return {"ready": False}
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return {"ready": True, "dataUrl": data_url, "width": img.width, "height": img.height}


@router.get("/image-upload-page")
def image_upload_page():
    """手动截图上传页：选择截图文件 + 元素名，注册为 image 元素供 findImage/clickImage 使用。"""
    html = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>RPA 图像元素注册</title>
<style>
body{font-family:system-ui;max-width:640px;margin:40px auto;padding:0 20px;color:#222}
h1{font-size:20px} label{display:block;margin:12px 0 4px;font-weight:600}
input[type=text],input[type=number],select{width:100%;padding:8px;border:1px solid #ccc;
  border-radius:6px;box-sizing:border-box}
input[type=file]{padding:8px;border:1px dashed #aaa;border-radius:6px;width:100%;box-sizing:border-box}
button{margin-top:16px;padding:10px 24px;background:#0b7;color:#fff;border:0;
  border-radius:6px;cursor:pointer;font-size:15px}
#result{margin-top:16px;white-space:pre-wrap;background:#f5f5f5;padding:12px;border-radius:6px;font-size:13px}
.hint{color:#777;font-size:12px;margin-top:4px}
</style></head><body>
<h1>📷 RPA 图像元素注册</h1>
<p class="hint">用 Windows 截图（Win+Shift+S）或浏览器元素截图保存 PNG，然后上传并命名。
注册后可在 findImage / clickImage 指令的 imageRef 里直接填元素名。</p>
<form id="f">
  <label>工作流 ID <span class="hint">(rpa_import_workflow 返回值 / /rpa list 可查)</span></label>
  <input type="number" name="workflow_id" required>
  <label>元素名</label>
  <input type="text" name="name" required placeholder="如 筛选按钮">
  <label>相似度阈值</label>
  <input type="number" name="similarity" value="0.8" min="0.5" max="1" step="0.05">
  <label>参考图文件 (PNG)</label>
  <input type="file" name="file" accept="image/png,image/jpeg" required>
  <label>来源说明 <span class="hint">可选，如「小红书筛选按钮截图」</span></label>
  <input type="text" name="source" placeholder="可选">
  <button type="submit">注册</button>
</form>
<div id="result"></div>
<script>
document.getElementById('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const r = await fetch('/api/extension/elements/image', { method: 'POST', body: fd });
  const j = await r.json();
  document.getElementById('result').textContent = JSON.stringify(j, null, 2);
});
</script>
</body></html>"""
    return HTMLResponse(content=html)
