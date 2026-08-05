"""桌面元素捕获覆盖层 — SetWindowRgn 挖空窗口方案。

鼠标移动时实时高亮目标控件（WS_EX_TOPMOST + SetWindowRgn 挖空中间，
只留 3px 蓝色边框 — 永远在最上面，不会被任何窗口覆盖）。
左键点击捕获，右键/Esc 取消。同时收集 Win32 + UIA 信息。
"""
import ctypes
import ctypes.wintypes as wintypes
import time
from dataclasses import dataclass, field

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_kernel32 = ctypes.windll.kernel32

# ── Constants ──
VK_ESCAPE = 0x1B; VK_RBUTTON = 0x02; VK_LBUTTON = 0x01
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
    tab_id: int = 0  # 捕获来源浏览器标签页(web元素验证用)


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
        "Chrome_WidgetWin_1", "MozillaWindowClass",
        "CASCADIA_HOSTING_WINDOW_CLASS", "ApplicationFrameWindow",
    ))

def _is_render_area(hwnd) -> bool:
    """是否是浏览器页面渲染区域（而非标签栏/菜单/地址栏）。"""
    cls = _get_class_name(hwnd)
    return cls == "Chrome_RenderWidgetHostHWND"


def _is_browser_in_chain(path: list) -> bool:
    return any(_is_browser_window(p.get("class_name", "")) for p in path)


def _try_uia_capture(x, y) -> dict | None:
    try:
        import pythoncom; pythoncom.CoInitialize()
        import uiautomation as uia
        ctrl = uia.ControlFromPoint(x, y)
        if not ctrl: return None
        chain = []; cur = ctrl; visited = set()
        while cur and id(cur) not in visited:
            visited.add(id(cur))
            try: br = cur.BoundingRectangle
            except: br = None
            chain.insert(0, {
                "name": cur.Name or "", "class_name": cur.ClassName or "",
                "control_type": cur.ControlTypeName or "", "automation_id": cur.AutomationId or "",
                "rect": {"left": br.left, "top": br.top, "right": br.right, "bottom": br.bottom,
                         "width": br.width() if br else 0, "height": br.height() if br else 0} if br else {},
            })
            try:
                p = cur.GetParentControl()
                if not p or p.ControlTypeName == "DesktopControl": break
                cur = p
            except: break
        leaf = chain[-1] if chain else {}
        return {"found": True, "name": leaf.get("name", ""), "class_name": leaf.get("class_name", ""),
                "control_type": leaf.get("control_type", ""), "automation_id": leaf.get("automation_id", ""),
                "rect": leaf.get("rect", {}), "path": chain}
    except:
        return None
    finally:
        try: import pythoncom; pythoncom.CoUninitialize()
        except: pass


def _get_uia_rect(x, y):
    global _uia_module
    uia = _uia_module
    if not uia:
        try:
            import pythoncom; pythoncom.CoInitialize()
            import uiautomation as uia
            _uia_module = uia
        except: return None
    try:
        ctrl = uia.ControlFromPoint(x, y)
        if not ctrl: return None
        br = ctrl.BoundingRectangle
        if br.width() > 0 and br.height() > 0:
            return {"left": br.left, "top": br.top, "right": br.right, "bottom": br.bottom,
                    "width": br.width(), "height": br.height()}
    except: pass
    return None


def _get_best_rect(hwnd, x, y):
    hwnd_rect = _get_window_rect(hwnd)
    uia_rect = _get_uia_rect(x, y)
    # Only trust UIA for reasonably small elements (< 500x500)
    if uia_rect and 0 < uia_rect.get("width", 0) <= 500 and 0 < uia_rect.get("height", 0) <= 500:
        return uia_rect, uia_rect
    return hwnd_rect, None


_uia_module = None

def _uia_init():
    global _uia_module
    if _uia_module is not None: return
    try:
        import pythoncom; pythoncom.CoInitialize()
        import uiautomation as uia
        _uia_module = uia
    except: pass

