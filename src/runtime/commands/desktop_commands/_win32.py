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
import time
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


def resolve_hwnd(value):
    """从 统一控件引用 / UIA dict / int 解析出 HWND。

    让纯 Win32 指令（findChild/clickControl/inputControl/closeWindow/screenshot 等）
    直接消费「自动选择」指令（findWindowAuto/pickElementAuto）产出的统一引用，
    以及旧 findWindowUia/pickElementUia 的 UIA dict（其 _uia_ctrl 带 Handle）。
    无法解析返回 None（调用方按无效句柄报错）。
    """
    if isinstance(value, int):
        return value
    if isinstance(value, dict):
        ref = value.get("desktop_ref")
        if ref == "win32":
            return value.get("hwnd")
        # UIA 控件 dict（含统一引用 uia 通道或旧 findWindowUia 产物）→ 取原生句柄
        if ref == "uia" or "_uia_ctrl" in value:
            ctrl = value.get("_uia_ctrl")
            try:
                # uiautomation 控件句柄属性为 NativeWindowHandle（repr 里的 Handle 只是显示）
                h = getattr(ctrl, "NativeWindowHandle", None) or getattr(ctrl, "Handle", None)
                return int(h) if h else None
            except Exception:
                return None
        if "hwnd" in value:
            return value.get("hwnd")
    return None


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


# ── 鼠标 / 光标 ──────────────────────────────────────────────────────

_GetCursorPos = _user32.GetCursorPos
_GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
_GetCursorPos.restype = wintypes.BOOL


def get_cursor_pos() -> dict | None:
    """读取当前鼠标光标在屏幕上的坐标 (x, y)。

    使用 GetCursorPos，返回虚拟屏幕坐标系（多显示器时副屏可含负坐标）。
    非 Windows 平台或失败时返回 None。
    """
    if not is_windows():
        return None
    try:
        pt = wintypes.POINT()
        if _GetCursorPos(ctypes.byref(pt)):
            return {"x": int(pt.x), "y": int(pt.y)}
    except Exception:
        pass
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
        # LPARAM 是整型：取指针的整数值（直接传 c_wchar_p/c_void_p 对象会 TypeError）
        lparam = ctypes.cast(ctypes.c_wchar_p(text), ctypes.c_void_p).value
        _SendMessageW(hwnd, WM_SETTEXT, 0, lparam)
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
        lparam = ctypes.cast(ctypes.byref(buf), ctypes.c_void_p).value
        _SendMessageW(hwnd, WM_GETTEXT, length + 1, lparam)
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


# ── 音量控制 ────────────────────────────────────────────────────────
# winmm API — waveOutSetVolume / waveOutGetVolume（控制默认音频设备主音量）

_winmm = ctypes.windll.winmm

_waveOutSetVolume = _winmm.waveOutSetVolume
_waveOutSetVolume.argtypes = [ctypes.c_void_p, ctypes.c_uint]
_waveOutSetVolume.restype = ctypes.c_uint

_waveOutGetVolume = _winmm.waveOutGetVolume
_waveOutGetVolume.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
_waveOutGetVolume.restype = ctypes.c_uint

# WAVE_MAPPER = (HWAVEOUT)-1，指向默认音频设备（64 位下为全 1）
_WAVE_MAPPER = ctypes.c_void_p(-1)

MAX_VOLUME = 0xFFFF


def set_volume(value: int) -> bool:
    """将系统主音量设置为指定百分比（0-100）。

    使用 winmm.waveOutSetVolume 作用于默认音频设备（WAVE_MAPPER）。
    dwVolume 左右声道各占 16 位（0x0000 静音 ~ 0xFFFF 最大），此处两声道设置相同值。
    value 会被 clamp 到 0-100。

    Returns:
        是否设置成功。
    """
    if not is_windows():
        return False
    try:
        value = max(0, min(100, int(value)))
        level = (value * MAX_VOLUME) // 100
        packed = (level & 0xFFFF) | ((level & 0xFFFF) << 16)
        return _waveOutSetVolume(_WAVE_MAPPER, packed) == 0
    except Exception:
        return False


