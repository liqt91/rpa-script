"""桌面元素捕获覆盖层 — SetWindowRgn 挖空窗口方案。

鼠标移动时实时高亮目标控件（WS_EX_TOPMOST + SetWindowRgn 挖空中间，
只留 3px 蓝色边框 — 永远在最上面，不会被任何窗口覆盖）。
左键点击捕获，右键/Esc 取消。同时收集 Win32 + UIA 信息。
"""
import ctypes
import ctypes.wintypes as wintypes
import os
import threading
import time
import uuid
from dataclasses import dataclass, field

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_kernel32 = ctypes.windll.kernel32
_ole32 = ctypes.windll.ole32


def _com_init():
    """当前线程初始化 COM（STA）。不依赖 pywin32，任何环境可用。"""
    _ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED


def _com_uninit():
    _ole32.CoUninitialize()

# ── Constants ──
VK_ESCAPE = 0x1B; VK_RBUTTON = 0x02; VK_LBUTTON = 0x01; VK_MENU = 0x12
VK_1 = 0x31; VK_2 = 0x32
SM_CXSCREEN = 0; SM_CYSCREEN = 1
BORDER_COLOR = 0x3b82f6  # blue
BORDER_T = 3

# ── Win32 API ──
_GetCursorPos = _user32.GetCursorPos
_GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
_GetAsyncKeyState = _user32.GetAsyncKeyState
_GetAsyncKeyState.argtypes = [ctypes.c_int]; _GetAsyncKeyState.restype = ctypes.c_short
_WindowFromPoint = _user32.WindowFromPoint
_WindowFromPoint.argtypes = [wintypes.POINT]; _WindowFromPoint.restype = wintypes.HWND
_GetWindowTextW = _user32.GetWindowTextW
_GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_GetWindowTextLengthW = _user32.GetWindowTextLengthW
_GetWindowTextLengthW.argtypes = [wintypes.HWND]; _GetWindowTextLengthW.restype = ctypes.c_int
_GetClassNameW = _user32.GetClassNameW
_GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_GetWindowRect = _user32.GetWindowRect
_GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]; _GetWindowRect.restype = wintypes.BOOL
_GetParent = _user32.GetParent
_GetParent.argtypes = [wintypes.HWND]; _GetParent.restype = wintypes.HWND
_GetSystemMetrics = _user32.GetSystemMetrics
_GetSystemMetrics.argtypes = [ctypes.c_int]; _GetSystemMetrics.restype = ctypes.c_int

# DWM (for real visible rect, excluding shadows)
_dwmapi = ctypes.windll.dwmapi
_DwmGetWindowAttribute = _dwmapi.DwmGetWindowAttribute
_DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
_DwmGetWindowAttribute.restype = ctypes.c_long
_FillRect = _user32.FillRect
_FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
_ReleaseDC  = _user32.ReleaseDC
_ReleaseDC.argtypes  = [wintypes.HWND, wintypes.HDC]
_SetBkMode  = _gdi32.SetBkMode
_SetBkMode.argtypes  = [wintypes.HDC, ctypes.c_int]
_SetTextColor = _gdi32.SetTextColor
_SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
_DrawTextW  = _user32.DrawTextW
_DrawTextW.argtypes  = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.c_void_p, wintypes.UINT]
_SelectObject = _gdi32.SelectObject
_SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_DeleteObject = _gdi32.DeleteObject
_DeleteObject.argtypes = [wintypes.HGDIOBJ]
_CreateFontW = _gdi32.CreateFontW
_CreateFontW.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                          wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                          wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                          wintypes.LPCWSTR]; _CreateFontW.restype = wintypes.HANDLE
_CreateSolidBrush = _gdi32.CreateSolidBrush
_CreateSolidBrush.argtypes = [wintypes.COLORREF]; _CreateSolidBrush.restype = wintypes.HBRUSH
_SetClassLongPtrW = _user32.SetClassLongPtrW
_SetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]; _SetClassLongPtrW.restype = wintypes.DWORD
_GetClassLongPtrW = _user32.GetClassLongPtrW
_GetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]; _GetClassLongPtrW.restype = ctypes.c_void_p
_GetDC = _user32.GetDC
_GetDC.argtypes = [wintypes.HWND]; _GetDC.restype = wintypes.HDC
DWMWA_EXTENDED_FRAME_BOUNDS = 9

# ── 捕获期间隐藏/恢复 RPA 编辑器窗口 ──
_GetForegroundWindow = _user32.GetForegroundWindow
_GetForegroundWindow.restype = wintypes.HWND
_ShowWindow = _user32.ShowWindow
_ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]; _ShowWindow.restype = wintypes.BOOL
_SetForegroundWindow = _user32.SetForegroundWindow
_SetForegroundWindow.argtypes = [wintypes.HWND]; _SetForegroundWindow.restype = wintypes.BOOL
_BringWindowToTop = _user32.BringWindowToTop
_BringWindowToTop.argtypes = [wintypes.HWND]; _BringWindowToTop.restype = wintypes.BOOL
_GetWindowThreadProcessId = _user32.GetWindowThreadProcessId
_GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_GetWindowThreadProcessId.restype = wintypes.DWORD
_keybd_event = _user32.keybd_event
_keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_ulonglong]
_keybd_event.restype = None
_SetWindowPos = _user32.SetWindowPos
_SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                          ctypes.c_int, ctypes.c_int, wintypes.UINT]
_SetWindowPos.restype = wintypes.BOOL
_EnumWindows = _user32.EnumWindows
_EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
_IsWindowVisible = _user32.IsWindowVisible
_IsWindowVisible.argtypes = [wintypes.HWND]; _IsWindowVisible.restype = wintypes.BOOL
_IsIconic = _user32.IsIconic
_IsIconic.argtypes = [wintypes.HWND]; _IsIconic.restype = wintypes.BOOL
_OpenProcess = _kernel32.OpenProcess
_OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_OpenProcess.restype = wintypes.HANDLE
_QueryFullProcessImageNameW = _kernel32.QueryFullProcessImageNameW
_QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
_QueryFullProcessImageNameW.restype = wintypes.BOOL

