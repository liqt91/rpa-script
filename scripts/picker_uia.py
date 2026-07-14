"""UIA 控件拾取器 — picker_uia.py

混合方案：Win32 快速高亮 + UIA 深度捕获。
高亮用 WindowFromPoint（即时），捕获时用 UIA ControlFromPoint（仅一次COM调用）。
"""
import sys
import json
import time
import ctypes
import ctypes.wintypes as wintypes

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_kernel32 = ctypes.windll.kernel32

WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_POPUP = 0x80000000
R2_XOR = 6; PS_SOLID = 0
VK_MENU = 0x12; VK_LBUTTON = 0x01; VK_ESCAPE = 0x1B

class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT), ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HICON), ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
    ]

# Win32 API 类型声明
_GetDC = _user32.GetDC; _GetDC.argtypes = [wintypes.HWND]; _GetDC.restype = wintypes.HDC
_ReleaseDC = _user32.ReleaseDC
_ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]; _ReleaseDC.restype = ctypes.c_int
_GetCursorPos = _user32.GetCursorPos
_GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
_GetAsyncKeyState = _user32.GetAsyncKeyState
_GetAsyncKeyState.argtypes = [ctypes.c_int]; _GetAsyncKeyState.restype = ctypes.c_short
_WindowFromPoint = _user32.WindowFromPoint
_WindowFromPoint.argtypes = [wintypes.POINT]; _WindowFromPoint.restype = wintypes.HWND
_GetWindowRect = _user32.GetWindowRect
_GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]; _GetWindowRect.restype = wintypes.BOOL
_SetROP2 = _gdi32.SetROP2
_SetROP2.argtypes = [wintypes.HDC, ctypes.c_int]; _SetROP2.restype = ctypes.c_int
_CreatePen = _gdi32.CreatePen
_CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.COLORREF]; _CreatePen.restype = wintypes.HANDLE
_SelectObject = _gdi32.SelectObject
_SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]; _SelectObject.restype = wintypes.HANDLE
_GetStockObject = _gdi32.GetStockObject
_GetStockObject.argtypes = [ctypes.c_int]; _GetStockObject.restype = wintypes.HANDLE
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


def draw_xor(hdc, r):
    _SetROP2(hdc, R2_XOR)
    pen = _CreatePen(PS_SOLID, 3, 0x0000FF)
    op = _SelectObject(hdc, pen)
    ob = _SelectObject(hdc, _GetStockObject(5))
    _Rectangle(hdc, r.left, r.top, r.right, r.bottom)
    _SelectObject(hdc, ob); _SelectObject(hdc, op)
    _SetROP2(hdc, R2_XOR); _DeleteObject(pen)


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

    print("UIA: Alt+Click=Capture  Esc=Cancel", file=sys.stderr)
    sys.stderr.write("\033[?25l"); sys.stderr.flush()

    hInst = _kernel32.GetModuleHandleW(None)
    wc = WNDCLASSW()
    wc.lpfnWndProc = ctypes.cast(_user32.DefWindowProcW, ctypes.c_void_p)
    wc.hInstance = hInst; wc.lpszClassName = "UiaPicker"
    _user32.RegisterClassW(ctypes.byref(wc))
    sw, sh = _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)
    hwnd = _user32.CreateWindowExW(
        WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST,
        "UiaPicker", "", WS_POPUP, 0, 0, sw, sh,
        None, None, hInst, None)
    _user32.SetLayeredWindowAttributes(hwnd, 0, 1, 0x02)
    _user32.ShowWindow(hwnd, 1)

    hdc = _GetDC(hwnd)
    pt = wintypes.POINT()
    prev_rect = wintypes.RECT()
    prev_valid = False
    alt_was = False
    result = {"cancelled": True}

    try:
        while True:
            if _GetAsyncKeyState(VK_ESCAPE) & 0x8000: break
            is_alt = bool(_GetAsyncKeyState(VK_MENU) & 0x8000)
            _GetCursorPos(ctypes.byref(pt))

            # Win32 快速获取鼠标下的窗口矩形
            h = _WindowFromPoint(pt)
            r = wintypes.RECT()
            if h and _GetWindowRect(h, ctypes.byref(r)):
                # 擦旧画新
                if prev_valid: draw_xor(hdc, prev_rect)
                draw_xor(hdc, r)
                prev_rect = r; prev_valid = True

                if alt_was and not is_alt and (_GetAsyncKeyState(VK_LBUTTON) & 0x8000):
                    chain = uia_capture(pt.x, pt.y)
                    if chain:
                        t = chain[-1]
                        result = {"cancelled": False, "name": t.get("name",""),
                                  "class_name": t.get("class_name",""),
                                  "control_type": t.get("control_type",""),
                                  "automation_id": t.get("automation_id",""),
                                  "rect": t.get("rect",{}), "path": chain}
                    break
            else:
                if prev_valid:
                    draw_xor(hdc, prev_rect)
                    prev_valid = False

            alt_was = is_alt
            time.sleep(0.04)

    finally:
        if prev_valid: draw_xor(hdc, prev_rect)
        _ReleaseDC(hwnd, hdc)
        _user32.DestroyWindow(hwnd)
        sys.stderr.write("\033[?25h"); sys.stderr.flush()

    return result


if __name__ == "__main__":
    r = run_picker()
    try: print(json.dumps(r, ensure_ascii=False, default=lambda o: str(o)[:200]))
    except Exception as e: print(json.dumps({"error": str(e)}, ensure_ascii=False))