def get_volume() -> int:
    """获取当前系统主音量百分比（0-100）；非 Windows 或失败返回 0。"""
    if not is_windows():
        return 0
    try:
        cur = ctypes.c_uint()
        if _waveOutGetVolume(_WAVE_MAPPER, ctypes.byref(cur)) != 0:
            return 0
        left = cur.value & 0xFFFF
        return int(round(left * 100 / MAX_VOLUME))
    except Exception:
        return 0


# ── 屏幕亮度控制 ────────────────────────────────────────────────────
# 通道1: WMI root\WMI — WmiMonitorBrightnessMethods.WmiSetBrightness（笔记本内屏/支持 WMI 亮度接口）
# 通道2: Dxva2.dll Physical Monitor API — SetMonitorBrightness / GetMonitorBrightness（DDC/CI 外接显示器）
# set_brightness 先走 WMI，失败再回退 Dxva2；get_brightness 同理。

# --- Dxva2 Physical Monitor API（DDC/CI）---
# 仅 Windows 加载；非 Windows 或 DLL 缺失时置 None，后续调用按不支持处理。
try:
    _dxva2 = ctypes.windll.dxva2
except Exception:
    _dxva2 = None

if _dxva2 is not None:
    _GetNumberOfPhysicalMonitorsFromHMONITOR = _dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR
    _GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    _GetNumberOfPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL

    _GetPhysicalMonitorsFromHMONITOR = _dxva2.GetPhysicalMonitorsFromHMONITOR
    _GetPhysicalMonitorsFromHMONITOR.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
    _GetPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL

    _SetMonitorBrightness = _dxva2.SetMonitorBrightness
    _SetMonitorBrightness.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _SetMonitorBrightness.restype = wintypes.BOOL

    _GetMonitorBrightness = _dxva2.GetMonitorBrightness
    _GetMonitorBrightness.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    _GetMonitorBrightness.restype = wintypes.BOOL

    _DestroyPhysicalMonitors = _dxva2.DestroyPhysicalMonitors
    _DestroyPhysicalMonitors.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    _DestroyPhysicalMonitors.restype = wintypes.BOOL

    _GetMonitorInfoW = _user32.GetMonitorInfoW
    _GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _GetMonitorInfoW.restype = wintypes.BOOL


class _PHYSICAL_MONITOR(ctypes.Structure):
    """PHYSICAL_MONITOR：一个物理显示器的句柄 + 描述。"""
    _fields_ = [
        ("hPhysicalMonitor", ctypes.c_void_p),
        ("szPhysicalMonitorDescription", ctypes.c_wchar * 128),
    ]


_MONITORINFOF_PRIMARY = 0x1


class _MONITORINFO(ctypes.Structure):
    """MONITORINFO：显示器信息，dwFlags 含 MONITORINFOF_PRIMARY。"""
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", ctypes.c_uint32),
    ]


_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.LPARAM
)
_EnumDisplayMonitors = _user32.EnumDisplayMonitors
_EnumDisplayMonitors.argtypes = [ctypes.c_void_p, ctypes.c_void_p, _MONITORENUMPROC, wintypes.LPARAM]
_EnumDisplayMonitors.restype = wintypes.BOOL


def _is_primary_monitor(hmonitor) -> bool:
    """判断给定 HMONITOR 是否为主显示器。"""
    try:
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if _GetMonitorInfoW(hmonitor, ctypes.byref(mi)):
            return bool(mi.dwFlags & _MONITORINFOF_PRIMARY)
    except Exception:
        pass
    return False


def _set_brightness_wmi(value: int) -> bool:
    """通过 WMI（root\\WMI / WmiMonitorBrightnessMethods.WmiSetBrightness）设置亮度。

    适用于笔记本内屏及支持 WMI 亮度接口的显示器。需要 pywin32（win32com)。
    Returns:
        是否至少设置了一个显示器。
    """
    try:
        import win32com.client  # noqa: F401

        wmig = win32com.client.GetObject("winmgmts:\\\\.\\root\\WMI")
        instances = wmig.InstancesOf("WmiMonitorBrightnessMethods")
        changed = False
        for inst in instances:
            try:
                inst.WmiSetBrightness(value, 0)
                changed = True
            except Exception:
                pass
        return changed
    except Exception:
        return False