# 悬浮框：灰色背景 + 白色边框
_FrameRect = _user32.FrameRect
_FrameRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
_FrameRect.restype = ctypes.c_int


def _bgr(rgb: int) -> int:
    return ((rgb & 0xFF) << 16) | (rgb & 0xFF00) | ((rgb >> 16) & 0xFF)


@dataclass
class ElementInfo:
    name: str = ""
    element_type: str = "win32"
    class_name: str = ""
    title: str = ""
    rect: dict = field(default_factory=dict)
    hwnd: int = 0
    control_type: str = ""
    automation_id: str = ""
    uia_path: list = field(default_factory=list)
    win32_path: list = field(default_factory=list)
    css_selector: str = ""
    xpath: str = ""
    tag_name: str = ""
    candidates: list = field(default_factory=list)  # 全部选择器候选
    screenshot: str = ""  # base64
    dom_path: list = field(default_factory=list)  # DOM层级路径
    elem_attrs: dict = field(default_factory=dict)  # 元素属性
    list_info: dict = field(default_factory=dict)  # 列表检测信息
    page_url: str = ""  # 页面 URL（web 元素）
    region: dict = field(default_factory=dict)  # 元素屏幕区域（图像兜底）
    threshold: float = 0.8  # 图像匹配阈值
    match_method: str = "template"  # 图像匹配方法
    screen_size: dict = field(default_factory=dict)  # 捕获时屏幕分辨率


def _get_window_text(hwnd) -> str:
    length = _GetWindowTextLengthW(hwnd)
    if length == 0: return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _get_class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _GetClassNameW(hwnd, buf, 256)
    return buf.value


# ── 捕获期间隐藏/恢复 RPA 编辑器窗口（仅 Electron，浏览器不隐藏）──

def _get_process_exe(hwnd) -> str:
    """返回指定窗口所属进程的可执行文件路径；失败返回空串。"""
    pid = wintypes.DWORD()
    _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    handle = _OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if _QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        _kernel32.CloseHandle(handle)


def _is_rpa_editor(hwnd) -> bool:
    """是否 RPA 编辑器（Electron）窗口。浏览器（chrome/msedge）窗口不视为编辑器。"""
    exe = os.path.basename(_get_process_exe(hwnd) or "").lower()
    if not exe:
        return False
    if "rpa" in exe:
        return True                       # 打包版 RPA-Script.exe
    if "electron" in exe:                 # dev 模式 Electron
        t = _get_window_text(hwnd).lower()
        return "workflow-editor" in t or "rpa" in t
    return False                          # chrome/msedge 浏览器等 → 不隐藏


def _hide_editor_window():
    """隐藏当前前台窗口若其为 RPA 编辑器（Electron）。返回被隐藏的 HWND，否则 None。"""
    if os.name != "nt":
        return None
    hwnd = _GetForegroundWindow()
    if hwnd and _is_rpa_editor(hwnd):
        _ShowWindow(hwnd, 0)              # SW_HIDE 完全隐藏
        return hwnd
    return None


def _restore_editor_window(hwnd):
    """恢复并可靠前置被隐藏的 RPA 编辑器窗口（解除 Windows 前台锁）。"""
    if not hwnd:
        return
    _ShowWindow(hwnd, 5)                  # SW_SHOW
    # 模拟一次 Alt 键，让本进程获得"最近输入"资格 → 解除前台锁，SetForegroundWindow 才生效
    _keybd_event(VK_MENU, 0, 0, 0)        # Alt down
    _keybd_event(VK_MENU, 0, 0x0002, 0)   # Alt up (KEYEVENTF_KEYUP)
    if not _SetForegroundWindow(hwnd):
        # 兜底：TOPMOST 提层级再恢复，确保浮到浏览器之上
        _SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0002 | 0x0001)   # HWND_TOPMOST
        _SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0002 | 0x0001)   # HWND_NOTOPMOST
    _BringWindowToTop(hwnd)


def _get_window_rect(hwnd) -> dict:
    # Try DWM first (excludes shadow/invisible chrome)
    dwm = wintypes.RECT()
    if _DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                               ctypes.byref(dwm), ctypes.sizeof(dwm)) == 0:
        if dwm.right - dwm.left > 0 and dwm.bottom - dwm.top > 0:
            return {"left": dwm.left, "top": dwm.top, "right": dwm.right, "bottom": dwm.bottom,
                    "width": dwm.right - dwm.left, "height": dwm.bottom - dwm.top}
    # Fallback
    r = wintypes.RECT()
    _GetWindowRect(hwnd, ctypes.byref(r))
    return {"left": r.left, "top": r.top, "right": r.right, "bottom": r.bottom,
            "width": r.right - r.left, "height": r.bottom - r.top}


def _get_ancestor_path(hwnd) -> list:
    path = []; cur = hwnd; visited = set()
    while cur and cur not in visited:
        visited.add(cur)
        path.insert(0, {"hwnd": cur, "class_name": _get_class_name(cur),
                         "title": _get_window_text(cur), "rect": _get_window_rect(cur)})
        parent = _GetParent(cur)
        if not parent: break
        cur = parent
    return path


def _is_browser_window(cls: str) -> bool:
    return any(c in cls for c in (
        "Chrome_WidgetWin_1", "MozillaWindowClass", "ApplicationFrameWindow",
    ))


def _is_browser_in_chain(path: list) -> bool:
    return any(_is_browser_window(p.get("class_name", "")) for p in path)


# 已知 UIA provider 有缺陷、查询会卡死/黑屏的进程名，本次会话内跳过 UIA
_uia_skip_exes: set = set()


