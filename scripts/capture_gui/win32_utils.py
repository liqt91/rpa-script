"""Win32 窗口查找工具 — 轻量级，供 overlay 和 validator 使用。"""

import ctypes
import ctypes.wintypes as wintypes

_user32 = ctypes.windll.user32

_FindWindowW = _user32.FindWindowW
_FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_FindWindowW.restype = wintypes.HWND

_FindWindowExW = _user32.FindWindowExW
_FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
_FindWindowExW.restype = wintypes.HWND

_EnumWindows = _user32.EnumWindows
_EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]

_GetWindowTextW = _user32.GetWindowTextW
_GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

_GetWindowTextLengthW = _user32.GetWindowTextLengthW
_GetWindowTextLengthW.argtypes = [wintypes.HWND]
_GetWindowTextLengthW.restype = ctypes.c_int

_GetClassNameW = _user32.GetClassNameW
_GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

_IsWindowVisible = _user32.IsWindowVisible
_IsWindowVisible.argtypes = [wintypes.HWND]
_IsWindowVisible.restype = wintypes.BOOL


def find_window(title: str = "", class_name: str = "") -> int | None:
    """查找顶层窗口。"""
    hwnd = _FindWindowW(class_name or None, title or None)
    return hwnd if hwnd else None


def find_child_window(parent: int, class_name: str = "", title: str = "") -> int | None:
    """在父窗口中查找子控件。"""
    hwnd = _FindWindowExW(parent, None, class_name or None, title or None)
    return hwnd if hwnd else None


def find_window_by_title_fuzzy(title: str) -> list[dict]:
    """模糊标题匹配，返回所有匹配的可见窗口 [{hwnd, title, class_name}]。"""
    results = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd, _lparam):
        if not _IsWindowVisible(hwnd):
            return True
        length = _GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _GetWindowTextW(hwnd, buf, length + 1)
        if title.lower() in buf.value.lower():
            cls_buf = ctypes.create_unicode_buffer(256)
            _GetClassNameW(hwnd, cls_buf, 256)
            results.append({
                "hwnd": hwnd,
                "title": buf.value,
                "class_name": cls_buf.value,
            })
        return True

    _EnumWindows(enum_proc, 0)
    return results