def _set_brightness_physical(value: int, scope: str = "all") -> bool:
    """通过 Dxva2 Physical Monitor API（SetMonitorBrightness）设置亮度。

    适用于支持 DDC/CI 的外接显示器。scope 为 "primary" 时仅调节主显示器。
    """
    if _dxva2 is None or not is_windows():
        return False
    changed = False
    handles = []

    @_MONITORENUMPROC
    def callback(hmonitor, _hdc, _lprect, _lparam):
        nonlocal changed
        if scope == "primary" and not _is_primary_monitor(hmonitor):
            return True
        count = ctypes.c_uint32()
        if not _GetNumberOfPhysicalMonitorsFromHMONITOR(hmonitor, ctypes.byref(count)) or count.value == 0:
            return True
        arr = (_PHYSICAL_MONITOR * count.value)()
        if not _GetPhysicalMonitorsFromHMONITOR(hmonitor, count.value, arr):
            return True
        for i in range(count.value):
            try:
                if _SetMonitorBrightness(arr[i].hPhysicalMonitor, value):
                    changed = True
            except Exception:
                pass
            handles.append(arr[i].hPhysicalMonitor)
        return True

    _EnumDisplayMonitors(None, None, callback, 0)
    _destroy_monitor_handles(handles)
    return changed


def _get_brightness_wmi() -> dict | None:
    """通过 WMI（root\\WMI / WmiMonitorBrightness）读取当前亮度。"""
    try:
        import win32com.client  # noqa: F401

        wmig = win32com.client.GetObject("winmgmts:\\\\.\\root\\WMI")
        instances = wmig.InstancesOf("WmiMonitorBrightness")
        for inst in instances:
            try:
                cur = int(inst.CurrentBrightness)
                return {"current": cur, "min": 0, "max": 100, "source": "wmi"}
            except Exception:
                continue
        return None
    except Exception:
        return None


def _get_brightness_physical() -> dict | None:
    """通过 Dxva2 Physical Monitor API（GetMonitorBrightness）读取当前亮度。"""
    if _dxva2 is None or not is_windows():
        return None
    out = {"current": None, "min": 0, "max": 100, "source": "physical"}
    handles = []

    @_MONITORENUMPROC
    def callback(hmonitor, _hdc, _lprect, _lparam):
        nonlocal out
        count = ctypes.c_uint32()
        if not _GetNumberOfPhysicalMonitorsFromHMONITOR(hmonitor, ctypes.byref(count)) or count.value == 0:
            return True
        arr = (_PHYSICAL_MONITOR * count.value)()
        if not _GetPhysicalMonitorsFromHMONITOR(hmonitor, count.value, arr):
            return True
        for i in range(count.value):
            mn = ctypes.c_uint32()
            cur = ctypes.c_uint32()
            mx = ctypes.c_uint32()
            try:
                if _GetMonitorBrightness(
                    arr[i].hPhysicalMonitor,
                    ctypes.byref(mn), ctypes.byref(cur), ctypes.byref(mx),
                ):
                    if out["current"] is None:
                        out["current"] = int(cur.value)
                        out["min"] = int(mn.value)
                        out["max"] = int(mx.value)
            except Exception:
                pass
            handles.append(arr[i].hPhysicalMonitor)
        return True

    _EnumDisplayMonitors(None, None, callback, 0)
    _destroy_monitor_handles(handles)
    return out if out["current"] is not None else None


def _destroy_monitor_handles(handles: list) -> None:
    """释放通过 GetPhysicalMonitorsFromHMONITOR 打开的物理显示器句柄。"""
    if _dxva2 is None or not handles:
        return
    try:
        for h in handles:
            arr = (_PHYSICAL_MONITOR * 1)(h, "")
            _DestroyPhysicalMonitors(1, arr)
    except Exception:
        pass


