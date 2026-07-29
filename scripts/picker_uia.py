"""UIA 控件拾取器 — picker_uia.py

混合方案：Win32 快速高亮 + UIA 深度捕获。
高亮直接在桌面 DC 绘制（不创建覆盖层窗口），捕获时用 UIA ControlFromPoint。
"""
import sys
import json
import time
import ctypes
import ctypes.wintypes as wintypes

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_kernel32 = ctypes.windll.kernel32

R2_NOTXORPEN = 10
PS_SOLID = 0
VK_MENU = 0x12; VK_LBUTTON = 0x01; VK_ESCAPE = 0x1B; VK_RBUTTON = 0x02

# Win32 API 类型声明
_GetCursorPos = _user32.GetCursorPos
_GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
_GetAsyncKeyState = _user32.GetAsyncKeyState
_GetAsyncKeyState.argtypes = [ctypes.c_int]; _GetAsyncKeyState.restype = ctypes.c_short
_WindowFromPoint = _user32.WindowFromPoint
_WindowFromPoint.argtypes = [wintypes.POINT]; _WindowFromPoint.restype = wintypes.HWND
_GetWindowRect = _user32.GetWindowRect
_GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]; _GetWindowRect.restype = wintypes.BOOL
_GetWindowDC = _user32.GetWindowDC
_GetWindowDC.argtypes = [wintypes.HWND]; _GetWindowDC.restype = wintypes.HDC
_ReleaseDC = _user32.ReleaseDC
_ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]; _ReleaseDC.restype = ctypes.c_int
_SetROP2 = _gdi32.SetROP2
_SetROP2.argtypes = [wintypes.HDC, ctypes.c_int]; _SetROP2.restype = ctypes.c_int
_CreatePen = _gdi32.CreatePen
_CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.COLORREF]; _CreatePen.restype = wintypes.HANDLE
_SelectObject = _gdi32.SelectObject
_SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]; _SelectObject.restype = wintypes.HANDLE
_Rectangle = _gdi32.Rectangle
_Rectangle.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
_Rectangle.restype = wintypes.BOOL
_DeleteObject = _gdi32.DeleteObject
_DeleteObject.argtypes = [wintypes.HANDLE]; _DeleteObject.restype = wintypes.BOOL

try: ctypes.windll.ole32.CoInitializeEx(None, 2)
except Exception: pass

UIA_AVAILABLE = False
try:
    import uiautomation as uia
    UIA_AVAILABLE = True
except ImportError: pass


def draw_highlight(hwnd):
    """用 XOR 画笔在目标控件外绘制高亮框（直接在桌面 DC）。"""
    try:
        rect = wintypes.RECT()
        _GetWindowRect(hwnd, ctypes.byref(rect))
        hdc = _GetWindowDC(0)  # desktop DC
        pen = _CreatePen(PS_SOLID, 3, 0x0000FF)
        old_pen = _SelectObject(hdc, pen)
        old_rop = _SetROP2(hdc, R2_NOTXORPEN)
        _Rectangle(hdc, rect.left, rect.top, rect.right, rect.bottom)
        _SetROP2(hdc, old_rop)
        _SelectObject(hdc, old_pen)
        _DeleteObject(pen)
        _ReleaseDC(0, hdc)
    except Exception:
        pass


def uia_capture(x, y):
    """仅在 Alt+Click 时调用一次 UIA。"""
    import pythoncom
    pythoncom.CoInitialize()
    try:
        ctrl = uia.ControlFromPoint(x, y)
        if not ctrl: return None
        chain = []
        cur = ctrl; visited = set()
        while cur:
            rid = id(cur)
            if rid in visited: break
            visited.add(rid)
            try: br = cur.BoundingRectangle
            except Exception: br = None
            chain.insert(0, {
                "name": cur.Name or "",
                "class_name": cur.ClassName or "",
                "control_type": cur.ControlTypeName or "",
                "automation_id": cur.AutomationId or "",
                "rect": {"left": br.left, "top": br.top, "right": br.right, "bottom": br.bottom,
                         "width": br.width(), "height": br.height()} if br else {},
            })
            try:
                p = cur.GetParentControl()
                if not p or p.ControlTypeName == "DesktopControl": break
                cur = p
            except Exception: break
        return chain
    except Exception: return None
    finally: pythoncom.CoUninitialize()


def run_picker():
    if not UIA_AVAILABLE:
        return {"error": "uiautomation not installed. pip install uiautomation"}

    print("UIA: Alt+Click=Capture  RightClick/Esc=Cancel", file=sys.stderr)
    sys.stderr.write("\033[?25l"); sys.stderr.flush()

    pt = wintypes.POINT()
    last_highlight = None
    result = {"cancelled": True}

    try:
        while True:
            # 检查退出
            if _GetAsyncKeyState(VK_ESCAPE) & 0x8000: break
            if _GetAsyncKeyState(VK_RBUTTON) & 0x8000: break

            _GetCursorPos(ctypes.byref(pt))
            target = _WindowFromPoint(pt)

            # 高亮目标窗口
            if target and target != last_highlight:
                if last_highlight:
                    draw_highlight(last_highlight)
                draw_highlight(target)
                last_highlight = target

            # Alt+左键捕获
            if (_GetAsyncKeyState(VK_LBUTTON) & 0x8000) and (_GetAsyncKeyState(VK_MENU) & 0x8000):
                if target:
                    if last_highlight:
                        draw_highlight(last_highlight)
                    time.sleep(0.1)  # 等鼠标释放
                    chain = uia_capture(pt.x, pt.y)
                    if chain:
                        t = chain[-1]
                        result = {"cancelled": False, "name": t.get("name", ""),
                                  "class_name": t.get("class_name", ""),
                                  "control_type": t.get("control_type", ""),
                                  "automation_id": t.get("automation_id", ""),
                                  "rect": t.get("rect", {}), "path": chain}
                    break

            time.sleep(0.03)

    finally:
        if last_highlight:
            draw_highlight(last_highlight)
        sys.stderr.write("\033[?25h"); sys.stderr.flush()

    return result


if __name__ == "__main__":
    r = run_picker()
    try: print(json.dumps(r, ensure_ascii=False, default=lambda o: str(o)[:200]))
    except Exception as e: print(json.dumps({"error": str(e)}, ensure_ascii=False))
