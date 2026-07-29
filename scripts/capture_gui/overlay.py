"""全屏透明捕获覆盖层。

鼠标变为十字光标，移动时 XOR 高亮目标控件。
左键点击捕获，右键/Esc 取消。
同时收集 Win32 + UIA 信息，浏览器窗口自动识别。
"""

import ctypes
import ctypes.wintypes as wintypes
import time
import sys
import json
import threading
from dataclasses import dataclass, field

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_kernel32 = ctypes.windll.kernel32

# ── Constants ──
R2_NOTXORPEN = 10
PS_SOLID = 0
VK_ESCAPE = 0x1B
VK_RBUTTON = 0x02
VK_LBUTTON = 0x01
VK_MENU = 0x12  # Alt
SM_CXSCREEN = 0
SM_CYSCREEN = 1

# ── Win32 API declarations ──
_GetCursorPos = _user32.GetCursorPos
_GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]

_GetAsyncKeyState = _user32.GetAsyncKeyState
_GetAsyncKeyState.argtypes = [ctypes.c_int]
_GetAsyncKeyState.restype = ctypes.c_short

_WindowFromPoint = _user32.WindowFromPoint
_WindowFromPoint.argtypes = [wintypes.POINT]
_WindowFromPoint.restype = wintypes.HWND

_GetWindowTextW = _user32.GetWindowTextW
_GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

_GetWindowTextLengthW = _user32.GetWindowTextLengthW
_GetWindowTextLengthW.argtypes = [wintypes.HWND]
_GetWindowTextLengthW.restype = ctypes.c_int

_GetClassNameW = _user32.GetClassNameW
_GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

_GetWindowRect = _user32.GetWindowRect
_GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_GetWindowRect.restype = wintypes.BOOL

_GetParent = _user32.GetParent
_GetParent.argtypes = [wintypes.HWND]
_GetParent.restype = wintypes.HWND

_GetWindowDC = _user32.GetWindowDC
_GetWindowDC.argtypes = [wintypes.HWND]
_GetWindowDC.restype = wintypes.HDC

_ReleaseDC = _user32.ReleaseDC
_ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_ReleaseDC.restype = ctypes.c_int

_CreatePen = _gdi32.CreatePen
_CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.COLORREF]
_CreatePen.restype = wintypes.HANDLE

_SelectObject = _gdi32.SelectObject
_SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
_SelectObject.restype = wintypes.HANDLE

_Rectangle = _gdi32.Rectangle
_Rectangle.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
_Rectangle.restype = wintypes.BOOL

_DeleteObject = _gdi32.DeleteObject
_DeleteObject.argtypes = [wintypes.HANDLE]
_DeleteObject.restype = wintypes.BOOL

_SetROP2 = _gdi32.SetROP2
_SetROP2.argtypes = [wintypes.HDC, ctypes.c_int]
_SetROP2.restype = ctypes.c_int

_GetSystemMetrics = _user32.GetSystemMetrics
_GetSystemMetrics.argtypes = [ctypes.c_int]
_GetSystemMetrics.restype = ctypes.c_int


@dataclass
class ElementInfo:
    """捕获到的元素统一数据结构。"""
    name: str = ""
    element_type: str = "win32"  # "win32" | "uia" | "web"
    class_name: str = ""
    title: str = ""
    rect: dict = field(default_factory=dict)
    hwnd: int = 0
    # UIA
    control_type: str = ""
    automation_id: str = ""
    uia_path: list = field(default_factory=list)
    # Web
    css_selector: str = ""
    xpath: str = ""
    tag_name: str = ""
    # 完整祖先链
    win32_path: list = field(default_factory=list)


def _get_window_text(hwnd) -> str:
    length = _GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _get_class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _GetClassNameW(hwnd, buf, 256)
    return buf.value


def _get_window_rect(hwnd) -> dict:
    rect = wintypes.RECT()
    _GetWindowRect(hwnd, ctypes.byref(rect))
    return {
        "left": rect.left, "top": rect.top,
        "right": rect.right, "bottom": rect.bottom,
        "width": rect.right - rect.left,
        "height": rect.bottom - rect.top,
    }


def _get_ancestor_path(hwnd) -> list:
    """从目标控件向上追溯到顶层窗口。"""
    path = []
    cur = hwnd
    visited = set()
    while cur:
        if cur in visited:
            break
        visited.add(cur)
        info = {
            "hwnd": cur,
            "class_name": _get_class_name(cur),
            "title": _get_window_text(cur),
            "rect": _get_window_rect(cur),
        }
        path.insert(0, info)
        parent = _GetParent(cur)
        if not parent:
            break
        cur = parent
    return path