def set_brightness(value: int, scope: str = "all") -> dict:
    """将显示器亮度调整到指定百分比（0-100，0 为最暗）。

    通道优先级：WMI（笔记本内屏/支持 WMI 亮度接口）→ Dxva2 Physical Monitor
    API（DDC/CI 外接显示器）。value 会被 clamp 到 0-100。

    Args:
        value: 目标亮度（0-100）。
        scope: "all" 或 "primary"。

    Returns:
        {"ok": bool, "value": 目标值, "scope": scope, "source": "wmi|physical|none", "error": str?}。
    """
    if not is_windows():
        return {"ok": False, "value": value, "scope": scope, "source": "none",
                "error": "当前系统非 Windows，设置亮度仅支持 Windows"}
    value = max(0, min(100, int(value)))
    if _set_brightness_wmi(value):
        return {"ok": True, "value": value, "scope": scope, "source": "wmi"}
    if _set_brightness_physical(value, scope):
        return {"ok": True, "value": value, "scope": scope, "source": "physical"}
    return {"ok": False, "value": value, "scope": scope, "source": "none",
            "error": "未找到支持亮度调节的显示器"}


def get_brightness() -> dict | None:
    """读取当前显示器亮度。优先 WMI，回退 Physical Monitor API。

    Returns:
        {"current": int, "min": int, "max": int, "source": "wmi|physical"} 或 None。
    """
    v = _get_brightness_wmi()
    if v:
        return v
    return _get_brightness_physical()


# ── 读取屏幕/显示器信息 ────────────────────────────────────────────

class _MONITORINFOEXW(ctypes.Structure):
    """MONITORINFOEXW：比 MONITORINFO 多一个设备名 szDevice。

    GetMonitorInfoW 根据 cbSize 判定是否为 EXW 版本；
    cbSize = sizeof(MONITORINFOEXW) 时把设备名（如 \\\\.\\DISPLAY1）写入 szDevice。
    """
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", ctypes.c_uint32),
        ("szDevice", ctypes.c_wchar * 32),
    ]


class _DEVMODE_PRINT(ctypes.Structure):
    """DEVMODE union 的打印分支（8 个 WORD）。"""
    _fields_ = [
        ("dmOrientation", ctypes.c_uint16),
        ("dmPaperSize", ctypes.c_uint16),
        ("dmPaperLength", ctypes.c_uint16),
        ("dmPaperWidth", ctypes.c_uint16),
        ("dmScale", ctypes.c_uint16),
        ("dmCopies", ctypes.c_uint16),
        ("dmDefaultSource", ctypes.c_uint16),
        ("dmPrintQuality", ctypes.c_uint16),
    ]


class _DEVMODE_DISPLAY(ctypes.Structure):
    """DEVMODE union 的显示分支（POINTL + 2 个 DWORD，16 字节）。"""
    _fields_ = [
        ("dmPosition", wintypes.POINT),
        ("dmDisplayOrientation", ctypes.c_uint32),
        ("dmDisplayFixedOutput", ctypes.c_uint32),
    ]


class _DEVMODE_UNION(ctypes.Union):
    """DEVMODE 头的联合体：打印/显示分支，两分支均 16 字节。"""
    _fields_ = [
        ("display", _DEVMODE_DISPLAY),
        ("print", _DEVMODE_PRINT),
    ]


class _DEVMODE(ctypes.Structure):
    """DEVMODE：取 dmPelsWidth/dmPelsHeight/dmDisplayFrequency 以获取分辨率与刷新率。

    字段布局遵循 Windows 头文件 DEVMODEW：头部 union 占 16 字节，
    因此 dmPelsWidth 位于 offset 172，dmDisplayFrequency 位于 offset 184。
    """
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", ctypes.c_uint16),
        ("dmDriverVersion", ctypes.c_uint16),
        ("dmSize", ctypes.c_uint16),
        ("dmDriverExtra", ctypes.c_uint16),
        ("dmFields", ctypes.c_uint32),
        ("dmUnion", _DEVMODE_UNION),
        ("dmColor", ctypes.c_uint16),
        ("dmDuplex", ctypes.c_uint16),
        ("dmYResolution", ctypes.c_uint16),
        ("dmTTOption", ctypes.c_uint16),
        ("dmCollate", ctypes.c_uint16),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", ctypes.c_uint16),
        ("dmBitsPerPel", ctypes.c_uint32),
        ("dmPelsWidth", ctypes.c_uint32),
        ("dmPelsHeight", ctypes.c_uint32),
        ("dmDisplayFlags", ctypes.c_uint32),
        ("dmDisplayFrequency", ctypes.c_uint32),
        ("dmICMMethod", ctypes.c_uint32),
        ("dmICMIntent", ctypes.c_uint32),
        ("dmMediaType", ctypes.c_uint32),
        ("dmDitherType", ctypes.c_uint32),
        ("dmReserved1", ctypes.c_uint32),
        ("dmReserved2", ctypes.c_uint32),
        ("dmPanningWidth", ctypes.c_uint32),
        ("dmPanningHeight", ctypes.c_uint32),
    ]