def _uia_done():
    global _uia_module
    if _uia_module is not None:
        try: import pythoncom; pythoncom.CoUninitialize()
        except: pass
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
    wc.hbrBackground = _gdi32.CreateSolidBrush(_bgr(0x0f172a))
    _user32.RegisterClassW(ctypes.byref(wc))
    _info_hwnd = _user32.CreateWindowExW(
        0x00000008 | 0x00000080 | 0x00000020, "RpaInfo", "", 0x80000000,
        0, 0, 460, 156, None, None, hInst, None)
    _user32.SetLayeredWindowAttributes(_info_hwnd, 0, 240, 0x02)
    return _info_hwnd

_info_side = False
INFO_W = 460; INFO_H = 156; INFO_MARGIN = 6; INFO_PAD = 10

def _info_box_contains(pt_x, pt_y, box_x, box_y):
    """鼠标是否在悬浮框 +10px 缓冲区内。"""
    return (pt_x >= box_x - 10 and pt_x <= box_x + INFO_W + 10 and
            pt_y >= box_y - 10 and pt_y <= box_y + INFO_H + 10)

def show_info(text: str):
    global _info_side
    hwnd = _ensure_info_window()
    if text:
        lines = text.split("\n")
        hdc = _GetDC(hwnd)
        r = wintypes.RECT(0, 0, INFO_W, INFO_H)
        br = _CreateSolidBrush(_bgr(0x0f172a))
        _FillRect(hdc, ctypes.byref(r), br)
        _DeleteObject(br)
        _SetBkMode(hdc, 1)
        font = _CreateFontW(19, 0, 0, 0, 400, 0, 0, 0, 0, 0, 0, 0, 0, "Consolas")
        old = _SelectObject(hdc, font)
        for i, line in enumerate(lines[:7]):
            is_current = (i == len(lines[:7]) - 2)  # 倒数第二行是当前选中
            _SetTextColor(hdc, 0x0090CAF9 if is_current else 0x00A0A0B0)
            buf = ctypes.create_unicode_buffer(line)
            _DrawTextW(hdc, buf, -1, ctypes.byref(wintypes.RECT(INFO_PAD, 3 + i * 20, INFO_W - INFO_PAD, 23 + i * 20)), 0x0000 | 0x0010)
        _SelectObject(hdc, old)
        _DeleteObject(font)
        _ReleaseDC(hwnd, hdc)
        sw = _GetSystemMetrics(SM_CXSCREEN)
        pt = wintypes.POINT(); _GetCursorPos(ctypes.byref(pt))
        box_x = sw - INFO_W - INFO_MARGIN if _info_side else INFO_MARGIN
        if _info_box_contains(pt.x, pt.y, box_x, INFO_MARGIN):
            _info_side = not _info_side
            box_x = sw - INFO_W - INFO_MARGIN if _info_side else INFO_MARGIN
        _user32.MoveWindow(hwnd, box_x, INFO_MARGIN, INFO_W, INFO_H, True)
        _user32.ShowWindow(hwnd, 1)
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

def _find_browser_root(hwnd):
    for p in reversed(_get_ancestor_path(hwnd)):
        if _is_browser_window(p.get("class_name", "")):
            return p["hwnd"]
    return None

def _capture_via_extension(browser_hwnd, sx, sy) -> ElementInfo | None:
    """委托浏览器插件原生捕获。阻塞等待用户 Alt+Click。"""
    win_rect = _get_window_rect(browser_hwnd)
    vx, vy = _screen_to_viewport(sx, sy, win_rect)
    show_info("插件捕获中... 点击页面元素")
    try:
        from scripts.capture_gui.ws_client import launch_browser_capture
        result = launch_browser_capture(vx, vy, timeout=20.0)
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
        rect = _get_window_rect(browser_hwnd)
        cls = _get_class_name(browser_hwnd)
        title = _get_window_text(browser_hwnd)
        path = _get_ancestor_path(browser_hwnd)
        info = ElementInfo(
            name=name,
            element_type="web", class_name=cls, title=title,
            rect=rect, hwnd=browser_hwnd, win32_path=path,
            css_selector=css, xpath=xpath,
            tag_name=result.get("tag", "") or result.get("tagName", ""),
            candidates=candidates,
            screenshot=result.get("screenshot", ""),
            dom_path=result.get("path", []),
            elem_attrs=result.get("attrs", {}),
            list_info={k: result.get(k) for k in ("listContainer","listItem","listSize","listSimilarity") if result.get(k)},
            tab_id=result.get("tabId", 0) or 0,
        )
        return info
    except Exception:
        return None


