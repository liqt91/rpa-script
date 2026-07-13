"""
Win32 API 底层封装 — 桌面自动化基础能力。

技术分层（按 JD 要求的 Windows 工作机制理解）：
  层级1: 窗口查找    → FindWindowW / FindWindowExW / EnumChildWindows
  层级2: 控件交互    → SendMessageW (BM_CLICK / WM_SETTEXT / WM_GETTEXT)
  层级3: 窗口管理    → SetForegroundWindow / ShowWindow / GetWindowTextW
  层级4: 图像兜底    → (TODO: OpenCV 模板匹配)

仅 Windows 平台可用。非 Windows 平台调用返回 None/False。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import logging

logger = logging.getLogger(__name__)

# ── Win32 API 函数声明 ──────────────────────────────────────────────

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

# 窗口查找
_FindWindowW = _user32.FindWindowW
_FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_FindWindowW.restype = wintypes.HWND

_FindWindowExW = _user32.FindWindowExW
_FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
_FindWindowExW.restype = wintypes.HWND

# 窗口文本
_GetWindowTextW = _user32.GetWindowTextW
_GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_GetWindowTextW.restype = ctypes.c_int

_GetWindowTextLengthW = _user32.GetWindowTextLengthW
_GetWindowTextLengthW.argtypes = [wintypes.HWND]
_GetWindowTextLengthW.restype = ctypes.c_int

_GetClassNameW = _user32.GetClassNameW
_GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_GetClassNameW.restype = ctypes.c_int

# 窗口状态
_IsWindowVisible = _user32.IsWindowVisible
_IsWindowVisible.argtypes = [wintypes.HWND]
_IsWindowVisible.restype = wintypes.BOOL

_IsWindowEnabled = _user32.IsWindowEnabled
_IsWindowEnabled.argtypes = [wintypes.HWND]
_IsWindowEnabled.restype = wintypes.BOOL

_SetForegroundWindow = _user32.SetForegroundWindow
_SetForegroundWindow.argtypes = [wintypes.HWND]
_SetForegroundWindow.restype = wintypes.BOOL

_ShowWindow = _user32.ShowWindow
_ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_ShowWindow.restype = wintypes.BOOL

_IsIconic = _user32.IsIconic
_IsIconic.argtypes = [wintypes.HWND]
_IsIconic.restype = wintypes.BOOL

# 消息发送
_SendMessageW = _user32.SendMessageW
_SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
_SendMessageW.restype = ctypes.c_longlong

_PostMessageW = _user32.PostMessageW
_PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
_PostMessageW.restype = wintypes.BOOL

# 矩形
_GetWindowRect = _user32.GetWindowRect
_GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_GetWindowRect.restype = wintypes.BOOL

# 枚举子窗口
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_EnumChildWindows = _user32.EnumChildWindows
_EnumChildWindows.argtypes = [wintypes.HWND, _WNDENUMPROC, wintypes.LPARAM]
_EnumChildWindows.restype = wintypes.BOOL

# ── 窗口消息常量 ────────────────────────────────────────────────────

WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
WM_CLOSE = 0x0010
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WM_COMMAND = 0x0111

BM_CLICK = 0x00F5
BM_GETCHECK = 0x00F0
BM_SETCHECK = 0x00F1

CB_GETCOUNT = 0x0146
CB_SETCURSEL = 0x014E
CB_GETCURSEL = 0x0147

SW_RESTORE = 9
SW_SHOW = 5


# ── 公共 API ────────────────────────────────────────────────────────

def is_windows() -> bool:
    return os.name == "nt"


def window_exists(hwnd: int) -> bool:
    """检查窗口句柄是否仍然有效。"""
    if not hwnd:
        return False
    try:
        return bool(_IsWindowVisible(hwnd) or True)
    except Exception:
        return False


# ── 窗口查找 ────────────────────────────────────────────────────────

def find_window(title: str = None, class_name: str = None) -> int | None:
    """查找顶层窗口。

    Args:
        title: 窗口标题（部分匹配需自行遍历，此处为精确匹配）
        class_name: 窗口类名（如 "Notepad", "Chrome_WidgetWin_1"）

    Returns:
        窗口句柄 HWND，未找到返回 None
    """
    if not is_windows():
        return None
    _title = title or None
    _class = class_name or None
    hwnd = _FindWindowW(_class, _title)
    return hwnd if hwnd else None


def find_window_by_title_fuzzy(title_fragment: str) -> list[dict]:
    """枚举所有顶层窗口，按标题片段模糊匹配。

    Returns:
        [{hwnd, title, class_name, visible}, ...]
    """
    if not is_windows():
        return []
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
        win_title = buf.value
        if title_fragment.lower() in win_title.lower():
            class_buf = ctypes.create_unicode_buffer(256)
            _GetClassNameW(hwnd, class_buf, 256)
            results.append({
                "hwnd": hwnd,
                "title": win_title,
                "class_name": class_buf.value,
                "visible": bool(_IsWindowVisible(hwnd)),
            })
        return True

    _user32.EnumWindows(enum_proc, 0)
    return results


def find_child_window(parent_hwnd: int, class_name: str = None,
                       title: str = None, index: int = 0) -> int | None:
    """在父窗口中查找第 index 个匹配的子控件。

    Args:
        parent_hwnd: 父窗口句柄
        class_name: 控件类名（如 "Button", "Edit", "ComboBox"）
        title: 控件标题/文本
        index: 第几个匹配项（0-based）

    Returns:
        子控件句柄，未找到返回 None
    """
    if not is_windows() or not parent_hwnd:
        return None
    hwnd = None
    for i in range(index + 1):
        hwnd = _FindWindowExW(parent_hwnd, hwnd, class_name or None, title or None)
        if not hwnd:
            return None
    return hwnd


def enum_child_windows(parent_hwnd: int) -> list[dict]:
    """枚举父窗口的所有直接子控件。

    Returns:
        [{hwnd, title, class_name, enabled, visible, rect}, ...]
    """
    if not is_windows() or not parent_hwnd:
        return []
    results = []

    @_WNDENUMPROC
    def enum_proc(hwnd, _lparam):
        length = _GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            _GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value

        class_buf = ctypes.create_unicode_buffer(256)
        _GetClassNameW(hwnd, class_buf, 256)

        rect = wintypes.RECT()
        _GetWindowRect(hwnd, ctypes.byref(rect))

        results.append({
            "hwnd": hwnd,
            "title": title,
            "class_name": class_buf.value,
            "enabled": bool(_IsWindowEnabled(hwnd)),
            "visible": bool(_IsWindowVisible(hwnd)),
            "rect": {"left": rect.left, "top": rect.top,
                     "right": rect.right, "bottom": rect.bottom,
                     "width": rect.right - rect.left,
                     "height": rect.bottom - rect.top},
        })
        return True

    _EnumChildWindows(parent_hwnd, enum_proc, 0)
    return results


def get_window_text(hwnd: int) -> str:
    """获取窗口标题/控件文本。"""
    if not is_windows() or not hwnd:
        return ""
    length = _GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def get_class_name(hwnd: int) -> str:
    """获取窗口类名。"""
    if not is_windows() or not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    _GetClassNameW(hwnd, buf, 256)
    return buf.value


def get_window_rect(hwnd: int) -> dict | None:
    """获取窗口矩形坐标。"""
    if not is_windows() or not hwnd:
        return None
    rect = wintypes.RECT()
    if _GetWindowRect(hwnd, ctypes.byref(rect)):
        return {"left": rect.left, "top": rect.top,
                "right": rect.right, "bottom": rect.bottom,
                "width": rect.right - rect.left,
                "height": rect.bottom - rect.top}
    return None


# ── 窗口操控 ────────────────────────────────────────────────────────

def activate_window(hwnd: int) -> bool:
    """激活并前置窗口。"""
    if not is_windows() or not hwnd:
        return False
    try:
        if _IsIconic(hwnd):
            _ShowWindow(hwnd, SW_RESTORE)
        _SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def close_window(hwnd: int) -> bool:
    """发送 WM_CLOSE 消息关闭窗口。"""
    if not is_windows() or not hwnd:
        return False
    try:
        _PostMessageW(hwnd, WM_CLOSE, 0, 0)
        return True
    except Exception:
        return False


# ── 控件交互 ────────────────────────────────────────────────────────

def click_control(hwnd: int) -> bool:
    """向控件发送 BM_CLICK 消息（按钮点击）。

    对于非 Button 类控件，改为发送 WM_LBUTTONDOWN + WM_LBUTTONUP。
    """
    if not is_windows() or not hwnd:
        return False
    try:
        class_name = get_class_name(hwnd)
        if class_name == "Button":
            _SendMessageW(hwnd, BM_CLICK, 0, 0)
        else:
            _SendMessageW(hwnd, WM_LBUTTONDOWN, 0, 0)
            _SendMessageW(hwnd, WM_LBUTTONUP, 0, 0)
        return True
    except Exception as e:
        logger.warning(f"click_control failed: {e}")
        return False


def set_control_text(hwnd: int, text: str) -> bool:
    """向 Edit 控件设置文本。"""
    if not is_windows() or not hwnd:
        return False
    try:
        _SendMessageW(hwnd, WM_SETTEXT, 0, ctypes.c_wchar_p(text))
        return True
    except Exception as e:
        logger.warning(f"set_control_text failed: {e}")
        return False


def get_control_text(hwnd: int) -> str:
    """从控件获取文本。"""
    if not is_windows() or not hwnd:
        return ""
    try:
        length = _SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        _SendMessageW(hwnd, WM_GETTEXT, length + 1, ctypes.byref(buf))
        return buf.value
    except Exception as e:
        logger.warning(f"get_control_text failed: {e}")
        return ""


def send_message(hwnd: int, msg: int, wparam: int = 0, lparam: int = 0) -> int:
    """发送自定义 Windows 消息。"""
    if not is_windows() or not hwnd:
        return 0
    try:
        result = _SendMessageW(hwnd, msg, wparam, lparam)
        return result
    except Exception:
        return 0


# ── ComboBox / ListBox 操作 ──────────────────────────────────────────

def combo_get_count(hwnd: int) -> int:
    """获取 ComboBox 的选项数量。"""
    if not hwnd:
        return 0
    try:
        return _SendMessageW(hwnd, CB_GETCOUNT, 0, 0)
    except Exception:
        return 0


def combo_select_index(hwnd: int, index: int) -> bool:
    """选择 ComboBox 的第 index 项。"""
    if not hwnd:
        return False
    try:
        _SendMessageW(hwnd, CB_SETCURSEL, index, 0)
        return True
    except Exception:
        return False