_MDT_EFFECTIVE_DPI = 0
_ENUM_CURRENT_SETTINGS = -1

# GetSystemMetrics 索引常量
_SM_CXSCREEN = 0
_SM_CYSCREEN = 1
_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79


def _get_dpi_for_monitor_fn():
    """shcore.GetDpiForMonitor（Win 8.1+）绑定；失败返回 None。"""
    try:
        fn = ctypes.windll.shcore.GetDpiForMonitor
        fn.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                       ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
        fn.restype = ctypes.c_int32
        return fn
    except Exception:
        return None


def _get_enum_display_settings_fn():
    """user32.EnumDisplaySettingsW 绑定；失败返回 None。"""
    try:
        fn = ctypes.windll.user32.EnumDisplaySettingsW
        fn.argtypes = [wintypes.LPCWSTR, ctypes.c_uint32, ctypes.POINTER(_DEVMODE)]
        fn.restype = wintypes.BOOL
        return fn
    except Exception:
        return None


def get_screen_info() -> dict | None:
    """读取所有显示器信息（分辨率/坐标/工作区/DPI/刷新率/主屏标志）及屏幕指标。

    Returns:
        结构化 dict：
        {
          "count": int,
          "primary": 主显示器 dict（与 monitors 中条目同构）,
          "monitors": [
            {index, device, isPrimary, x, y, width, height,
             workArea:{left,top,right,bottom,width,height},
             dpi, resolution:{width,height}, refreshRate},
            ...
          ],
          "screen": {"width":..., "height":...},          # 主屏分辨率
          "virtualScreen": {"x":..., "y":..., "width":..., "height":...},
          "systemDpi": int,
        }
        非 Windows 或枚举失败返回 None。
    """
    if not is_windows():
        return None

    _GetSystemMetrics = ctypes.windll.user32.GetSystemMetrics
    _GetSystemMetrics.argtypes = [ctypes.c_int]
    _GetSystemMetrics.restype = ctypes.c_int

    dpi_fn = _get_dpi_for_monitor_fn()
    enum_fn = _get_enum_display_settings_fn()

    def _monitor_dpi(hmonitor) -> int | None:
        if dpi_fn is None:
            return None
        dx = ctypes.c_uint32()
        dy = ctypes.c_uint32()
        try:
            if dpi_fn(hmonitor, _MDT_EFFECTIVE_DPI, ctypes.byref(dx), ctypes.byref(dy)) == 0:
                return int(dx.value)
        except Exception:
            pass
        return None

    def _device_setting(device):
        if enum_fn is None:
            return None
        dm = _DEVMODE()
        dm.dmSize = ctypes.sizeof(_DEVMODE)
        try:
            if enum_fn(device, _ENUM_CURRENT_SETTINGS, ctypes.byref(dm)):
                return {
                    "width": int(dm.dmPelsWidth),
                    "height": int(dm.dmPelsHeight),
                    "refreshRate": int(dm.dmDisplayFrequency),
                }
        except Exception:
            pass
        return None

    monitors: list[dict] = []

    @_MONITORENUMPROC
    def _callback(hmonitor, _hdc, _lprect, _lparam):
        mi = _MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if not _GetMonitorInfoW(hmonitor, ctypes.byref(mi)):
            return True
        device = mi.szDevice
        entry = {
            "index": len(monitors),
            "device": device,
            "isPrimary": bool(mi.dwFlags & _MONITORINFOF_PRIMARY),
            "x": mi.rcMonitor.left,
            "y": mi.rcMonitor.top,
            "width": mi.rcMonitor.right - mi.rcMonitor.left,
            "height": mi.rcMonitor.bottom - mi.rcMonitor.top,
            "workArea": {
                "left": mi.rcWork.left,
                "top": mi.rcWork.top,
                "right": mi.rcWork.right,
                "bottom": mi.rcWork.bottom,
                "width": mi.rcWork.right - mi.rcWork.left,
                "height": mi.rcWork.bottom - mi.rcWork.top,
            },
            "dpi": _monitor_dpi(hmonitor),
        }
        st = _device_setting(device)
        if st:
            entry["resolution"] = {"width": st["width"], "height": st["height"]}
            entry["refreshRate"] = st["refreshRate"]
        else:
            entry["resolution"] = {"width": entry["width"], "height": entry["height"]}
            entry["refreshRate"] = None
        monitors.append(entry)
        return True

    try:
        _EnumDisplayMonitors(None, None, _callback, 0)
    except Exception:
        pass

    if not monitors:
        return None

    screen_w = int(_GetSystemMetrics(_SM_CXSCREEN))
    screen_h = int(_GetSystemMetrics(_SM_CYSCREEN))

    try:
        _GetDpiForSystem = ctypes.windll.user32.GetDpiForSystem
        _GetDpiForSystem.restype = ctypes.c_uint
        sys_dpi = int(_GetDpiForSystem())
    except Exception:
        sys_dpi = None

    primary = next((m for m in monitors if m["isPrimary"]), monitors[0])

    return {
        "count": len(monitors),
        "primary": primary,
        "monitors": monitors,
        "screen": {"width": screen_w, "height": screen_h},
        "virtualScreen": {
            "x": int(_GetSystemMetrics(_SM_XVIRTUALSCREEN)),
            "y": int(_GetSystemMetrics(_SM_YVIRTUALSCREEN)),
            "width": int(_GetSystemMetrics(_SM_CXVIRTUALSCREEN)),
            "height": int(_GetSystemMetrics(_SM_CYVIRTUALSCREEN)),
        },
        "systemDpi": sys_dpi,
    }