def run_capture() -> ElementInfo | None:
    sw = _GetSystemMetrics(SM_CXSCREEN); sh = _GetSystemMetrics(SM_CYSCREEN)
    pt = wintypes.POINT()
    last_hwnd = None; captured = None
    last_pt = (0, 0)
    # 层级导航栈：记录用户按 ↑ 上走过的路径，↓ 可退回
    parent_stack = []
    VK_UP = 0x26; VK_DOWN = 0x28

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

    try:
        _uia_init()
        while True:
            if _GetAsyncKeyState(VK_ESCAPE) & 0x8000: break
            if _GetAsyncKeyState(VK_RBUTTON) & 0x8000: break

            _GetCursorPos(ctypes.byref(pt))
            target = _WindowFromPoint(pt) if 0 <= pt.x < sw * 2 and -sh < pt.y < sh * 2 else None
            if target and _get_class_name(target) == "RpaBorder":
                target = None
            if not target and last_hwnd and _user32.IsWindow(last_hwnd):
                target = last_hwnd

            # ↑ 上箭头 → 选父级
            if _GetAsyncKeyState(VK_UP) & 0x8000:
                if target:
                    parent = _GetParent(target)
                    if parent:
                        parent_stack.append(target)
                        target = parent
                        _select_hwnd(target)
                time.sleep(0.15)
                continue

            # ↓ 下箭头 → 退回子级
            if _GetAsyncKeyState(VK_DOWN) & 0x8000:
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

            if (_GetAsyncKeyState(VK_LBUTTON) & 0x8000) and last_hwnd:
                show_border(None); show_info("")
                time.sleep(0.1)
                # 浏览器网页渲染区 → 插件捕获；标签栏/菜单 → 桌面捕获
                cls_last = _get_class_name(last_hwnd)
                broot = _find_browser_root(last_hwnd) or (last_hwnd if _is_browser_window(cls_last) else None)
                if broot and _is_render_area(last_hwnd):
                    captured = _capture_via_extension(broot, pt.x, pt.y)
                else:
                    captured = _build_element_info(last_hwnd, pt.x, pt.y)
                break
            time.sleep(0.03)
    finally:
        show_border(None); show_info("")
        _uia_done()
    return captured


def _build_element_info(hwnd, x, y) -> ElementInfo:
    cls = _get_class_name(hwnd); title = _get_window_text(hwnd); rect = _get_window_rect(hwnd)
    path = _get_ancestor_path(hwnd)
    info = ElementInfo(name=title or cls, class_name=cls, title=title, rect=rect, hwnd=hwnd, win32_path=path)
    if _is_browser_window(cls): info.element_type = "web"
    uia = _try_uia_capture(x, y)
    if uia:
        info.control_type = uia.get("control_type", ""); info.automation_id = uia.get("automation_id", "")
        info.uia_path = uia.get("path", [])
        if not info.name: info.name = uia.get("name", "")
        if info.element_type == "web" and info.control_type in (
            "EditControl", "ButtonControl", "HyperlinkControl", "TextControl",
            "ComboBoxControl", "CheckBoxControl", "ListItemControl", "TreeItemControl"):
            info.name = uia.get("name") or title
    if _is_browser_in_chain(path) and info.element_type != "web":
        info.element_type = "web"
    return info