def _is_browser_window(class_name: str) -> bool:
    """检测窗口是否是浏览器（Chrome/Edge）。"""
    browser_classes = (
        "Chrome_WidgetWin_1",
        "MozillaWindowClass",
        "CASCADIA_HOSTING_WINDOW_CLASS",
    )
    return any(c in class_name for c in browser_classes)


def _try_uia_capture(x: int, y: int) -> dict | None:
    """尝试 UIA 捕获。失败返回 None。"""
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pass

    try:
        import uiautomation as uia

        ctrl = uia.ControlFromPoint(x, y)
        if not ctrl:
            return None

        chain = []
        cur = ctrl
        visited = set()
        while cur:
            rid = id(cur)
            if rid in visited:
                break
            visited.add(rid)
            try:
                br = cur.BoundingRectangle
            except Exception:
                br = None
            chain.insert(0, {
                "name": cur.Name or "",
                "class_name": cur.ClassName or "",
                "control_type": cur.ControlTypeName or "",
                "automation_id": cur.AutomationId or "",
                "rect": {
                    "left": br.left, "top": br.top,
                    "right": br.right, "bottom": br.bottom,
                    "width": br.width() if br else 0,
                    "height": br.height() if br else 0,
                } if br else {},
            })
            try:
                p = cur.GetParentControl()
                if not p or p.ControlTypeName == "DesktopControl":
                    break
                cur = p
            except Exception:
                break

        leaf = chain[-1] if chain else {}
        return {
            "found": True,
            "name": leaf.get("name", ""),
            "class_name": leaf.get("class_name", ""),
            "control_type": leaf.get("control_type", ""),
            "automation_id": leaf.get("automation_id", ""),
            "rect": leaf.get("rect", {}),
            "path": chain,
        }
    except Exception:
        return None
    finally:
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass


def draw_highlight(hwnd, color=0x0000FF):
    """XOR 绘制/擦除目标控件的边框（在桌面 DC 上）。"""
    try:
        rect = wintypes.RECT()
        if not _GetWindowRect(hwnd, ctypes.byref(rect)):
            return
        hdc = _GetWindowDC(0)
        pen = _CreatePen(PS_SOLID, 3, color)
        old_pen = _SelectObject(hdc, pen)
        old_rop = _SetROP2(hdc, R2_NOTXORPEN)
        _Rectangle(hdc, rect.left, rect.top, rect.right, rect.bottom)
        _SetROP2(hdc, old_rop)
        _SelectObject(hdc, old_pen)
        _DeleteObject(pen)
        _ReleaseDC(0, hdc)
    except Exception:
        pass


def draw_highlight_rect(rect: dict, color=0x00FF00):
    """在屏幕坐标上 XOR 绘制/擦除矩形。"""
    try:
        hdc = _GetWindowDC(0)
        pen = _CreatePen(PS_SOLID, 3, color)
        old_pen = _SelectObject(hdc, pen)
        old_rop = _SetROP2(hdc, R2_NOTXORPEN)
        _Rectangle(hdc, rect["left"], rect["top"], rect["right"], rect["bottom"])
        _SetROP2(hdc, old_rop)
        _SelectObject(hdc, old_pen)
        _DeleteObject(pen)
        _ReleaseDC(0, hdc)
    except Exception:
        pass


def flash_element(element: ElementInfo, times=3, color_good=0x00FF00, color_bad=0x0000FF):
    """闪烁元素边框：找到=绿色，没找到=红色。返回是否找到。"""
    found = _validate_and_flash(element, times, color_good, color_bad)
    return found


def _validate_and_flash(element: ElementInfo, times: int, color_good: int, color_bad: int) -> bool:
    """反向查找元素并闪烁。"""
    hwnd = _find_element_hwnd(element)
    rect = element.rect if element.rect else None

    if not hwnd and not rect:
        return False

    if hwnd and not rect:
        rect = _get_window_rect(hwnd)

    if not rect or not rect.get("width"):
        return False

    color = color_good if hwnd else color_bad
    for _ in range(times):
        if hwnd:
            draw_highlight(hwnd, color)
        else:
            draw_highlight_rect(rect, color)
        time.sleep(0.2)
        if hwnd:
            draw_highlight(hwnd, color)
        else:
            draw_highlight_rect(rect, color)
        time.sleep(0.2)

    return hwnd is not None