def _is_skip_uia(hwnd) -> bool:
    """是否需要跳过 UIA（微信族：查询其 UIA provider 会导致应用卡死+黑屏）。"""
    exe = _get_process_exe(hwnd).lower()
    if not exe:
        return False
    name = os.path.basename(exe).lower()
    if name in _uia_skip_exes:
        return True
    if "wechat" in name or "weixin" in name or "wework" in name:
        _uia_skip_exes.add(name)
        return True
    return False


_UIA_DEBUG = os.path.join(os.environ.get("TEMP", "."), "rpa_uia_debug.log")
_uia_last_sig = ""


def _uia_debug_log(item, chain):
    """记录 hover 时 UIA 返回的元素链（诊断用，元素变化才写）。"""
    global _uia_last_sig
    r = item.get("rect") or {}
    sig = (item.get("control_type", "") + "|" + (item.get("name", "") or "")[:30] + "|"
           + str(r.get("width", 0)) + "x" + str(r.get("height", 0)))
    if sig == _uia_last_sig:
        return
    _uia_last_sig = sig
    try:
        with open(_UIA_DEBUG, "a", encoding="utf-8") as f:
            f.write("---\n")
            for c in reversed(chain):  # 根 → 叶
                cr = c.get("rect") or {}
                f.write(f"{c.get('control_type', '')} | {(c.get('name', '') or '')[:40]} | "
                        f"{c.get('class_name', '')} | {cr.get('width', 0)}x{cr.get('height', 0)}\n")
            f.write(f">> BEST {item.get('control_type', '')} | {(item.get('name', '') or '')[:40]} | "
                    f"{r.get('width', 0)}x{r.get('height', 0)}\n")
    except Exception:
        pass


def _uia_chain_at(x, y, uia):
    """光标下 UIA 元素链（叶在前、根在后）：[leaf, ..., root]。"""
    try:
        ctrl = uia.ControlFromPoint(x, y)
    except Exception:
        return []
    if not ctrl:
        return []
    chain = []
    cur = ctrl
    seen = set()
    for _ in range(10):
        if not cur or id(cur) in seen:
            break
        seen.add(id(cur))
        try:
            br = cur.BoundingRectangle
        except Exception:
            br = None
        rect = {}
        if br:
            rect = {"left": br.left, "top": br.top, "right": br.right, "bottom": br.bottom,
                    "width": br.width(), "height": br.height()}
        chain.append({
            "name": cur.Name or "", "class_name": cur.ClassName or "",
            "control_type": cur.ControlTypeName or "", "automation_id": cur.AutomationId or "",
            "rect": rect,
        })
        try:
            p = cur.GetParentControl()
            if not p or p.ControlTypeName == "DesktopControl":
                break
            cur = p
        except Exception:
            break
    return chain