# ── 读取系统硬件信息 ────────────────────────────────────────────────────

# 一次 PowerShell 调用批量取硬件信息（CPU/计算机/主板/BIOS/OS/显卡/磁盘），
# 输出 JSON 供 Python 解析。仅 Windows 执行；每段独立 try/catch，失败项缺失。
_HARDWARE_PS = r"""
$r = @{}
try { $r['cpu'] = @(Get-CimInstance Win32_Processor | ForEach-Object {
    [PSCustomObject]@{ name=$_.Name; cores=$_.NumberOfCores; threads=$_.NumberOfLogicalProcessors; maxClock=$_.MaxClockSpeed }
}) } catch {}
try { $r['computer'] = @(Get-CimInstance Win32_ComputerSystem | ForEach-Object {
    [PSCustomObject]@{ manufacturer=$_.Manufacturer; model=$_.Model; totalMemory=$_.TotalPhysicalMemory }
}) } catch {}
try { $r['baseboard'] = @(Get-CimInstance Win32_BaseBoard | ForEach-Object {
    [PSCustomObject]@{ manufacturer=$_.Manufacturer; product=$_.Product }
}) } catch {}
try { $r['bios'] = @(Get-CimInstance Win32_BIOS | ForEach-Object {
    [PSCustomObject]@{ manufacturer=$_.Manufacturer; version=$_.SMBIOSBIOSVersion }
}) } catch {}
try { $r['os'] = @(Get-CimInstance Win32_OperatingSystem | ForEach-Object {
    [PSCustomObject]@{ caption=$_.Caption; version=$_.Version; build=$_.BuildNumber;
                      totalMemory=$_.TotalVisibleMemorySize; freeMemory=$_.FreePhysicalMemory }
}) } catch {}
try { $r['gpu'] = @(Get-CimInstance Win32_VideoController | ForEach-Object {
    [PSCustomObject]@{ name=$_.Name; vram=$_.AdapterRAM; driver=$_.DriverVersion }
}) } catch {}
try { $r['disk'] = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
    [PSCustomObject]@{ device=$_.DeviceID; size=$_.Size; free=$_.FreeSpace }
}) } catch {}
$r | ConvertTo-Json -Depth 6 -Compress
"""

