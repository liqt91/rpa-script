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

_IsWindow = _user32.IsWindow
_IsWindow.argtypes = [wintypes.HWND]
_IsWindow.restype = wintypes.BOOL

_IsWindowEnabled = _user32.IsWindowEnabled
_IsWindowEnabled.argtypes = [wintypes.HWND]
_IsWindowEnabled.restype = wintypes.BOOL

_SetFocus = _user32.SetFocus
_SetFocus.argtypes = [wintypes.HWND]
_SetFocus.restype = wintypes.HWND

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
        return bool(_IsWindow(hwnd))
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


def find_edit_by_label(parent_hwnd: int, label: str, edit_index: int = 0) -> int | None:
    """通过 Static 标签文字定位相邻的输入控件（Edit 或 ComboBox）。

    常见对话框（文件打开、保存等）中标签旁边的控件可能是 Edit
    或 ComboBox/ComboBoxEx32。标签找不到则回退到直接取第 N 个匹配控件。
    """
    if not is_windows() or not parent_hwnd:
        return None

    _INPUT_CLASSES = {"Edit", "ComboBox", "ComboBoxEx32"}

    children = enum_child_windows(parent_hwnd)
    if not children:
        return None

    # 找匹配的 Static 标签
    label_idx = None
    for i, child in enumerate(children):
        if child["class_name"] == "Static" and label.lower() in child["title"].lower():
            label_idx = i
            break

    start = label_idx if label_idx is not None else 0
    match_count = 0
    for child in children[start:]:
        if child["class_name"] in _INPUT_CLASSES:
            if match_count == edit_index:
                return child["hwnd"]
            match_count += 1

    return None


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


# 窗口关系导航
_GetParent = _user32.GetParent
_GetParent.argtypes = [wintypes.HWND]
_GetParent.restype = wintypes.HWND

_GetWindow = _user32.GetWindow
_GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
_GetWindow.restype = wintypes.HWND

GW_HWNDNEXT = 2
GW_HWNDPREV = 3
GW_CHILD = 5
GW_HWNDFIRST = 0
GW_HWNDLAST = 1


def get_parent_window(hwnd: int) -> int | None:
    """获取父窗口句柄。"""
    if not is_windows() or not hwnd:
        return None
    parent = _GetParent(hwnd)
    return parent if parent else None


def get_next_sibling(hwnd: int) -> int | None:
    """获取下一个兄弟窗口（Z 序后继，同层级）。"""
    if not is_windows() or not hwnd:
        return None
    next_hwnd = _GetWindow(hwnd, GW_HWNDNEXT)
    return next_hwnd if next_hwnd else None


def get_prev_sibling(hwnd: int) -> int | None:
    """获取上一个兄弟窗口（Z 序前驱）。"""
    if not is_windows() or not hwnd:
        return None
    prev_hwnd = _GetWindow(hwnd, GW_HWNDPREV)
    return prev_hwnd if prev_hwnd else None


def find_sibling_by_class(hwnd: int, class_name: str = "",
                           direction: str = "next", skip: int = 0) -> int | None:
    """从参考控件出发，按方向查找第 skip 个匹配类名的兄弟。

    Args:
        hwnd: 参考控件句柄
        class_name: 目标类名（空=不筛选）
        direction: "next" 或 "prev"
        skip: 跳过几个匹配项（0=第一个）
    """
    if not is_windows() or not hwnd:
        return None
    gw_cmd = GW_HWNDNEXT if direction == "next" else GW_HWNDPREV
    cur = _GetWindow(hwnd, gw_cmd)
    matched = 0
    while cur:
        if not class_name or get_class_name(cur) == class_name:
            if matched == skip:
                return cur
            matched += 1
        cur = _GetWindow(cur, gw_cmd)
    return None


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


def focus_control(hwnd: int) -> bool:
    """聚焦控件（SetFocus），keybd_event 按键前调用确保按键发到目标。"""
    if not is_windows() or not hwnd:
        return False
    try:
        _SetFocus(hwnd)
        return True
    except Exception:
        return False


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


# ── 菜单操作 ────────────────────────────────────────────────────────

# Menu APIs
_GetMenu = _user32.GetMenu
_GetMenu.argtypes = [wintypes.HWND]
_GetMenu.restype = wintypes.HMENU

_GetSubMenu = _user32.GetSubMenu
_GetSubMenu.argtypes = [wintypes.HMENU, ctypes.c_int]
_GetSubMenu.restype = wintypes.HMENU

_GetMenuItemCount = _user32.GetMenuItemCount
_GetMenuItemCount.argtypes = [wintypes.HMENU]
_GetMenuItemCount.restype = ctypes.c_int

_GetMenuItemID = _user32.GetMenuItemID
_GetMenuItemID.argtypes = [wintypes.HMENU, ctypes.c_int]
_GetMenuItemID.restype = ctypes.c_uint

_GetMenuStringW = _user32.GetMenuStringW
_GetMenuStringW.argtypes = [wintypes.HMENU, ctypes.c_uint, wintypes.LPWSTR, ctypes.c_int, ctypes.c_uint]
_GetMenuStringW.restype = ctypes.c_int

MF_BYPOSITION = 0x00000400


def get_menu_text(hmenu: int, pos: int) -> str:
    """获取菜单项文本。"""
    buf = ctypes.create_unicode_buffer(256)
    if _GetMenuStringW(hmenu, pos, buf, 255, MF_BYPOSITION):
        return buf.value
    return ""