def _uia_score(item) -> float:
    """元素打分：越适合捕获（细粒度、有文字、常见控件）分越高。"""
    r = item.get("rect") or {}
    w = r.get("width", 0); h = r.get("height", 0)
    if w <= 0 or h <= 0:
        return -100
    s = 0
    if 6 <= w <= 600 and 6 <= h <= 300:
        s += 40          # 细粒度控件
    elif w <= 2000 and h <= 200:
        s += 20          # 宽条（tab strip 等又宽又矮）
    else:
        s -= 30          # 过大 → 整窗
    if (item.get("name") or "").strip():
        s += 25
    ct = item.get("control_type") or ""
    if ct in ("TabItemControl", "ButtonControl", "ListItemControl", "MenuItemControl",
              "TextControl", "EditControl", "CheckBoxControl", "ComboBoxControl",
              "HyperlinkControl", "RadioButtonControl", "TreeItemControl"):
        s += 20
    elif ct in ("WindowControl", "PaneControl", "DocumentControl", "GroupControl"):
        s -= 15
    s += min(10, (600 - min(int(w), 600)) // 60)  # 更细粒度微偏好
    return s


def _best_uia_item(chain):
    if not chain:
        return None, -1
    idx = max(range(len(chain)), key=lambda i: _uia_score(chain[i]))
    return chain[idx], idx


def _uia_node_dict(node) -> dict:
    """把 UIA 控件转为可序列化字典（name/class/type/automation_id/rect）。"""
    try:
        br = node.BoundingRectangle
    except Exception:
        br = None
    rect = {}
    if br:
        rect = {"left": br.left, "top": br.top, "right": br.right, "bottom": br.bottom,
                "width": br.width(), "height": br.height()}
    return {
        "name": node.Name or "", "class_name": node.ClassName or "",
        "control_type": node.ControlTypeName or "", "automation_id": node.AutomationId or "",
        "rect": rect,
    }


def _deepest_uia_element(x, y, uia, max_depth=8, max_nodes=400):
    """从窗口根有界 BFS，找「rect 含光标 (x,y) 的最小/最有价值元素」。

    混合架构应用（XAML island：hit-test 返回 0x0 占位）的兜底方案：
      - 根 = ElementFromHandle(WindowFromPoint)，不 hit-test
      - 不按节点 rect 剪枝（父节点可能 0x0/无效，但子树里有有效元素）
      - 只在「含光标的候选」上读 Name/类型（控制成本）
    返回 (best_dict, 根→best 的路径 list)。
    """
    try:
        root = uia.ControlFromPoint2(x, y)
    except Exception:
        return None, None
    if not root:
        return None, None
    candidates = []  # (node, dict)
    parents = {}
    stack = [root]
    seen = set()
    nodes = 0
    while stack and nodes < max_nodes:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        nodes += 1
        try:
            br = node.BoundingRectangle
        except Exception:
            br = None
        if br and br.width() > 0 and br.height() > 0 \
                and (br.left <= x <= br.right and br.top <= y <= br.bottom):
            candidates.append((node, _uia_node_dict(node)))
        try:
            kids = node.GetChildren()
        except Exception:
            kids = []
        for k in kids:
            if id(k) not in seen:
                parents[id(k)] = node
            stack.append(k)
    if not candidates:
        return None, None
    best_node, best_dict = max(candidates, key=lambda c: _uia_score(c[1]))
    rev = []
    cur = best_node
    guard = 0
    while cur is not None and guard < 20:
        rev.append(cur)
        cur = parents.get(id(cur))
        guard += 1
    rev.reverse()
    path = [_uia_node_dict(c) for c in rev]
    return best_dict, path


_UIA_QUERY_TIMEOUT = 3.0  # 秒


def _blacklist_process(hwnd):
    """把指定窗口所属进程加入 UIA 运行时黑名单（通用兜底，不硬编码应用名）。"""
    exe = _get_process_exe(hwnd).lower()
    if exe:
        _uia_skip_exes.add(os.path.basename(exe).lower())


def _try_uia_capture(x, y) -> dict | None:
    """UIA 捕获（祖先链 + 打分选优；hit-test 失效时深搜兜底）。
    在工作线程执行并限时，超时 → 返回 None 并把该进程记入运行时黑名单（防卡死）。"""
    result = {"done": False, "value": None}

    def _run():
        try:
            import uiautomation as uia
            with uia.UIAutomationInitializerInThread():  # 工作线程必须各自初始化 COM
                chain = _uia_chain_at(x, y, uia)
                item, idx = _best_uia_item(chain)
                path = None
                if item:
                    r = item.get("rect") or {}
                    if r.get("width", 0) > 0 and r.get("height", 0) > 0:
                        path = list(reversed(chain))[: len(chain) - idx]  # 根 → 最优
                        # 最优元素 ≈ 整窗 → 深搜找细粒度
                        hwnd = _WindowFromPoint(wintypes.POINT(x, y))
                        if hwnd:
                            wr = _get_window_rect(hwnd)
                            if wr["width"] > 0 and wr["height"] > 0 \
                                    and r.get("width", 0) * r.get("height", 0) > 0.6 * wr["width"] * wr["height"]:
                                path = None
                if not path:
                    # hit-test 不可用（0x0/None）或整窗 → 深搜兜底（混合架构应用）
                    item, path = _deepest_uia_element(x, y, uia)
                if item and path:
                    result["value"] = {
                        "found": True,
                        "name": item.get("name", ""), "class_name": item.get("class_name", ""),
                        "control_type": item.get("control_type", ""), "automation_id": item.get("automation_id", ""),
                        "rect": item.get("rect", {}), "path": path,
                    }
                    _uia_debug_log(item, chain or list(reversed(path)))
        except Exception:
            pass
        finally:
            result["done"] = True

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(_UIA_QUERY_TIMEOUT)
    if result["done"]:
        return result["value"]
    # 超时：UIA provider 卡死 → 运行时黑名单，本次会话内跳过
    hwnd = _WindowFromPoint(wintypes.POINT(x, y))
    if hwnd:
        _blacklist_process(hwnd)
    return None


def _get_uia_rect(x, y):
    """UIA 命中框：轻量 hit-test 优先；hit-test 失效（0x0/None，XAML island 等混合应用）时
    深搜兜底（节流缓存，避免每帧全树遍历）。只读矩形，避免在 UIA provider 敏感应用上卡死。"""
    global _uia_module
    uia = _uia_module
    if not uia:
        try:
            _com_init()
            import uiautomation as uia
            _uia_module = uia
        except Exception:
            return None
    # 1) 轻量 hit-test（正常应用，O(1)）
    try:
        ctrl = uia.ControlFromPoint(x, y)
        if ctrl:
            br = ctrl.BoundingRectangle
            if br and br.width() > 0 and br.height() > 0:
                _deep_cache["hwnd"] = 0  # 清深搜缓存
                return {"left": br.left, "top": br.top, "right": br.right, "bottom": br.bottom,
                        "width": br.width(), "height": br.height()}
    except Exception:
        pass
    # 2) 深搜兜底（节流：窗口/位移 >15px 或 >0.4s 才重算）
    hwnd = _WindowFromPoint(wintypes.POINT(x, y))
    now = time.time()
    c = _deep_cache
    if (hwnd != c["hwnd"] or abs(x - c["x"]) > 15 or abs(y - c["y"]) > 15 or now - c["t"] > 0.4):
        item, _ = _deepest_uia_element(x, y, uia, max_nodes=200)
        rect = None
        if item:
            r = item.get("rect") or {}
            if r.get("width", 0) > 0:
                rect = r
        c.update(hwnd=hwnd, x=x, y=y, t=now, rect=rect)
    return c.get("rect")


def _get_best_rect(hwnd, x, y):
    hwnd_rect = _get_window_rect(hwnd)
    if _is_skip_uia(hwnd):
        return hwnd_rect, None
    uia_rect = _get_uia_rect(x, y)
    if uia_rect and uia_rect.get("width", 0) > 0:
        return uia_rect, uia_rect
    return hwnd_rect, None


_uia_module = None
_deep_cache = {"hwnd": 0, "x": 0, "y": 0, "t": 0, "rect": None}  # 深搜兜底节流缓存

def _uia_init():
    global _uia_module
    if _uia_module is not None: return
    try:
        _com_init()
        import uiautomation as uia
        _uia_module = uia
    except Exception:
        pass

def _uia_done():
    global _uia_module
    if _uia_module is not None:
        try: _com_uninit()
        except Exception:
            pass
        _uia_module = None


# ─── Info overlay (top-center floating tip) ───

_info_hwnd = None

def _ensure_info_window():
    global _info_hwnd
    if _info_hwnd: return _info_hwnd
    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", ctypes.c_void_p),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HICON), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]
    hInst = _kernel32.GetModuleHandleW(None)
    wc = WNDCLASSW()
    wc.lpfnWndProc = ctypes.cast(_user32.DefWindowProcW, ctypes.c_void_p)
    wc.hInstance = hInst; wc.lpszClassName = "RpaInfo"
    wc.hbrBackground = _gdi32.CreateSolidBrush(_bgr(INFO_BG))
    _user32.RegisterClassW(ctypes.byref(wc))
    _info_hwnd = _user32.CreateWindowExW(
        0x00000008 | 0x00000080 | 0x00000020, "RpaInfo", "", 0x80000000,
        0, 0, 460, INFO_H, None, None, hInst, None)
    _user32.SetLayeredWindowAttributes(_info_hwnd, 0, 240, 0x02)
    return _info_hwnd

_info_side = False
INFO_W = 460; INFO_H = 190; INFO_MARGIN = 6; INFO_PAD = 10
INFO_BG = 0x4b5563     # 灰色背景
INFO_BORDER = 0xffffff  # 白色边框
INFO_HINT = "Alt+点击 捕获 · Alt+1/Alt+2 父/子级 · Esc 取消"

def _info_box_contains(pt_x, pt_y, box_x, box_y):
    """鼠标是否在悬浮框 +10px 缓冲区内。"""
    return (pt_x >= box_x - 10 and pt_x <= box_x + INFO_W + 10 and
            pt_y >= box_y - 10 and pt_y <= box_y + INFO_H + 10)

def _move_info_window():
    """重新定位悬浮框以躲避鼠标（光标在框内则翻到另一侧）。"""
    global _info_side
    hwnd = _ensure_info_window()
    sw = _GetSystemMetrics(SM_CXSCREEN)
    pt = wintypes.POINT(); _GetCursorPos(ctypes.byref(pt))
    box_x = sw - INFO_W - INFO_MARGIN if _info_side else INFO_MARGIN
    if _info_box_contains(pt.x, pt.y, box_x, INFO_MARGIN):
        _info_side = not _info_side
        box_x = sw - INFO_W - INFO_MARGIN if _info_side else INFO_MARGIN
    _user32.MoveWindow(hwnd, box_x, INFO_MARGIN, INFO_W, INFO_H, True)
    _user32.ShowWindow(hwnd, 1)


def show_info(text: str):
    hwnd = _ensure_info_window()
    if text:
        lines = text.split("\n")
        hdc = _GetDC(hwnd)
        r = wintypes.RECT(0, 0, INFO_W, INFO_H)
        br = _CreateSolidBrush(_bgr(INFO_BG))
        _FillRect(hdc, ctypes.byref(r), br)
        _DeleteObject(br)
        # 白色边框（2px：外圈 + 内缩 1px）
        wbr = _CreateSolidBrush(_bgr(INFO_BORDER))
        _FrameRect(hdc, ctypes.byref(r), wbr)
        _FrameRect(hdc, ctypes.byref(wintypes.RECT(1, 1, INFO_W - 1, INFO_H - 1)), wbr)
        _DeleteObject(wbr)
        _SetBkMode(hdc, 1)
        font = _CreateFontW(19, 0, 0, 0, 400, 0, 0, 0, 0, 0, 0, 0, 0, "Consolas")
        old = _SelectObject(hdc, font)
        for i, line in enumerate(lines[:7]):
            is_current = (i == len(lines[:7]) - 2)  # 倒数第二行是当前选中
            _SetTextColor(hdc, 0x0090CAF9 if is_current else 0x00A0A0B0)
            buf = ctypes.create_unicode_buffer(line)
            _DrawTextW(hdc, buf, -1,
                       ctypes.byref(wintypes.RECT(INFO_PAD, 3 + i * 20,
                                                  INFO_W - INFO_PAD, 23 + i * 20)),
                       0x0000 | 0x0010)
        _SelectObject(hdc, old)
        _DeleteObject(font)
        # 分隔线 + 操作提示
        sep = _CreateSolidBrush(_bgr(0x6b7280))
        _FillRect(hdc, ctypes.byref(wintypes.RECT(INFO_PAD, 146, INFO_W - INFO_PAD, 148)), sep)
        _DeleteObject(sep)
        hint_font = _CreateFontW(16, 0, 0, 0, 400, 0, 0, 0, 0, 0, 0, 0, 0, "Consolas")
        old2 = _SelectObject(hdc, hint_font)
        _SetTextColor(hdc, 0x00FFFFFF)
        hbuf = ctypes.create_unicode_buffer(INFO_HINT)
        _DrawTextW(hdc, hbuf, -1, ctypes.byref(wintypes.RECT(INFO_PAD, 154, INFO_W - INFO_PAD, 174)), 0x0000 | 0x0010)
        _SelectObject(hdc, old2)
        _DeleteObject(hint_font)
        _ReleaseDC(hwnd, hdc)
        _move_info_window()
    else:
        _user32.ShowWindow(hwnd, 0)


# ─── Border window (SetWindowRgn — always on top, never overwritten) ───

_border_hwnd = None
_border_visible = False


def _ensure_border_window():
    global _border_hwnd
    if _border_hwnd: return _border_hwnd
    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", ctypes.c_void_p),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HICON), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]
    hInst = _kernel32.GetModuleHandleW(None)
    wc = WNDCLASSW()
    wc.lpfnWndProc = ctypes.cast(_user32.DefWindowProcW, ctypes.c_void_p)
    wc.hInstance = hInst; wc.lpszClassName = "RpaBorder"; wc.hbrBackground = _gdi32.CreateSolidBrush(_bgr(BORDER_COLOR))
    _user32.RegisterClassW(ctypes.byref(wc))
    _border_hwnd = _user32.CreateWindowExW(
        0x00000008 | 0x00000080 | 0x00000020, "RpaBorder", "", 0x80000000,
        # WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT
        0, 0, 100, 100, None, None, hInst, None)
    return _border_hwnd


def _set_border_region(hwnd, w, h):
    outer = _gdi32.CreateRectRgn(0, 0, w, h)
    inner = _gdi32.CreateRectRgn(BORDER_T, BORDER_T, w - BORDER_T, h - BORDER_T)
    _gdi32.CombineRgn(outer, outer, inner, 3)  # RGN_DIFF
    _gdi32.DeleteObject(inner)
    _user32.SetWindowRgn(hwnd, outer, True)


def _set_window_color(hwnd, rgb):
    _DeleteObject(_GetClassLongPtrW(hwnd, -10))
    _SetClassLongPtrW(hwnd, -10, _CreateSolidBrush(_bgr(rgb)))


def show_border(rect: dict | None):
    global _border_visible
    hwnd = _ensure_border_window()
    if rect and rect.get("width", 0) > 0 and rect.get("height", 0) > 0:
        _set_border_region(hwnd, rect["width"], rect["height"])
        _user32.MoveWindow(hwnd, rect["left"], rect["top"], rect["width"], rect["height"], True)
        _user32.ShowWindow(hwnd, 1); _border_visible = True
        _user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0010)
        _user32.BringWindowToTop(hwnd)
    elif _border_visible:
        _user32.ShowWindow(hwnd, 0); _border_visible = False