# get_hardware_info 支持的 scope 值 → 返回的顶层键
_HW_SCOPE_KEYS = {
    "system": "system",
    "cpu": "cpu",
    "memory": "memory",
    "gpu": "gpu",
    "disk": "disk",
}


def fmt_bytes(n) -> str | None:
    """将字节数格式化为可读字符串；空/异常值返回 None。"""
    try:
        n = float(n or 0)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _run_powershell_json(script: str) -> dict | None:
    """运行一次性 PowerShell 命令并解析 JSON 输出；失败返回 None。"""
    if not is_windows():
        return None
    try:
        import subprocess
        import json
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", script],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return None
        out = proc.stdout.strip()
        if not out:
            return None
        return json.loads(out)
    except Exception:
        return None


def _normalize_list(val) -> list:
    """ConvertTo-Json 单项时不包 []，这里统一规整为列表。"""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def _get_memory_status() -> dict:
    """读取物理内存总量/可用量（字节）。

    Windows 用 GlobalMemoryStatusEx；非 Windows 尝试 psutil，失败返回 {}。
    """
    if is_windows():
        try:
            class _MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_uint32),
                    ("dwMemoryLoad", ctypes.c_uint32),
                    ("ullTotalPhys", ctypes.c_uint64),
                    ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64),
                    ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64),
                    ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64),
                ]
            ms = _MEMORYSTATUSEX()
            ms.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
                return {
                    "total": int(ms.ullTotalPhys),
                    "available": int(ms.ullAvailPhys),
                    "usagePercent": int(ms.dwMemoryLoad),
                }
        except Exception:
            pass
    try:
        import psutil
        vm = psutil.virtual_memory()
        return {"total": int(vm.total), "available": int(vm.available),
                "usagePercent": int(vm.percent)}
    except Exception:
        return {}