def find_menu_item(hwnd: int, path: list[str]) -> int | None:
    """按路径查找菜单项，返回菜单项 ID。

    Args:
        hwnd: 窗口句柄
        path: 菜单路径列表，如 ["文件", "另存为"]

    Returns:
        菜单项 ID，找到子菜单或无 ID 返回 -1，未找到返回 None
    """
    if not is_windows() or not hwnd or not path:
        return None

    hmenu = _GetMenu(hwnd)
    if not hmenu:
        return None

    for depth, target in enumerate(path):
        is_last = (depth == len(path) - 1)
        count = _GetMenuItemCount(hmenu)
        found = False

        for i in range(count):
            text = get_menu_text(hmenu, i)
            # 清理菜单文本（去掉 & 加速键标记和 Tab 后的快捷键提示）
            clean = text.replace("&", "").split("\t")[0].strip()
            if target.lower() in clean.lower():
                if is_last:
                    item_id = _GetMenuItemID(hmenu, i)
                    return item_id if item_id != 0xFFFFFFFF else -1
                else:
                    hmenu = _GetSubMenu(hmenu, i)
                    found = bool(hmenu)
                    break

        if not found:
            return None

    return None


def click_menu(hwnd: int, item_id: int) -> bool:
    """通过 WM_COMMAND 点击菜单项（PostMessage 异步，避免模态对话框阻塞）。"""
    if not is_windows() or not hwnd or item_id < 0:
        return False
    try:
        _PostMessageW(hwnd, WM_COMMAND, item_id, 0)
        return True
    except Exception:
        return False


# ── 键盘操作 ────────────────────────────────────────────────────────

# keybd_event API
_keybd_event = _user32.keybd_event
_keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_uint, wintypes.LPARAM]
_keybd_event.restype = None

KEYEVENTF_KEYUP = 0x0002

# Virtual-key codes for common keys
_VK_MAP = {
    "Enter": 0x0D, "Tab": 0x09, "Escape": 0x1B, "Backspace": 0x08,
    "Delete": 0x2E, "Space": 0x20, " ": 0x20,
    "ArrowUp": 0x26, "ArrowDown": 0x28, "ArrowLeft": 0x25, "ArrowRight": 0x27,
    "PageUp": 0x21, "PageDown": 0x22, "Home": 0x24, "End": 0x23,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "Insert": 0x2D, "PrintScreen": 0x2C,
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45,
    "f": 0x46, "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A,
    "k": 0x4B, "l": 0x4C, "m": 0x4D, "n": 0x4E, "o": 0x4F,
    "p": 0x50, "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54,
    "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58, "y": 0x59, "z": 0x5A,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
}

_VK_MODIFIERS = {
    "Ctrl": 0x11, "Alt": 0x12, "Shift": 0x10, "Win": 0x5B,
}


# VkKeyScanW — 字符转虚拟键码（处理特殊字符）
_VkKeyScanW = _user32.VkKeyScanW
_VkKeyScanW.argtypes = [wintypes.WCHAR]
_VkKeyScanW.restype = ctypes.c_short


def send_key(key: str, modifiers: str = "", delay: float = 0.05) -> bool:
    """通过 keybd_event 发送键盘按键（OS 级，不依赖浏览器）。

    Args:
        key: 按键名，如 "Enter", "Tab", "a", "F5" 等（见 _VK_MAP）
        modifiers: 修饰键，如 "Ctrl", "Alt", "Ctrl,Shift"
        delay: 按下和释放之间的延迟（秒）

    Returns:
        是否成功发送
    """
    if not is_windows():
        return False
    try:
        import time

        # 按下修饰键
        if modifiers:
            for mod in [m.strip() for m in modifiers.split(",") if m.strip()]:
                vk = _VK_MODIFIERS.get(mod)
                if vk:
                    _keybd_event(vk, 0, 0, 0)

        # 按下目标键
        vk = _VK_MAP.get(key)
        extra_mod = ""
        if vk is None and len(key) == 1:
            # 用 VkKeyScanW 获取特殊字符的正确 VK 码（如 \ : / 等）
            try:
                scan = _VkKeyScanW(ctypes.c_wchar(key))
                vk = scan & 0xFF
                shift = (scan >> 8) & 0xFF
                if shift & 1:
                    extra_mod = "Shift"
            except Exception:
                vk = ord(key.upper())
        if vk is None:
            return False

        # VkKeyScan 返回的修饰键也需要按下
        if extra_mod and extra_mod not in (modifiers or ""):
            _keybd_event(_VK_MODIFIERS[extra_mod], 0, 0, 0)

        _keybd_event(vk, 0, 0, 0)
        time.sleep(delay)
        _keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

        if extra_mod and extra_mod not in (modifiers or ""):
            _keybd_event(_VK_MODIFIERS[extra_mod], 0, KEYEVENTF_KEYUP, 0)

        # 释放修饰键（逆序）
        if modifiers:
            mods = [m.strip() for m in modifiers.split(",") if m.strip()]
            for mod in reversed(mods):
                vk = _VK_MODIFIERS.get(mod)
                if vk:
                    _keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

        return True
    except Exception:
        return False


def send_char(hwnd: int, ch: str) -> bool:
    """发送单个 WM_CHAR 消息到指定窗口，绕过输入法。

    与 keybd_event 不同，WM_CHAR 直接投递到目标窗口过程，
    不会被 IME 拦截。
    """
    try:
        _PostMessageW(hwnd, WM_CHAR, ord(ch), 0)
        return True
    except Exception:
        return False


def send_text_via_char(hwnd: int, text: str, delay: float = 0.02) -> bool:
    """逐字符发送 WM_CHAR，绕过 IME。注意：此函数为同步，需在 asyncio.to_thread 中调用。"""
    try:
        for ch in text:
            _PostMessageW(hwnd, WM_CHAR, ord(ch), 0)
            time.sleep(delay)
        return True
    except Exception:
        return False