def _flash_once(hwnd, rect, color):
    _set_window_color(hwnd, color)
    _set_border_region(hwnd, rect["width"], rect["height"])  # hollow border
    _user32.MoveWindow(hwnd, rect["left"], rect["top"], rect["width"], rect["height"], True)
    _user32.ShowWindow(hwnd, 1); time.sleep(0.2)
    _user32.ShowWindow(hwnd, 0); time.sleep(0.15)


def flash_element(element: ElementInfo, times=3):
    # 优先用 UIA 细粒度 rect（图标/菜单项等），其次 HWND rect
    rect = None
    if element.uia_path:
        leaf = element.uia_path[-1]
        if leaf.get("rect", {}).get("width", 0) > 0:
            rect = leaf["rect"]
    if not rect:
        found = _find_element_hwnd(element)
        rect = _get_window_rect(found) if found else element.rect
    if not rect or not rect.get("width"): return False
    found = _find_element_hwnd(element)
    hwnd = _ensure_border_window(); show_border(None)
    color = 0x22c55e if found else 0xdc2626
    for _ in range(times): _flash_once(hwnd, rect, color)
    _set_window_color(hwnd, BORDER_COLOR)
    return found is not None


# ─── Element lookup ───

def _find_element_hwnd(element: ElementInfo) -> int | None:
    path = element.win32_path
    if not path: return None
    hwnd = _find_top_window(path[0])
    if not hwnd or len(path) == 1: return hwnd
    from scripts.capture_gui.win32_utils import find_child_window
    for lvl in path[1:]:
        hwnd = find_child_window(hwnd, class_name=lvl.get("class_name", ""), title=lvl.get("title", ""))
        if not hwnd: return None
    return hwnd