def get_hardware_info(scope: str = "all") -> dict:
    """读取系统硬件信息，按 scope 过滤返回对应部分。

    Args:
        scope: "all" | "system" | "cpu" | "memory" | "gpu" | "disk"。

    Returns:
        结构化 dict，顶层键取决于 scope：
          system: {python, manufacturer, model, totalMemory, motherboard, bios, os}
          cpu:    {list:[{name, cores, threads, maxClock}], physicalCores, logicalCores, count}
          memory: {total, available, usagePercent}
          gpu:    {list:[{name, vram, vramText, driver}], count}
          disk:   {list:[{device, size, free, sizeText, freeText}], count}
        单段读取失败时该项为空列表/空字典，不抛异常。
    """
    if scope not in _HW_SCOPE_KEYS and scope != "all":
        scope = "all"
    want = set(_HW_SCOPE_KEYS) if scope == "all" else {_HW_SCOPE_KEYS[scope]}
    out: dict = {"scope": scope}

    ps = _run_powershell_json(_HARDWARE_PS) if is_windows() else None

    # ── system：Python 通用信息 + PowerShell 计算机/主板/BIOS/OS ──
    if "system" in want:
        sys_part: dict = {}
        try:
            import platform as _pf
            import os as _os
            import sys as _sys
            sys_part["python"] = {
                "name": _pf.system(),
                "release": _pf.release(),
                "version": _pf.version(),
                "machine": _pf.machine(),
                "processor": _pf.processor(),
                "node": _pf.node(),
                "platform": _pf.platform(),
                "logicalCpuCount": _os.cpu_count(),
                "pythonVersion": _sys.version.split()[0],
            }
        except Exception:
            pass
        if ps:
            comps = _normalize_list(ps.get("computer"))
            if comps:
                c = comps[0]
                sys_part["manufacturer"] = c.get("manufacturer")
                sys_part["model"] = c.get("model")
                total = c.get("totalMemory")
                if total:
                    sys_part["totalMemory"] = int(total)
            boards = _normalize_list(ps.get("baseboard"))
            if boards:
                b = boards[0]
                mb = f"{b.get('manufacturer', '')} {b.get('product', '')}".strip()
                sys_part["motherboard"] = mb
            bioses = _normalize_list(ps.get("bios"))
            if bioses:
                bio = bioses[0]
                bv = f"{bio.get('manufacturer', '')} {bio.get('version', '')}".strip()
                sys_part["bios"] = bv
            oses = _normalize_list(ps.get("os"))
            if oses:
                o = oses[0]
                sys_part["os"] = {
                    "caption": o.get("caption"),
                    "version": o.get("version"),
                    "build": o.get("build"),
                }
        out["system"] = sys_part

    # ── cpu ──
    if "cpu" in want:
        cpu_list: list = []
        if ps:
            for c in _normalize_list(ps.get("cpu")):
                cpu_list.append({
                    "name": (c.get("name") or "").strip(),
                    "cores": c.get("cores"),
                    "threads": c.get("threads"),
                    "maxClock": c.get("maxClock"),
                })
        import os as _os
        import platform as _pf
        logical = _os.cpu_count()
        # WMI 不可用（如受限环境/非 Windows）时用 platform/环境变量兜底，保证有 CPU
        if not cpu_list:
            cpu_name = (_os.environ.get("PROCESSOR_IDENTIFIER") or _pf.processor() or "").strip()
            cpu_list.append({"name": cpu_name or None, "cores": None,
                             "threads": logical, "maxClock": None})
        cores = cpu_list[0].get("cores")
        threads = cpu_list[0].get("threads")
        out["cpu"] = {
            "list": cpu_list,
            "physicalCores": cores,
            "logicalCores": threads if threads else logical,
            "count": len(cpu_list),
        }

    # ── memory ──
    if "memory" in want:
        mem = _get_memory_status()
        # 若 ctypes 未取到，用 PowerShell 的计算机总内存兜底（字节）
        if ps:
            comps = _normalize_list(ps.get("computer"))
            if comps and comps[0].get("totalMemory") and not mem.get("total"):
                mem["total"] = int(comps[0]["totalMemory"])
        out["memory"] = mem

    # ── gpu ──
    if "gpu" in want:
        gpu_list: list = []
        if ps:
            for g in _normalize_list(ps.get("gpu")):
                vram = g.get("vram")
                entry = {
                    "name": (g.get("name") or "").strip(),
                    "vram": int(vram) if vram else None,
                    "vramText": fmt_bytes(vram),
                    "driver": g.get("driver"),
                }
                gpu_list.append(entry)
        out["gpu"] = {"list": gpu_list, "count": len(gpu_list)}

    # ── disk ──
    if "disk" in want:
        disk_list: list = []
        if ps:
            for d in _normalize_list(ps.get("disk")):
                size = d.get("size")
                free = d.get("free")
                disk_list.append({
                    "device": d.get("device"),
                    "size": int(size) if size else None,
                    "free": int(free) if free else None,
                    "sizeText": fmt_bytes(size),
                    "freeText": fmt_bytes(free),
                })
        if not disk_list:
            try:
                import shutil
                for drive in _get_local_drives():
                    try:
                        usage = shutil.disk_usage(drive)
                        disk_list.append({
                            "device": drive,
                            "size": usage.total,
                            "free": usage.free,
                            "sizeText": fmt_bytes(usage.total),
                            "freeText": fmt_bytes(usage.free),
                        })
                    except Exception:
                        pass
            except Exception:
                pass
        out["disk"] = {"list": disk_list, "count": len(disk_list)}

    return out


def _get_local_drives() -> list[str]:
    """枚举本地固定磁盘盘符（如 'C:\\'），非 Windows 返回[]。"""
    if not is_windows():
        return []
    try:
        import string
        import ctypes as _ct
        bitmask = _ct.windll.kernel32.GetLogicalDrives()
        drives = []
        for i, ch in enumerate(string.ascii_uppercase):
            if bitmask & (1 << i):
                drives.append(f"{ch}:\\")
        return drives
    except Exception:
        return []
