"""控件拾取器 — 类似 Spy++ 的十字光标捕获工具。

用法:
    python scripts/picker.py              # 输出 JSON
    python scripts/picker.py --compact    # 紧凑 JSON（单行）

工作流程:
    1. 鼠标变为十字光标
    2. 移动鼠标实时高亮目标控件（红色边框）
    3. 左键点击 → 输出控件信息 JSON → 退出
    4. 右键 / Esc → 取消退出

输出格式:
{
    "hwnd": 12345,
    "title": "确定",
    "class_name": "Button",
    "rect": {"left": 100, "top": 200, "right": 180, "bottom": 224, ...},
    "path": [
        {"hwnd": ..., "class_name": "#32770", "title": "打开"},
        {"hwnd": ..., "class_name": "Button", "title": "确定"}
    ]
}
"""
import ctypes
from ctypes import wintypes
import sys
import json
import time

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32

# ── Window APIs ──
_GetCursorPos = _user32.GetCursorPos
_GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]

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

_GetParent = _user32.GetParent
_GetParent.argtypes = [wintypes.HWND]
_GetParent.restype = wintypes.HWND

_ScreenToClient = _user32.ScreenToClient
_ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]

_GetWindowDC = _user32.GetWindowDC
_GetWindowDC.argtypes = [wintypes.HWND]
_GetWindowDC.restype = wintypes.HDC

_ReleaseDC = _user32.ReleaseDC
_ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]

_GetSystemMetrics = _user32.GetSystemMetrics
_GetSystemMetrics.argtypes = [ctypes.c_int]
_GetSystemMetrics.restype = ctypes.c_int

_GetKeyState = _user32.GetKeyState
_GetKeyState.argtypes = [ctypes.c_int]
_GetKeyState.restype = ctypes.c_short

_SetCapture = _user32.SetCapture
_SetCapture.argtypes = [wintypes.HWND]

_ReleaseCapture = _user32.ReleaseCapture

_InvalidateRect = _user32.InvalidateRect
_InvalidateRect.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]

_GetDesktopWindow = _user32.GetDesktopWindow
_GetDesktopWindow.restype = wintypes.HWND

# ── GDI 🔁 ──
_PatBlt = _gdi32.PatBlt
_PatBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]

_CreatePen = _gdi32.CreatePen
_CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint]
_CreatePen.restype = wintypes.HGDIOBJ

_SelectObject = _gdi32.SelectObject
_SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_SelectObject.restype = wintypes.HGDIOBJ

_DeleteObject = _gdi32.DeleteObject
_DeleteObject.argtypes = [wintypes.HGDIOBJ]

_Rectangle = _gdi32.Rectangle
_Rectangle.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]

_SetROP2 = _gdi32.SetROP2
_SetROP2.argtypes = [wintypes.HDC, ctypes.c_int]
_SetROP2.restype = ctypes.c_int

# Constants
SM_CXSCREEN = 0
SM_CYSCREEN = 1
R2_NOTXORPEN = 10
PS_SOLID = 0
PATINVERT = 0x005A0049
VK_ESCAPE = 0x1B
VK_RBUTTON = 0x02
VK_MENU = 0x12  # Alt
VK_LBUTTON = 0x01
WHITE_BRUSH = 0

# ── Helpers ──
def get_window_text(hwnd):
    length = _GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _GetWindowTextW(hwnd, buf, length + 1)
    return buf.value

def get_class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    _GetClassNameW(hwnd, buf, 256)
    return buf.value

def get_window_rect(hwnd):
    rect = wintypes.RECT()
    _GetWindowRect(hwnd, ctypes.byref(rect))
    return {
        "left": rect.left, "top": rect.top,
        "right": rect.right, "bottom": rect.bottom,
        "width": rect.right - rect.left,
        "height": rect.bottom - rect.top,
    }

def get_ancestor_path(hwnd):
    """从目标控件向上追溯到顶层窗口，返回路径列表。"""
    path = []
    cur = hwnd
    while cur:
        info = {
            "hwnd": cur,
            "class_name": get_class_name(cur),
            "title": get_window_text(cur),
            "rect": get_window_rect(cur),
        }
        path.insert(0, info)
        parent = _GetParent(cur)
        if not parent:
            break
        cur = parent
    return path

def draw_highlight(hwnd, color=0x0000FF):
    """用 XOR 画笔在目标控件外绘制高亮框。"""
    try:
        rect = wintypes.RECT()
        _GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top

        hdc = _GetWindowDC(0)  # desktop DC
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

# ── Main picker loop ──
def pick() -> dict | None:
    """进入控件拾取模式，返回捕获的控件信息，取消返回 None。"""

    print("🔍 控件拾取器：移动鼠标选择控件，Alt+左键捕获，右键/Esc 取消", file=sys.stderr)
    print("    移动鼠标到目标控件上，Alt+左键捕获，右键/Esc 取消...", file=sys.stderr)

    last_highlight_hwnd = None
    captured = None

    while True:
        # 检查退出键
        if _GetKeyState(VK_ESCAPE) & 0x8000:
            print("\n    ⏹ 已取消 (Esc)", file=sys.stderr)
            break
        if _GetKeyState(VK_RBUTTON) & 0x8000:
            print("\n    ⏹ 已取消 (右键)", file=sys.stderr)
            break

        # 获取鼠标位置
        pt = wintypes.POINT()
        _GetCursorPos(ctypes.byref(pt))
        target = _WindowFromPoint(pt)

        # 转为客户区坐标的高亮目标
        if target and target != last_highlight_hwnd:
            # 清除旧高亮
            if last_highlight_hwnd:
                draw_highlight(last_highlight_hwnd)
            # 绘制新高亮
            draw_highlight(target)
            last_highlight_hwnd = target
            title = get_window_text(target)
            cls = get_class_name(target)
            r = get_window_rect(target)
            print(f"    {cls} \"{title}\" [{r['width']}x{r['height']}]  ", end="\r", file=sys.stderr)

        # Alt+左键捕获
        if (_GetKeyState(VK_LBUTTON) & 0x8000) and (_GetKeyState(VK_MENU) & 0x8000):
            if target:
                # 清除高亮
                if last_highlight_hwnd:
                    draw_highlight(last_highlight_hwnd)
                # 短暂延迟等鼠标释放
                time.sleep(0.1)
                captured = target
                print(f"\n    ✅ 捕获: {get_class_name(target)} \"{get_window_text(target)}\"", file=sys.stderr)
                break

        time.sleep(0.03)

    # 清理可能残留的高亮
    if last_highlight_hwnd:
        draw_highlight(last_highlight_hwnd)

    if captured is None:
        return None

    return {
        "hwnd": captured,
        "title": get_window_text(captured),
        "class_name": get_class_name(captured),
        "rect": get_window_rect(captured),
        "path": get_ancestor_path(captured),
    }


if __name__ == "__main__":
    compact = "--compact" in sys.argv
    result = pick()
    if result:
        indent = None if compact else 2
        print(json.dumps(result, ensure_ascii=False, indent=indent))
    else:
        print(json.dumps({"cancelled": True}))