def _find_top_window(info: dict) -> int | None:
    from scripts.capture_gui.win32_utils import find_window, find_window_by_title_fuzzy
    t, cls = info.get("title", ""), info.get("class_name", "")
    if t:
        m = find_window_by_title_fuzzy(t)
        if m: return m[0]["hwnd"]
        h = find_window(title=t)
        if h: return h
    if cls:
        h = find_window(class_name=cls)
        if h: return h
    return None


# ─── Main capture loop ───

_SHELL_CLASSES = {"Shell_TrayWnd", "MSTaskSwWClass", "MSTaskListWClass",
                   "TrayButton", "Start", "TrayNotifyWnd", "ReBarWindow32"}

def _is_shell(hwnd) -> bool:
    return _get_class_name(hwnd) in _SHELL_CLASSES


def _screen_size() -> dict:
    return {"w": _GetSystemMetrics(SM_CXSCREEN), "h": _GetSystemMetrics(SM_CYSCREEN)}


def _grab_region_screenshot(rect: dict | None) -> str:
    """截取屏幕指定区域，返回 base64 dataURL。失败返回空串。"""
    if not rect or not rect.get("width", 0) > 0 or not rect.get("height", 0) > 0:
        return ""
    try:
        from PIL import ImageGrab
        import io
        bbox = (int(rect["left"]), int(rect["top"]),
                int(rect["left"] + rect["width"]), int(rect["top"] + rect["height"]))
        img = ImageGrab.grab(bbox=bbox)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        import base64
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""

BROWSER_CHROME_HEIGHT = 88

def _screen_to_viewport(sx, sy, win_rect):
    return (sx - win_rect["left"], max(0, sy - win_rect["top"] - BROWSER_CHROME_HEIGHT))

def _viewport_rect_to_screen(dom_rect, win_rect):
    return {
        "left": dom_rect["left"] + win_rect["left"],
        "top": dom_rect["top"] + win_rect["top"] + BROWSER_CHROME_HEIGHT,
        "right": dom_rect["right"] + win_rect["left"],
        "bottom": dom_rect["bottom"] + win_rect["top"] + BROWSER_CHROME_HEIGHT,
        "width": dom_rect["width"], "height": dom_rect["height"],
    }

def _is_web_browser(hwnd) -> bool:
    """是否是真正的浏览器顶层窗口（避免把 Electron 应用 / Windows Terminal 当浏览器）。"""
    cls = _get_class_name(hwnd)
    if cls not in ("Chrome_WidgetWin_1", "Chrome_WidgetWin_0",
                   "MozillaWindowClass", "ApplicationFrameWindow"):
        return False
    exe = _get_process_exe(hwnd).lower()
    return exe.endswith(("chrome.exe", "msedge.exe", "firefox.exe"))


def _find_active_browser():
    """返回最上层（Z 序最前）的非最小化浏览器窗口；无则 None。"""
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, _lp):
        if not _IsWindowVisible(hwnd):
            return True
        if _IsIconic(hwnd):
            return True
        if _is_web_browser(hwnd):
            found.append(hwnd)
        return True

    _EnumWindows(_enum, 0)
    return found[0] if found else None