def _find_element_hwnd(element: ElementInfo) -> int | None:
    """根据 element 的 win32_path 反向查找控件。"""
    path = element.win32_path
    if not path:
        return None

    # 从路径第一层（顶层窗口）开始逐层匹配
    top = path[0]
    hwnd = _find_top_window(top)

    if not hwnd:
        return None
    if len(path) == 1:
        return hwnd

    # 穿透子控件
    from scripts.capture_gui.win32_utils import find_child_window
    for level in path[1:]:
        child = find_child_window(
            hwnd,
            class_name=level.get("class_name", ""),
            title=level.get("title", ""),
        )
        if not child:
            return None
        hwnd = child
    return hwnd


def _find_top_window(info: dict) -> int | None:
    """根据 path 第一层信息查找顶层窗口。"""
    from scripts.capture_gui.win32_utils import find_window, find_window_by_title_fuzzy

    title = info.get("title", "")
    cls = info.get("class_name", "")

    if title:
        matches = find_window_by_title_fuzzy(title)
        if matches:
            return matches[0]["hwnd"]
        h = find_window(title=title)
        if h:
            return h
    if cls:
        h = find_window(class_name=cls)
        if h:
            return h
    return None


def run_capture() -> ElementInfo | None:
    """进入捕获模式。阻塞直到用户点击或取消。返回元素信息或 None。

    由 tkinter 主线程调用（会短暂隐藏 tkinter 窗口）。
    """
    screen_w = _GetSystemMetrics(SM_CXSCREEN)
    screen_h = _GetSystemMetrics(SM_CYSCREEN)
    pt = wintypes.POINT()
    last_highlight_hwnd = None
    captured: ElementInfo | None = None

    print("[Capture] 移动鼠标到目标上，左键捕获，右键/Esc 取消...")

    try:
        while True:
            # 退出键
            if _GetAsyncKeyState(VK_ESCAPE) & 0x8000:
                print("[Capture] 已取消 (Esc)")
                break
            if _GetAsyncKeyState(VK_RBUTTON) & 0x8000:
                print("[Capture] 已取消 (右键)")
                break

            _GetCursorPos(ctypes.byref(pt))

            # 边界检查（多显示器时可能出现负坐标）
            if 0 <= pt.x < screen_w * 2 and -screen_h < pt.y < screen_h * 2:
                target = _WindowFromPoint(pt)
            else:
                target = None

            # 高亮切换
            if target and target != last_highlight_hwnd:
                if last_highlight_hwnd:
                    draw_highlight(last_highlight_hwnd)
                draw_highlight(target)
                last_highlight_hwnd = target

            # 左键捕获
            if (_GetAsyncKeyState(VK_LBUTTON) & 0x8000) and target:
                # 清除高亮
                if last_highlight_hwnd:
                    draw_highlight(last_highlight_hwnd)
                time.sleep(0.1)  # 等鼠标释放

                info = _build_element_info(target, pt.x, pt.y)
                captured = info
                print(f"[Capture] 捕获: {info.element_type} \"{info.name or info.class_name}\"")
                break

            time.sleep(0.03)

    finally:
        if last_highlight_hwnd:
            draw_highlight(last_highlight_hwnd)

    return captured


def _build_element_info(hwnd, x: int, y: int) -> ElementInfo:
    """收集 Win32 + UIA 信息，构建 ElementInfo。"""
    class_name = _get_class_name(hwnd)
    title = _get_window_text(hwnd)
    rect = _get_window_rect(hwnd)
    win32_path = _get_ancestor_path(hwnd)

    info = ElementInfo(
        name=title or class_name,
        element_type="win32",
        class_name=class_name,
        title=title,
        rect=rect,
        hwnd=hwnd,
        win32_path=win32_path,
    )

    # 浏览器窗口 → 标记为 web
    if _is_browser_window(class_name):
        info.element_type = "web"

    # UIA 捕获
    uia_result = _try_uia_capture(x, y)
    if uia_result:
        info.control_type = uia_result.get("control_type", "")
        info.automation_id = uia_result.get("automation_id", "")
        info.uia_path = uia_result.get("path", [])
        if not info.name:
            info.name = uia_result.get("name", "")
        # 如果是浏览器内的 DOM 元素，UIA 会给更细的类型
        if info.element_type == "web" and info.control_type in (
            "EditControl", "ButtonControl", "HyperlinkControl",
            "TextControl", "ComboBoxControl", "CheckBoxControl",
            "ListItemControl", "TreeItemControl", "MenuBarControl",
        ):
            info.name = uia_result.get("name") or title

    # 浏览器窗口里的元素 → 标记 web
    is_browser_child = _is_browser_in_chain(win32_path)
    if is_browser_child and info.element_type != "web":
        info.element_type = "web"

    return info


def _is_browser_in_chain(path: list) -> bool:
    """检查祖先链中是否包含浏览器窗口。"""
    for p in path:
        if _is_browser_window(p.get("class_name", "")):
            return True
    return False