class BackToDesktop(Exception):
    """网页拾取中用户切回桌面拾取 —— 结束当前拾取但不结束整场捕获。"""


def _format_web_hover(hover: dict) -> str:
    tag = hover.get("tag") or ""
    id_ = hover.get("id") or ""
    cls = hover.get("classes") or ""
    text = (hover.get("text") or "").strip()
    lines = []
    if tag:
        name = tag
        if id_: name += "#" + id_
        if cls: name += "." + cls
        lines.append(name)
    if text:
        lines.append(text[:50])
    if lines:
        lines.append("")
        lines.append("Alt+点击 捕获 · Alt+1/Alt+2 父/子级")
        lines.append("Esc 结束")
    return "\n".join(lines)


def _poll_hover_thread(request_id: str, stop: threading.Event):
    """网页拾取期间轮询悬停元素信息/提示 → 悬浮窗实时显示。

    每轮都调用 _move_info_window() 重新躲避鼠标（不依赖文本变化）。
    """
    try:
        from scripts.capture_gui.ws_client import poll_capture_hover
    except Exception:
        return
    last_text = ""
    while not stop.is_set():
        data = poll_capture_hover(request_id)
        note = (data.get("note") or "").strip()
        hover = data.get("hover") or {}
        text = None
        if hover:
            text = _format_web_hover(hover)
        elif note:
            text = note  # 受限页/载入中等提示
        if text:
            _move_info_window()  # 每轮都重新躲避鼠标
            if text != last_text:
                last_text = text
                if not stop.is_set():
                    show_info(text)
        time.sleep(0.25)


def _poll_esc_cancel(request_id: str, stop: threading.Event):
    """网页拾取期间 Esc 兜底取消：不依赖 content 脚本（受限页/载入中也能立即取消）。"""
    try:
        from scripts.capture_gui.ws_client import cancel_browser_capture
    except Exception:
        return
    while not stop.is_set():
        if _GetAsyncKeyState(VK_ESCAPE) & 0x8000:
            cancel_browser_capture(request_id)
            return
        time.sleep(0.05)


def _capture_via_extension(browser_hwnd, sx, sy, web_only: bool = False) -> ElementInfo | None:
    """委托浏览器插件原生捕获。阻塞等待用户 Alt+Click。"""
    win_rect = _get_window_rect(browser_hwnd)
    vx, vy = _screen_to_viewport(sx, sy, win_rect)
    show_info("网页拾取中... 悬停查看元素 · Alt+点击确认")
    request_id = str(uuid.uuid4())[:8]
    stop = threading.Event()
    threading.Thread(target=_poll_hover_thread, args=(request_id, stop), daemon=True).start()
    threading.Thread(target=_poll_esc_cancel, args=(request_id, stop), daemon=True).start()
    try:
        from scripts.capture_gui.ws_client import launch_browser_capture
        result = launch_browser_capture(vx, vy, timeout=300.0, request_id=request_id, web_only=web_only)
        if result.get("backToDesktop"):
            raise BackToDesktop()
        if result.get("error"):
            return None
        def _strip_pf(s):
            for pf in ("css:", "xpath:", "drission:", "verse:"):
                if s.lower().startswith(pf): return s[len(pf):]
            return s
        css = xpath = ""
        candidates = []
        for c in result.get("candidates", []):
            fam = c.get("family", "")
            syn = _strip_pf(c.get("syntax", ""))
            cc = dict(c); cc["syntax"] = syn
            candidates.append(cc)
            if not css and fam == "css": css = syn
            if not xpath and fam == "xpath": xpath = syn
        name = result.get("name") or result.get("inner_text", "")[:30] or result.get("tag", "")
        win_rect = _get_window_rect(browser_hwnd)
        rect = win_rect
        elem_rect = result.get("rect") or {}
        if elem_rect.get("width", 0) > 0:
            rect = _viewport_rect_to_screen(elem_rect, win_rect)
        cls = _get_class_name(browser_hwnd)
        title = _get_window_text(browser_hwnd)
        path = _get_ancestor_path(browser_hwnd)
        list_info = {}
        lf = result.get("listFamily") or {}
        if lf.get("container"):
            list_info = {
                "listContainer": lf.get("container", ""),
                "listItem": lf.get("item", ""),
                "listSize": lf.get("size", 0),
            }
        info = ElementInfo(
            name=name,
            element_type="web", class_name=cls, title=title,
            rect=rect, hwnd=browser_hwnd, win32_path=path,
            css_selector=css, xpath=xpath,
            tag_name=result.get("tag", "") or result.get("tagName", ""),
            candidates=candidates,
            screenshot=result.get("screenshot", ""),
            dom_path=result.get("domPath", []),
            elem_attrs=result.get("features", {}) or {},
            list_info=list_info,
            page_url=result.get("pageUrl") or result.get("url") or "",
            region=rect,
            screen_size=_screen_size(),
        )
        return info
    except BackToDesktop:
        raise  # 切回桌面信号不能被通用 except 吞掉，放行给 run_capture 继续循环
    except Exception:
        return None
    finally:
        stop.set()  # 停止悬停信息轮询线程


def run_capture(mode: str = "desktop") -> ElementInfo | None:
    sw = _GetSystemMetrics(SM_CXSCREEN); sh = _GetSystemMetrics(SM_CYSCREEN)
    pt = wintypes.POINT()
    last_hwnd = None; captured = None
    last_pt = (0, 0)
    # 层级导航栈：记录用户按 Alt+1 上走过的路径，Alt+2 可退回
    parent_stack = []

    def _build_info_text(hwnd):
        rect = _get_window_rect(hwnd)
        path = _get_ancestor_path(hwnd)
        # 最近 6 层祖先，不足用空行补齐
        levels = path[-6:]
        lines = []
        n = len(levels)
        for i in range(6):
            if i < n:
                cls = levels[i]["class_name"]
                is_current = (i == n - 1)
                prefix = "> " if is_current else "  "
                lines.append(f"{prefix}{cls}")
            else:
                lines.append("")
        lines.append(f"    {rect['width']}×{rect['height']}")
        return "\n".join(lines)

    def _select_hwnd(hwnd):
        """选中并高亮指定 hwnd。"""
        nonlocal last_hwnd
        if hwnd:
            rect = _get_window_rect(hwnd)
            if rect["width"] > 0 and rect["height"] > 0:
                show_border(rect)
                last_hwnd = hwnd
                show_info(_build_info_text(hwnd))

    editor_hwnd = _hide_editor_window()  # 捕获期间隐藏 RPA 编辑器（Electron）
    try:
        _uia_init()
        if mode == "web":
            # 网页模式：直接对最前面的浏览器进入 DOM 拾取
            browser = _find_active_browser()
            if not browser:
                show_info("未找到浏览器窗口，请先打开 Chrome/Edge 并置于最前")
                time.sleep(1.2)
                return None
            rect = _get_window_rect(browser)
            cx, cy = rect["left"] + rect["width"] // 2, rect["top"] + rect["height"] // 2
            _user32.SetForegroundWindow(browser)  # 浏览器置前，扩展 currentWindow 才正确
            try:
                return _capture_via_extension(browser, cx, cy, web_only=True)
            except BackToDesktop:
                return None  # web 模式 content 已禁用切换，理论不触发，兜底
        while True:
            if _GetAsyncKeyState(VK_ESCAPE) & 0x8000: break
            if _GetAsyncKeyState(VK_RBUTTON) & 0x8000: break

            _GetCursorPos(ctypes.byref(pt))
            target = _WindowFromPoint(pt) if 0 <= pt.x < sw * 2 and -sh < pt.y < sh * 2 else None
            if target and _get_class_name(target) == "RpaBorder":
                target = None
            if not target and last_hwnd and _user32.IsWindow(last_hwnd):
                target = last_hwnd

            # Alt+1 → 选父级
            if (_GetAsyncKeyState(VK_1) & 0x8000) and (_GetAsyncKeyState(VK_MENU) & 0x8000):
                if target:
                    parent = _GetParent(target)
                    if parent:
                        parent_stack.append(target)
                        target = parent
                        _select_hwnd(target)
                time.sleep(0.15)
                continue

            # Alt+2 → 退回子级
            if (_GetAsyncKeyState(VK_2) & 0x8000) and (_GetAsyncKeyState(VK_MENU) & 0x8000):
                if parent_stack:
                    target = parent_stack.pop()
                    _select_hwnd(target)
                time.sleep(0.15)
                continue

            # 鼠标移动 → 自动选最细粒度
            if target != last_hwnd and not parent_stack:
                last_pt = (pt.x, pt.y)
                if target:
                    rect = _get_window_rect(target)
                    if rect["width"] > 0 and rect["height"] > 0:
                        show_border(rect)
                        show_info(_build_info_text(target))
                    else:
                        show_border(None); show_info("")
                else:
                    show_border(None); show_info("")
                last_hwnd = target
                parent_stack.clear()
            elif target == last_hwnd and target and abs(pt.x - last_pt[0]) + abs(pt.y - last_pt[1]) > 6:
                last_pt = (pt.x, pt.y)
                uia_rect, _ = _get_best_rect(target, pt.x, pt.y)
                if uia_rect["width"] > 0:
                    show_border(uia_rect)
                    show_info(_build_info_text(target))
                else:
                    uia_rect, _ = _get_best_rect(target, pt.x, pt.y)
                    if uia_rect["width"] > 0:
                        show_border(uia_rect)
                        show_info(_build_info_text(target))

            # Alt+点击 → 捕获桌面元素（Win32+UIA）
            if (_GetAsyncKeyState(VK_LBUTTON) & 0x8000) and (_GetAsyncKeyState(VK_MENU) & 0x8000) and last_hwnd:
                show_border(None); show_info("")
                time.sleep(0.1)
                captured = _build_element_info(last_hwnd, pt.x, pt.y)
                break
            time.sleep(0.03)
    finally:
        show_border(None); show_info("")
        _uia_done()
        _restore_editor_window(editor_hwnd)  # 捕获结束恢复并前置 RPA 编辑器
    return captured


def _build_element_info(hwnd, x, y) -> ElementInfo:
    cls = _get_class_name(hwnd); title = _get_window_text(hwnd); rect = _get_window_rect(hwnd)
    path = _get_ancestor_path(hwnd)
    info = ElementInfo(name=title or cls, class_name=cls, title=title, rect=rect, hwnd=hwnd, win32_path=path)
    if _is_browser_window(cls): info.element_type = "web"
    uia = None
    if not _is_skip_uia(hwnd):
        uia = _try_uia_capture(x, y)
    best_rect = rect
    if uia:
        info.control_type = uia.get("control_type", ""); info.automation_id = uia.get("automation_id", "")
        info.uia_path = uia.get("path", [])
        if not info.name: info.name = uia.get("name", "")
        if info.element_type == "web" and info.control_type in (
            "EditControl", "ButtonControl", "HyperlinkControl", "TextControl",
            "ComboBoxControl", "CheckBoxControl", "ListItemControl", "TreeItemControl"):
            info.name = uia.get("name") or title
        uia_rect = uia.get("rect") or {}
        if (uia_rect.get("width", 0) > 0
                and 0 < uia_rect.get("width", 0) <= 500
                and 0 < uia_rect.get("height", 0) <= 500):
            best_rect = uia_rect
    if _is_browser_in_chain(path) and info.element_type != "web":
        info.element_type = "web"
    # 所有元素统一捕获区域快照（图像兜底数据）
    info.region = best_rect
    info.screen_size = _screen_size()
    info.screenshot = _grab_region_screenshot(best_rect)
    return info
