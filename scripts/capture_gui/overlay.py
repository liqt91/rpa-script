"""桌面元素捕获覆盖层 — SetWindowRgn 挖空窗口方案。

鼠标移动时实时高亮目标控件（WS_EX_TOPMOST + SetWindowRgn 挖空中间，
只留 3px 蓝色边框 — 永远在最上面，不会被任何窗口覆盖）。
左键点击捕获，右键/Esc 取消。同时收集 Win32 + UIA 信息。
"""
import ctypes
import ctypes.wintypes as wintypes
import json
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
VK_MBUTTON = 0x04
VK_1 = 0x31; VK_2 = 0x32
SM_CXSCREEN = 0; SM_CYSCREEN = 1
# 虚拟屏（跨多显示器的完整坐标系）：双屏笔记本副屏坐标可能为负或超出主屏宽高，
# 屏幕边界判断必须用虚拟屏而非主屏（tdSelector 同样用 SM_X/Y/CX/CYVIRTUALSCREEN）
SM_XVIRTUALSCREEN = 76; SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78; SM_CYVIRTUALSCREEN = 79
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
# SendMessageTimeout：读目标窗口文本用，目标 UI 线程卡死/鼠标模态态时不再永久阻塞
_SendMessageTimeoutW = _user32.SendMessageTimeoutW
_SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, wintypes.LPWSTR,
                                 wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
_SendMessageTimeoutW.restype = wintypes.LPARAM
WM_GETTEXT = 0x000D; WM_GETTEXTLENGTH = 0x000E
SMTO_ABORTIFHUNG = 0x0002
_WNDTEXT_TIMEOUT_MS = 150
_GetClassNameW = _user32.GetClassNameW
_GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_GetWindowRect = _user32.GetWindowRect
_GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]; _GetWindowRect.restype = wintypes.BOOL
_GetParent = _user32.GetParent
_GetParent.argtypes = [wintypes.HWND]; _GetParent.restype = wintypes.HWND
_GetWindow = _user32.GetWindow
_GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]; _GetWindow.restype = wintypes.HWND
_IsWindowEnabled = _user32.IsWindowEnabled
_IsWindowEnabled.argtypes = [wintypes.HWND]; _IsWindowEnabled.restype = wintypes.BOOL
GW_CHILD = 5; GW_HWNDNEXT = 2
_GetSystemMetrics = _user32.GetSystemMetrics
_GetSystemMetrics.argtypes = [ctypes.c_int]; _GetSystemMetrics.restype = ctypes.c_int

# DPI awareness：双屏笔记本内外屏缩放常不一致（外接 100% / 笔记本 150%），DPI unaware
# 进程坐标会被系统虚拟化导致 hover 框/捕获坐标与真实物理像素错位。设为 Per-Monitor V2
# 让 GetCursorPos/WindowFromPoint/ControlFromPoint/UIA 矩形/截图全链路用物理像素坐标
# （tdSelector 同样 SetProcessDpiAwareness + GetPhysicalCursorPos）。必须最先设置（建窗口前）。
try:
    _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            _user32.SetProcessDPIAware()
        except Exception:
            pass

# DWM (for real visible rect, excluding shadows)
_dwmapi = ctypes.windll.dwmapi
_DwmGetWindowAttribute = _dwmapi.DwmGetWindowAttribute
_DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
_DwmGetWindowAttribute.restype = ctypes.c_long
_DwmFlush = _dwmapi.DwmFlush  # 阻塞到 DWM 完成一次合成（截图前确保边框/悬浮框已从屏幕移除）
_DwmFlush.argtypes = []
_DwmFlush.restype = ctypes.c_long


def _dwm_flush(timeout: float = 0.5):
    """DwmFlush 有界版：极端情况下组合器不应答时不永久阻塞。"""
    def _run():
        try:
            _DwmFlush()
        except Exception:
            pass
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
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
_EnumChildWindows = _user32.EnumChildWindows
_EnumChildWindows.argtypes = [wintypes.HWND, ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
                              wintypes.LPARAM]
_IsWindowVisible = _user32.IsWindowVisible
_IsWindowVisible.argtypes = [wintypes.HWND]; _IsWindowVisible.restype = wintypes.BOOL
_IsIconic = _user32.IsIconic
_IsIconic.argtypes = [wintypes.HWND]; _IsIconic.restype = wintypes.BOOL
_OpenProcess = _kernel32.OpenProcess
_OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_OpenProcess.restype = wintypes.HANDLE
# 跨进程内存读写：桌面图标（SysListView32）单项捕获需要向 explorer 进程发
# LVM_HITTEST/LVM_GETITEMRECT，结构体须分配在目标进程地址空间（tdSelector 同款做法）
_VirtualAllocEx = _kernel32.VirtualAllocEx
_VirtualAllocEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t,
                            wintypes.DWORD, wintypes.DWORD]
_VirtualAllocEx.restype = wintypes.LPVOID
_VirtualFreeEx = _kernel32.VirtualFreeEx
_VirtualFreeEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD]
_VirtualFreeEx.restype = wintypes.BOOL
_WriteProcessMemory = _kernel32.WriteProcessMemory
_WriteProcessMemory.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.LPCVOID,
                                ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
_WriteProcessMemory.restype = wintypes.BOOL
_ReadProcessMemory = _kernel32.ReadProcessMemory
_ReadProcessMemory.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.LPVOID,
                               ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
_ReadProcessMemory.restype = wintypes.BOOL
_CloseHandle = _kernel32.CloseHandle
_CloseHandle.argtypes = [wintypes.HANDLE]; _CloseHandle.restype = wintypes.BOOL
_SendMessageW = _user32.SendMessageW
_SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_SendMessageW.restype = wintypes.LPARAM
_ScreenToClient = _user32.ScreenToClient
_ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
_ScreenToClient.restype = wintypes.BOOL
_ClientToScreen = _user32.ClientToScreen
_ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
_ClientToScreen.restype = wintypes.BOOL
_QueryFullProcessImageNameW = _kernel32.QueryFullProcessImageNameW
_QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
_QueryFullProcessImageNameW.restype = wintypes.BOOL

_advapi32 = ctypes.windll.advapi32
_OpenProcessToken = _advapi32.OpenProcessToken
_OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
_OpenProcessToken.restype = wintypes.BOOL
_GetTokenInformation = _advapi32.GetTokenInformation
_GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                 wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
_GetTokenInformation.restype = wintypes.BOOL
_TokenElevation = 20  # TOKEN_INFORMATION_CLASS.TokenElevation
_shell32 = ctypes.windll.shell32

# 悬浮框：灰色背景 + 白色边框
_FrameRect = _user32.FrameRect
_FrameRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
_FrameRect.restype = ctypes.c_int

# 消息泵（悬浮框窗口保持响应，避免被 Windows 标记未响应/假死）
_PeekMessageW = _user32.PeekMessageW
_PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                          ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
_PeekMessageW.restype = wintypes.BOOL
_TranslateMessage = _user32.TranslateMessage
_TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
_TranslateMessage.restype = wintypes.BOOL
_DispatchMessageW = _user32.DispatchMessageW
_DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
_DispatchMessageW.restype = ctypes.c_long
_ValidateRect = _user32.ValidateRect
_ValidateRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_ValidateRect.restype = wintypes.BOOL
# 独立钩子泵线程：阻塞式 GetMessage（低级钩子消息投递到安装线程队列）
_GetMessageW = _user32.GetMessageW
_GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, ctypes.c_uint, ctypes.c_uint]
_GetMessageW.restype = wintypes.BOOL
_GetCurrentThreadId = _kernel32.GetCurrentThreadId
_GetCurrentThreadId.argtypes = []
_GetCurrentThreadId.restype = wintypes.DWORD
_PostThreadMessageW = _user32.PostThreadMessageW
_PostThreadMessageW.argtypes = [wintypes.DWORD, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
_PostThreadMessageW.restype = wintypes.BOOL
WM_PAINT = 0x000F
WM_QUIT = 0x0012


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
    uia_target_index: int = -1  # uia_path 中目标元素的层级序号（-1=最后一层）
    uia_available: bool = True  # uiautomation 依赖是否可用（False=静默降级为仅 Win32，需提示用户）
    elevation_blocked: bool = False  # 目标进程提权而自身未提权（UIPI 拦截，只能拿到窗口壳）
    win32_path: list = field(default_factory=list)
    css_selector: str = ""
    xpath: str = ""
    tag_name: str = ""
    candidates: list = field(default_factory=list)  # 全部选择器候选
    screenshot: str = ""  # base64
    dom_path: list = field(default_factory=list)  # DOM层级路径
    elem_attrs: dict = field(default_factory=dict)  # 元素属性
    dom_editor_path: list = field(default_factory=list)  # 前端手动编辑 DOM 形态（tag/id/classes/attrs）
    attrs: dict = field(default_factory=dict)  # 元素属性别名（前端 setDomAttrs 用）
    list_info: dict = field(default_factory=dict)  # 列表检测信息
    page_url: str = ""  # 页面 URL（web 元素）
    region: dict = field(default_factory=dict)  # 元素屏幕区域（图像兜底）
    threshold: float = 0.8  # 图像匹配阈值
    match_method: str = "template"  # 图像匹配方法
    screen_size: dict = field(default_factory=dict)  # 捕获时屏幕分辨率


def _get_window_text(hwnd) -> str:
    """读窗口文本（有界）：SendMessageTimeout + ABORTIFHUNG，目标 UI 线程
    卡死或处于鼠标模态态（按住按钮/拖动）时最多等 _WNDTEXT_TIMEOUT_MS 后放弃，
    避免桌面捕获主循环被永久阻塞。"""
    res = ctypes.c_size_t(0)
    ok = _SendMessageTimeoutW(hwnd, WM_GETTEXTLENGTH, 0, None,
                              SMTO_ABORTIFHUNG, _WNDTEXT_TIMEOUT_MS, ctypes.byref(res))
    if not ok:
        return ""
    length = res.value
    if length <= 0 or length > 4096:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    res2 = ctypes.c_size_t(0)
    ok2 = _SendMessageTimeoutW(hwnd, WM_GETTEXT, length + 1, buf,
                               SMTO_ABORTIFHUNG, _WNDTEXT_TIMEOUT_MS, ctypes.byref(res2))
    if not ok2:
        return ""
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


def _hwnd_pid(hwnd) -> int:
    pid = wintypes.DWORD()
    _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _is_process_elevated(pid) -> bool:
    """进程是否以管理员（提升令牌）运行。查询失败按 False 处理（低权限打开高权限进程会失败，
    那恰恰说明目标权限更高）。"""
    if not pid:
        return False
    handle = _OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return True  # 打不开的进程多半权限更高
    try:
        token = wintypes.HANDLE()
        if not _OpenProcessToken(handle, 0x0008, ctypes.byref(token)):  # TOKEN_QUERY
            return False
        try:
            elev = wintypes.DWORD(0)
            size = wintypes.DWORD(0)
            if _GetTokenInformation(token, _TokenElevation,
                                    ctypes.byref(elev), ctypes.sizeof(elev), ctypes.byref(size)):
                return bool(elev.value)
            return False
        finally:
            _kernel32.CloseHandle(token)
    finally:
        _kernel32.CloseHandle(handle)


def _self_elevated() -> bool:
    try:
        return bool(_shell32.IsUserAnAdmin())
    except Exception:
        return False


def _elevation_blocked(hwnd) -> bool:
    """目标窗口进程提权运行而自身未提权 → UIPI 拦截跨权限 UIA/消息读取，
    捕获只能拿到窗口壳。检测此状态以便前端提示用户用管理员身份运行本工具。"""
    if not hwnd:
        return False
    return _is_process_elevated(_hwnd_pid(hwnd)) and not _self_elevated()


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


def _child_class_index(parent, hwnd) -> int:
    """hwnd 在其父窗口下同“类名”子窗口中的 Z 序序号（0 起）。与运行时
    find_child_window(parent, class_name=..., index=idx) 的语义对齐（FindWindowExW 同类名枚举）。"""
    if not parent: return 0
    cls = _get_class_name(hwnd)
    idx = 0; sib = _GetWindow(parent, GW_CHILD)
    guard = 0
    while sib and guard < 2000:
        if _get_class_name(sib) == cls:
            if sib == hwnd: return idx
            idx += 1
        sib = _GetWindow(sib, GW_HWNDNEXT)
        guard += 1
    return idx


def _get_ancestor_path(hwnd, with_title: bool = True) -> list:
    # with_title=False（hover 显示路径用）：跳过每层的 SendMessageTimeout 跨进程文本读取，
    # 全部本地调用（GetClassNameW/GetWindowRect/_child_class_index），hover 主循环零阻塞。
    path = []; cur = hwnd; visited = set()
    while cur and cur not in visited:
        visited.add(cur)
        parent = _GetParent(cur)
        node = {"hwnd": cur, "class_name": _get_class_name(cur),
                "title": _get_window_text(cur) if with_title else "",
                "rect": _get_window_rect(cur),
                "enabled": bool(_IsWindowEnabled(cur)), "visible": bool(_IsWindowVisible(cur))}
        node["index"] = _child_class_index(parent, cur) if parent else 0
        path.insert(0, node)
        if not parent: break
        cur = parent
    return path


def _is_browser_window(cls: str) -> bool:
    return any(c in cls for c in (
        "Chrome_WidgetWin_1", "MozillaWindowClass", "ApplicationFrameWindow",
    ))


def _is_browserish_hwnd(hwnd) -> bool:
    """hwnd 或其祖先链是否浏览器窗口（含 Chrome_RenderWidgetHostHWND 渲染宿主）。
    仅本地 GetClassName/GetParent，hover 热路径可用。"""
    cur = hwnd
    for _ in range(6):
        if not cur:
            break
        cls = _get_class_name(cur)
        if _is_browser_window(cls) or "Chrome_RenderWidgetHostHWND" in cls:
            return True
        cur = _GetParent(cur)
    return False


_uia_import_ok = None  # 缓存 uiautomation 依赖探测结果


def _uia_dependency_ok() -> bool:
    """uiautomation 依赖是否可用（首次调用缓存结果）。缺失时 UIA 通道静默失效，
    通过 ElementInfo.uia_available=False 暴露给前端提示，不再无声降级。"""
    global _uia_import_ok
    if _uia_import_ok is None:
        try:
            import uiautomation  # noqa: F401
            _uia_import_ok = True
        except Exception:
            _uia_import_ok = False
    return _uia_import_ok


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
    keep_alive = [ctrl]  # 持有访问过的 Control 强引用，防 GC 后 id() 复用导致 seen 误判
    for _ in range(20):
        if not cur or id(cur) in seen:
            break
        seen.add(id(cur))
        keep_alive.append(cur)
        try:
            br = cur.BoundingRectangle
        except Exception:
            br = None
        rect = {}
        if br:
            rect = {"left": br.left, "top": br.top, "right": br.right, "bottom": br.bottom,
                    "width": br.width(), "height": br.height()}
        node = {
            "name": cur.Name or "", "class_name": cur.ClassName or "",
            "control_type": cur.ControlTypeName or "", "automation_id": cur.AutomationId or "",
            "rect": rect,
        }
        try:
            node["enabled"] = bool(cur.IsEnabled)
        except Exception:
            pass
        try:
            node["is_off_screen"] = bool(cur.IsOffscreen)
        except Exception:
            pass
        chain.append(node)
        try:
            p = cur.GetParentControl()
            if not p or p.ControlTypeName == "DesktopControl":
                break
            # 兄弟序号：cur 在 p 的直接子级中第几个（0 起），用 RuntimeId 定位
            try:
                rid = cur.GetRuntimeId()
                sibs = p.GetChildren()
                for i, s in enumerate(sibs):
                    if s.GetRuntimeId() == rid:
                        node["index"] = i
                        break
            except Exception:
                pass
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


_ARIA_ROLE_PROP = 30101
_ARIA_PROPS_PROP = 30102


def _uia_aria(node) -> tuple[str, dict]:
    """读 UIA 节点的 AriaRole / AriaProperties（网页 DOM 元素才有语义）。

    AriaProperties 是 JSON 风格字符串（如 {"label":"提交","checked":"true"}），
    解析为 dict；解析失败退回空 dict。任何异常都安全返回缺省。
    """
    role = ""
    props = {}
    try:
        role = node.GetPropertyValue(_ARIA_ROLE_PROP) or ""
    except Exception:
        role = ""
    try:
        raw = node.GetPropertyValue(_ARIA_PROPS_PROP) or ""
        if raw:
            props = json.loads(raw)
            if not isinstance(props, dict):
                props = {}
    except Exception:
        props = {}
    return role, props


def _uia_node_dict(node, read_aria: bool = True) -> dict:
    """把 UIA 控件转为可序列化字典（name/class/type/automation_id/rect/enabled/offscreen）。

    read_aria 时额外读 AriaRole/AriaProperties（供网页元素转 CSS/XPath 选择器用）；
    hover 高频路径若走这里可传 False 跳过。
    """
    try:
        br = node.BoundingRectangle
    except Exception:
        br = None
    rect = {}
    if br:
        rect = {"left": br.left, "top": br.top, "right": br.right, "bottom": br.bottom,
                "width": br.width(), "height": br.height()}
    d = {
        "name": node.Name or "", "class_name": node.ClassName or "",
        "control_type": node.ControlTypeName or "", "automation_id": node.AutomationId or "",
        "rect": rect,
    }
    if read_aria:
        role, props = _uia_aria(node)
        if role:
            d["aria_role"] = role
        if props:
            d["aria_props"] = props
    try:
        d["enabled"] = bool(node.IsEnabled)
    except Exception:
        pass
    try:
        d["is_off_screen"] = bool(node.IsOffscreen)
    except Exception:
        pass
    return d


def _deepest_uia_element(x, y, uia, max_depth=8, max_nodes=400):
    """从窗口根有界遍历，找「rect 含光标 (x,y) 的最小/最有价值元素」。

    混合架构应用（XAML island：hit-test 返回 0x0 占位）的兜底方案：
      - 根 = ElementFromHandle(WindowFromPoint)，不 hit-test
      - 不按节点 rect 剪枝（父节点可能 0x0/无效，但子树里有有效元素）
      - **含光标的子节点优先 DFS**：纯 BFS 在大树（Windows Terminal 等）上会在
        max_nodes 预算内访问不到深层 tab/text 节点 → 概率性命中。把含点子节点排在
        栈顶（先访问），沿含点链一路下钻，O(深度) 即可触达最深元素；不含点的兄弟
        仍入栈兜底（预算内），不丢失"父 0x0 子有效"的分支。
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
    keep_alive = [root]  # 持有所有访问过的 Control 强引用：uiautomation 节点是临时
    # wrapper，GC 后 id() 会被新对象复用 → seen/parents 误判导致整棵子树被剪掉
    nodes = 0
    while stack and nodes < max_nodes:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        keep_alive.append(node)
        nodes += 1
        try:
            br = node.BoundingRectangle
        except Exception:
            br = None
        node_contains = bool(br) and br.width() > 0 and br.height() > 0 \
            and (br.left <= x <= br.right and br.top <= y <= br.bottom)
        if node_contains:
            candidates.append((node, _uia_node_dict(node)))
        try:
            kids = node.GetChildren()
        except Exception:
            kids = []
        # 只有「含光标的节点」的子级才读 rect 做含点优先排序（沿含点链 DFS 下钻，
        # O(深度×兄弟数) 触达最深元素）；不含点节点的子级直接入栈（不读 rect）——
        # 否则浏览器等大树（DOM 数千节点）每个子节点一次跨进程 rect 读取会爆到 5s 级。
        containing = []
        others = []
        for k in kids:
            keep_alive.append(k)  # 子节点入栈前同样持引用，防 id 复用
            if id(k) not in seen:
                parents[id(k)] = node
            if node_contains:
                try:
                    kbr = k.BoundingRectangle
                except Exception:
                    kbr = None
                if kbr and kbr.width() > 0 and kbr.height() > 0 \
                        and (kbr.left <= x <= kbr.right and kbr.top <= y <= kbr.bottom):
                    containing.append(k)
                    continue
            others.append(k)
        # 栈是 LIFO：先压不含点的（后处理），再压含点的（先处理）→ 沿含点链 DFS 下钻
        stack.extend(others)
        stack.extend(reversed(containing))
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
    path = []
    for pos, c in enumerate(rev):
        d = _uia_node_dict(c)
        if pos > 0:
            # 兄弟序号：c 在其父级直接子级中第几个（0 起）
            parent = rev[pos - 1]
            try:
                rid = c.GetRuntimeId()
                for i, s in enumerate(parent.GetChildren()):
                    if s.GetRuntimeId() == rid:
                        d["index"] = i
                        break
            except Exception:
                pass
        path.append(d)
    return best_dict, path


# ---------------------------------------------------------------------------
# UIA 无障碍树网页拾取（tdSelector 同款机制，不依赖扩展/后端/CDP 端口）
#
# Edge/Chrome 把网页 DOM 暴露为 UIA 无障碍树：渲染根 Chrome_RenderWidgetHostHWND
# （Name='Chrome Legacy Window'）之下的节点即网页元素（role=EditControl 的输入框、
# class=DOM 类名的容器等）。用 UIA 深搜"含光标的最深有价值节点"即可拾取网页元素，
# 生成与 tdSelector 同款特征链（aaRole/ClassName/Text/AutomationId/兄弟序号）。
# ---------------------------------------------------------------------------

# 网页 DOM 节点在 UIA 树中的角色集合（Chromium 无障碍树典型值）
_WEB_DOM_ROLES = {
    "EditControl", "ButtonControl", "HyperlinkControl", "TextControl",
    "ComboBoxControl", "CheckBoxControl", "RadioButtonControl", "ListItemControl",
    "TreeItemControl", "ImageControl", "GroupControl", "CustomControl",
    "SliderControl", "ProgressBarControl", "TabItemControl", "SplitButtonControl",
}
# 网页交互型控件：同为"含点候选"时优先选它们（textarea/按钮/链接 优于容器 div/section）
_WEB_INTERACTIVE_TYPES = {
    "EditControl", "ButtonControl", "SplitButtonControl", "HyperlinkControl",
    "ComboBoxControl", "CheckBoxControl", "RadioButtonControl", "TreeItemControl",
    "ListItemControl", "TabItemControl", "MenuItemControl", "SliderControl",
}
# 浏览器 UI 骨架类名（非 DOM，跳过避免把工具栏当网页元素）
_BROWSER_UI_CLASSES = (
    "BrowserRootView", "NonClientView", "EdgeBrowserFrameViewWin", "BrowserView",
    "MainBackgroundRegionView", "TopContainerView", "EdgeToolbarView", "LocationBarView",
    "OmniboxViewViews", "EdgeTabContainerImpl", "TabStrip", "BrowserCaptionButtonContainer",
    "EdgeWindowsCaptionButton", "WorkspacesButton", "SpaceworkButton", "SidePaneRootContainer",
    "EdgeContentsContainerBorder", "InkDropContainerView", "EdgeExtensionsToolbarContainer",
    "PinnedToolbarActionsContainer", "CollaboratorsPhotosContainer",
)


def _is_web_dom_node(node, uia) -> bool:
    """节点是否像网页 DOM 元素（排除浏览器 UI 骨架 + 捕获 Chromium 原生窗口外壳）。"""
    try:
        cls = node.ClassName or ""
    except Exception:
        cls = ""
    if any(b in cls for b in _BROWSER_UI_CLASSES):
        return False
    try:
        role = node.ControlTypeName or ""
    except Exception:
        role = ""
    if role == "WindowControl":
        return False  # 顶层/渲染外壳窗口不算 DOM 元素
    return True


def _uia_web_dom_at(x, y, uia, max_depth=40, max_nodes=1500):
    """UIA 无障碍树深搜：找含光标 (x,y) 的最深、最有价值的网页 DOM 节点。

    返回 (leaf_dict, path[根→叶]) 或 (None, None)：
      - leaf_dict：目标节点特征（name/class_name/control_type/automation_id/rect/index）
      - path：完整祖先链（根=渲染根，叶=目标），与 tdSelector 输出同构
    从 ElementFromPoint 得到的节点向上爬到渲染根，再从渲染根向下做
    "含光标优先 DFS" —— 沿含点链直达最深 DOM 节点（O(深度×兄弟数)），
    同时保留不含点分支兜底（预算内），避免错过大树中的有效元素。
    """
    try:
        start = uia.ControlFromPoint(x, y)
    except Exception:
        return None, None
    if not start:
        return None, None
    # 1) 向上爬到渲染根（Chrome_RenderWidgetHostHWND / 网页 DOM 链顶）
    root = start
    keep = [start]
    guard = 0
    while guard < 30:
        try:
            p = root.GetParentControl()
        except Exception:
            p = None
        if not p or p.ControlTypeName == "DesktopControl":
            break
        keep.append(p)
        root = p
        guard += 1

    # 2) 从渲染根做含光标优先 DFS（复用 _deepest_uia_element 的策略，但节点语义为 DOM）
    candidates = []
    parents = {}
    stack = [root]
    seen = set()
    nodes = 0
    while stack and nodes < max_nodes:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        keep.append(node)
        nodes += 1
        try:
            br = node.BoundingRectangle
        except Exception:
            br = None
        contains = bool(br) and br.width() > 0 and br.height() > 0 \
            and (br.left <= x <= br.right and br.top <= y <= br.bottom)
        if contains and _is_web_dom_node(node, uia):
            candidates.append((node, _uia_node_dict(node)))
        try:
            kids = node.GetChildren()
        except Exception:
            kids = []
        containing, others = [], []
        for k in kids:
            keep.append(k)
            if id(k) not in seen:
                parents[id(k)] = node
            if contains:
                try:
                    kbr = k.BoundingRectangle
                except Exception:
                    kbr = None
                if kbr and kbr.width() > 0 and kbr.height() > 0 \
                        and (kbr.left <= x <= kbr.right and kbr.top <= y <= kbr.bottom):
                    containing.append(k)
                    continue
            others.append(k)
        stack.extend(others)
        stack.extend(reversed(containing))

    if not candidates:
        return None, None
    # 选目标节点：网页 DOM 里叶子通常是用户真正点中的元素，且 Chromium 无障碍树角色有限，
    # 打分区分度低。取"含点 + DOM 节点"中最深者；深度相近（≤2 层）时优先交互控件
    # （textarea/按钮/链接 等），避免误选包住它们的纯容器（section/div）。
    max_dep = max(len(_uia_parent_chain(c[0], parents)) for c in candidates)

    def _leaf_key(c):
        node, d = c
        chain_len = len(_uia_parent_chain(node, parents))
        interactive = int((d.get("control_type") or "") in _WEB_INTERACTIVE_TYPES)
        # 深度权重为主；在离最深 ≤2 层内，交互控件排前
        if chain_len >= max_dep - 2:
            return (chain_len, interactive, 0)
        return (chain_len - 5, interactive, 0)

    best_node, best_dict = max(candidates, key=_leaf_key)
    # 组装根→叶路径
    rev = []
    cur = best_node
    g2 = 0
    while cur is not None and g2 < 40:
        rev.append(cur)
        cur = parents.get(id(cur))
        g2 += 1
    rev.reverse()
    path = []
    for pos, c in enumerate(rev):
        d = _uia_node_dict(c)
        if pos > 0:
            parent = rev[pos - 1]
            try:
                rid = c.GetRuntimeId()
                for i, s in enumerate(parent.GetChildren()):
                    if s.GetRuntimeId() == rid:
                        d["index"] = i
                        break
            except Exception:
                pass
        path.append(d)
    return best_dict, path


def _uia_parent_chain(node, parents) -> list:
    chain = []
    cur = node
    g = 0
    while cur is not None and g < 40:
        chain.append(id(cur))
        cur = parents.get(id(cur))
        g += 1
    return chain


def _uia_web_capture(x, y) -> dict | None:
    """浏览器内容区 UIA 网页拾取入口（限时工作线程执行）。

    返回捕获 dict（与扩展捕获结果同构，供 _build_element_info 消费）：
      {found, name, class_name, control_type, automation_id, rect, path, target_index,
       element_type:"web", css_selector, xpath, candidates:[...], dom_path, page_url?}
    非浏览器区域 / 无 DOM 命中 → None（调用方回退扩展或桌面通道）。
    """
    result = {"done": False, "value": None}

    def _run():
        try:
            import uiautomation as uia
            with uia.UIAutomationInitializerInThread():
                leaf, path = _uia_web_dom_at(x, y, uia)
                if leaf and path and len(path) >= 2:  # 至少 渲染根 + 一个 DOM 节点
                    r = leaf.get("rect") or {}
                    if r.get("width", 0) > 0 and r.get("height", 0) > 0:
                        # UIA → CSS/XPath 选择器生成（本地捕获脱离扩展的关键）
                        try:
                            from scripts.capture_gui.web_selector import generate_selectors
                            cands = generate_selectors(leaf)
                        except Exception:
                            cands = []
                        css = next((c["syntax"] for c in cands
                                    if c["family"] == "css" and c.get("syntax")), "")
                        xpath = next((c["syntax"] for c in cands
                                      if c["family"] == "xpath" and c.get("syntax")), "")
                        attrs = {
                            "tag": (leaf.get("aria_role") or leaf.get("control_type") or "").strip(),
                            "role": leaf.get("aria_role", ""),
                            "class": leaf.get("class_name", ""),
                            "id": leaf.get("automation_id", ""),
                            "name": leaf.get("name", ""),
                        }
                        # 前端手动编辑 DOM 层级期望的节点形态：{tag,id,classes[],attrs{}}。
                        # UIA 的 dom_path（role/class/…）转成该形态，让"手动编辑"tab 也能用。
                        dom_editor = _uia_dom_for_editor(path)
                        editor_attrs = dict(attrs)
                        editor_attrs.setdefault("tag", _uia_tag_of(leaf))
                        result["value"] = {
                            "found": True,
                            "element_type": "web",
                            "name": leaf.get("name", ""),
                            "class_name": leaf.get("class_name", ""),
                            "control_type": leaf.get("control_type", ""),
                            "automation_id": leaf.get("automation_id", ""),
                            "rect": r,
                            "path": path,
                            "target_index": len(path) - 1,
                            "dom_path": path,              # 原始 UIA 链（供 normalize）
                            "dom_editor_path": dom_editor,  # 前端手动编辑形态
                            "css_selector": css,
                            "xpath": xpath,
                            "candidates": cands,
                            "elem_attrs": attrs,
                            "attrs": editor_attrs,          # 前端 setDomAttrs(data.attrs) 用
                        }
        except Exception:
            pass
        finally:
            result["done"] = True

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(_UIA_QUERY_TIMEOUT)
    return result["value"] if result["done"] else None


_UIA_QUERY_TIMEOUT = 8.0  # 秒；深搜兜底在 XAML 应用（Windows Terminal/PowerShell）上可达 1-5s，
                          # 3s 会把正常深搜杀掉 → 捕获降级成整窗。正常捕获优先复用 hover worker
                          # 结果，此超时只是 worker 结果缺失时的兜底。


# 前端手动编辑 tab 的展示标签：role → 常见 HTML 标签（仅用于层级树展示与选择器拼接）
_ROLE_TO_TAG = {
    "button": "button", "link": "a", "textbox": "input", "searchbox": "input",
    "checkbox": "input", "radio": "input", "img": "img", "tab": "a",
    "treeitem": "li", "option": "option", "slider": "input", "combobox": "input",
    "listbox": "select", "menuitem": "li",
}


def _uia_tag_of(node: dict) -> str:
    """UIA 特征 → HTML 标签（粗映射，供前端手动编辑 DOM 层级展示用）。"""
    role = (node.get("aria_role") or "").strip().lower()
    if role in _ROLE_TO_TAG:
        return _ROLE_TO_TAG[role]
    try:
        from scripts.capture_gui.web_selector import _CONTROL_TYPE_TAG
        tag = _CONTROL_TYPE_TAG.get((node.get("control_type") or ""), "div")
    except Exception:
        return "div"
    # _CONTROL_TYPE_TAG 可能返回 [role=x] 形式 → 转纯标签
    return tag.lstrip("[]").split("=")[0] if tag.startswith("[") else tag


def _uia_dom_for_editor(path: list) -> list:
    """把 UIA 的 dom_path（原始链）转成前端"手动编辑"tab 期望的节点形态。

    前端 updateDomSel 逐节点用 n.tag / n.id / n.classes[] / n.attrs{} 拼选择器。
    UIA 节点是 {control_type, class_name, automation_id, name, rect, aria_role...}，
    这里做同构映射，让本地捕获的网页元素在"手动编辑"tab 也能正常渲染与编辑。
    """
    out = []
    for node in path or []:
        if not isinstance(node, dict):
            out.append(node)
            continue
        cls = (node.get("class_name") or "").split()
        node_attrs = {}
        if node.get("automation_id"):
            node_attrs["id"] = node["automation_id"]
        role = node.get("aria_role")
        if role:
            node_attrs["role"] = role
        if node.get("name"):
            node_attrs["aria-label"] = node["name"]
        out.append({
            "tag": _uia_tag_of(node),
            "id": node.get("automation_id") or "",
            "classes": cls,
            "attrs": node_attrs,
            "name": node.get("name", ""),
            "control_type": node.get("control_type", ""),
        })
    return out


def _web_display_name(web: dict) -> str:
    """网页元素的显示名：叶子无可访问名时，用 class / id / 控件类型生成可读名。

    不可用窗口标题（浏览器顶层 "Chrome Legacy Window"）——那是窗口名不是元素名。
    """
    leaf = (web.get("dom_path") or [{}])[-1] if web.get("dom_path") else {}
    if not isinstance(leaf, dict):
        leaf = {}
    aid = (leaf.get("automation_id") or web.get("automation_id") or "").strip()
    if aid:
        return f"#{aid}"
    cls = (leaf.get("class_name") or web.get("class_name") or "").strip()
    if cls:
        return ".".join(cls.split()[:2])
    ct = (leaf.get("control_type") or web.get("control_type") or "").strip()
    if ct:
        return ct[:-len("Control")] if ct.endswith("Control") else ct
    return "网页元素"


def _try_uia_capture(x, y) -> dict | None:
    """UIA 捕获（祖先链 + 打分选优；hit-test 失效时深搜兜底）。
    在工作线程执行并限时，超时 → 返回 None（本次降级，不永久拉黑进程）。
    注意：不要在超时时把进程加入 _uia_skip_exes —— Windows Terminal 等正常应用
    的 UIA provider 偶发查询慢（>3s），若因此永久跳过 UIA，整个会话的 hover 高亮
    会全部退化为整窗（tab/内部元素全是纯 UIA，无独立 HWND）。微信族的防卡死由
    _is_skip_uia 里的硬编码 wechat/weixin/wework 检测负责，不需要这里兜底。"""
    result = {"done": False, "value": None}

    def _run():
        try:
            import uiautomation as uia
            with uia.UIAutomationInitializerInThread():  # 工作线程必须各自初始化 COM
                chain = _uia_chain_at(x, y, uia)
                item, idx = _best_uia_item(chain)
                path = None
                target_index = -1
                if item:
                    r = item.get("rect") or {}
                    if r.get("width", 0) > 0 and r.get("height", 0) > 0:
                        path = list(reversed(chain))  # 完整 根 → 叶（不再截断到最优，便于前端选层级）
                        target_index = len(chain) - 1 - idx  # 最优元素在 path 中的位置
                        # 最优元素 ≈ 整窗 → 深搜找细粒度
                        hwnd = _WindowFromPoint(wintypes.POINT(x, y))
                        if hwnd:
                            wr = _get_window_rect(hwnd)
                            if wr["width"] > 0 and wr["height"] > 0 \
                                    and r.get("width", 0) * r.get("height", 0) > 0.6 * wr["width"] * wr["height"]:
                                path = None
                if not path:
                    # hit-test 不可用（0x0/None）或整窗 → 深搜兜底（混合架构应用）。
                    # 浏览器窗口例外：内容区是 DOM（不在 UIA 树），深搜只能遍历数千节点
                    # （实测 4-6s 超时）且找不到更细的 → 放弃深搜回退整窗，网页细粒度
                    # 走「捕获网页元素」通道。
                    _hwnd = _WindowFromPoint(wintypes.POINT(x, y))
                    if _hwnd and _is_browserish_hwnd(_hwnd):
                        item, path = None, None
                    else:
                        item, path = _deepest_uia_element(x, y, uia)
                    target_index = len(path) - 1 if path else -1  # 深搜路径终点即目标
                if item and path:
                    result["value"] = {
                        "found": True,
                        "name": item.get("name", ""), "class_name": item.get("class_name", ""),
                        "control_type": item.get("control_type", ""), "automation_id": item.get("automation_id", ""),
                        "rect": item.get("rect", {}), "path": path, "target_index": target_index,
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
    # 超时：UIA provider 偶发卡住 → 本次返回 None（降级为仅 Win32），不永久拉黑进程
    return None




def _uia_hit_rect(x, y, uia):
    """UIA 命中框 + 捕获信息（纯同步查询，无内部线程/超时）：轻量 hit-test 优先；
    hit-test 失效（0x0/None，XAML island 等混合应用）时深搜兜底（节流缓存，避免每帧
    全树遍历）。

    返回 (rect, info)：
      - rect：hover 高亮用（只读矩形）。
      - info：深搜算出的**完整捕获信息**（name/control_type/automation_id/path/
        target_index，与 _try_uia_capture 同构），供捕获直接复用 —— 深搜慢（XAML 应用
        1-5s），捕获时若重新查会撞 3s 超时降级成整窗（"框到 tab、捕获整窗"），而 worker
        在 hover 期间已经算好了。快速命中（非整窗）或浏览器整窗时不深搜 → info 为 None，
        捕获走自身快速查询即可。
    本函数可能被单次卡死的 UIA 调用（ControlFromPoint/GetChildren）永久阻塞，
    因此**只能在 _HoverWorker 常驻线程调用**。"""
    # 1) 轻量 hit-test（正常应用，O(1)）
    try:
        ctrl = uia.ControlFromPoint(x, y)
        if ctrl:
            br = ctrl.BoundingRectangle
            if br and br.width() > 0 and br.height() > 0:
                hit = {"left": br.left, "top": br.top, "right": br.right, "bottom": br.bottom,
                       "width": br.width(), "height": br.height()}
                # 命中≈整窗（面积 >60% 窗口）视为粗命中，不直接返回 —— Windows Terminal 等
                # XAML 应用的 ControlFromPoint 常返回整窗大的 pane（有效矩形），直接采纳
                # 会让 hover 永远停在整窗（实测：大部分情况框整窗，仅偶尔 0x0 才走深搜
                # 拿到 tab/文字 = "概率性细粒度"）。落入深搜兜底拿真实细粒度元素。
                # 例外：浏览器窗口（Chrome_RenderWidgetHostHWND 等）内容区是 DOM 不在 UIA
                # 树里，深搜只能遍历数千 DOM 节点（实测 5.9s）且找不到更细的 → 直接接受整窗。
                hwnd0 = _WindowFromPoint(wintypes.POINT(x, y))
                wr = _get_window_rect(hwnd0) if hwnd0 else None
                is_window_sized = bool(wr) and wr["width"] > 0 and wr["height"] > 0 and \
                    hit["width"] * hit["height"] > 0.6 * wr["width"] * wr["height"]
                if is_window_sized and _is_browserish_hwnd(hwnd0):
                    _deep_cache["hwnd"] = 0
                    return hit, None
                if not is_window_sized:
                    _deep_cache["hwnd"] = 0  # 清深搜缓存
                    return hit, None
    except Exception:
        pass
    # 2) 深搜兜底（节流：窗口/位移 >15px 或 >0.4s 才重算）
    hwnd = _WindowFromPoint(wintypes.POINT(x, y))
    # 浏览器窗口不深搜：内容区是 DOM（不在 UIA 树），深搜只能遍历数千节点（实测 4-6s）
    # 且找不到更细的 —— hover 用整窗兜底即可，细粒度网页元素走「捕获网页元素」通道。
    if hwnd and _is_browserish_hwnd(hwnd):
        return None, None
    now = time.time()
    c = _deep_cache
    if (hwnd != c["hwnd"] or abs(x - c["x"]) > 15 or abs(y - c["y"]) > 15 or now - c["t"] > 0.4):
        item, path = _deepest_uia_element(x, y, uia, max_nodes=200)
        rect = None
        info = None
        if item:
            r = item.get("rect") or {}
            if r.get("width", 0) > 0:
                rect = r
                info = _deep_info_to_capture(item, path)
        c.update(hwnd=hwnd, x=x, y=y, t=now, rect=rect, info=info)
    return c.get("rect"), c.get("info")


def _deep_info_to_capture(item: dict, path: list) -> dict:
    """深搜结果 (best_dict, path) → 捕获信息 dict（与 _try_uia_capture 返回同构）。

    让捕获直接复用 hover worker 已算好的深搜结果 —— 显示什么就捕获什么，且不再
    触发一次可能超时的重查。"""
    return {
        "found": True,
        "name": item.get("name", ""), "class_name": item.get("class_name", ""),
        "control_type": item.get("control_type", ""), "automation_id": item.get("automation_id", ""),
        "rect": item.get("rect", {}),
        "path": path or [],
        "target_index": len(path) - 1 if path else -1,
    }


# worker 的 UIA hit-test 与主循环窗口绘制（show_border/show_info）的互斥锁：
# 两者都需 DWM 配合，并发会互相饿死（实测 diag_interfere：主循环画 border 时 worker 的
# ControlFromPoint 永久卡死）。严格串行后 worker 查询回到 <0.5s，主循环绘制几乎不被延迟。
_uia_draw_lock = threading.Lock()


class _HoverWorker:
    """后台 hover UIA 查询 worker —— 常驻线程一次性 init COM 后直接查询，主循环零阻塞。

    设计要点（经真机实测校准）：
    - 主循环只把最新鼠标坐标写进共享状态 + 读 worker 最新结果，绝不等待 → hover 不卡。
    - worker 常驻线程 init COM 一次后**直接同步调 `_uia_hit_rect`**。实测（diag_resident）：
      常驻线程 hit-test 1~39ms；XAML island 应用（Windows Terminal）hit-test 失效走深搜，
      深搜慢（1~5s，遍历整棵 XAML 树）但**会返回** —— 这是 UIA provider 的物理特性。
    - **不要给单次查询加超时/外包线程**：实测（diag_comthread）每次新建线程 init COM 的
      首次 UIA 调用反而更慢/易卡，且超时会杀掉正常慢深搜 → 永远框不出细粒度（tab）。
      外包僵尸线程还会并发打爆 provider。慢就让 worker 后台慢慢算，算完写 `_res`，
      主循环下一帧读到即切换细粒度；期间由 `_get_best_rect` 用 Win32 整窗兜底，
      蓝框始终跟随鼠标（不会"卡住不动"）。
    - 偶发"真·永久卡死"（UIA provider 挂死永不返回）会导致 latest 冻结：此时主循环仍
      流畅（整窗兜底），用户 Esc 取消后 `run_capture` finally 会 `_stop_hover_worker()`，
      下次捕获重建 worker 即恢复。

    mouse_down（SetCapture 模态态）期间暂停查询：此时跨进程 UIA 调用会无限等待，
    先冻结当前结果，松开后再继续。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._paused = False
        # 主循环写入：最新坐标 + 是否有效
        self._req = {"x": 0, "y": 0, "valid": False, "seq": 0}
        # worker 写出：最新结果（rect 供高亮，info 供捕获复用 —— 显示什么捕获什么）
        self._res = {"rect": None, "info": None, "x": 0, "y": 0}
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        try:
            import uiautomation as uia
            with uia.UIAutomationInitializerInThread():  # worker 常驻线程一次性 init COM
                last_seq = 0  # 上次处理的 submit 序号：只在坐标更新（新 submit）时查询，
                # wait 超时（无新坐标）不重复查 —— 否则每 0.2s 重复深搜同坐标，持续打满
                # UIA provider，把单次深搜从 0.3s 拖到 8s+（实测独立深搜仅 0.3s）。
                while not self._stop:
                    self._wake.wait(timeout=0.2)
                    self._wake.clear()
                    if self._stop:
                        break
                    if self._paused:
                        continue
                    with self._lock:
                        req = dict(self._req)
                    if not req["valid"] or req["seq"] == last_seq:
                        continue  # 无新坐标，不重复查询
                    # 防御：屏幕外坐标不查询（详见 _get_uia_rect 注释 —— ControlFromPoint 对
                    # 屏幕外点永久卡死，会占死锁内 worker）。跳过并推进 last_seq 防重复判断。
                    # 用虚拟屏边界（多显示器副屏坐标可能为负），否则会误拦双屏 hover。
                    if not _in_virtual_screen(req["x"], req["y"]):
                        last_seq = req["seq"]
                        continue
                    last_seq = req["seq"]
                    # 直接在本线程查询（COM 已初始化）。深搜慢也只影响结果更新时机，
                    # 主循环始终用最近一次结果 + 整窗兜底 → 不卡。
                    # 互斥锁：worker 的 UIA hit-test 与主循环的窗口绘制严格串行（不同时），
                    # 否则主循环窗口操作会饿死 worker 的 ControlFromPoint（实测 diag_interfere）。
                    with _uia_draw_lock:
                        rect, info = self._query(req["x"], req["y"], uia)
                    with self._lock:
                        # 结果总是写回（即使查询期间鼠标已移动）：是否采纳由读取方
                        # _get_uia_rect 按"当前光标是否仍在结果矩形内"判断。旧逻辑按坐标
                        # 丢弃，深搜慢的应用（Windows Terminal 300ms+）期间鼠标微动就丢
                        # 结果 → hover 概率性退化为整窗。
                        self._res = {"rect": rect, "info": info, "x": req["x"], "y": req["y"]}
        except Exception:
            pass

    def _query(self, x, y, uia):
        """在 worker 常驻线程内执行查询（COM 已初始化）。返回 (rect, info)。

        info 与最终采纳的 rect 配对：滞回保留旧 rect 时，info 也用旧结果的 ——
        否则会出现"高亮框着 tab、捕获信息却是整窗"的不一致。"""
        try:
            rect, info = _uia_hit_rect(x, y, uia)
        except Exception:
            rect, info = None, None
        final_rect = self._hysteresis(x, y, rect)
        if final_rect is not rect:
            # 滞回保留了旧 rect：info 必须跟显示的高亮一致
            info = self._res.get("info")
        return final_rect, info

    def _hysteresis(self, x, y, new_rect):
        """滞回：防止"细粒度 → 整窗"的跳变。

        深搜兜底是概率性的（max_nodes 预算内访问不到深层 tab/text 节点就返回较粗的
        元素）。当鼠标在 tab/文字内微动触发重查，若新结果是一块明显更粗（面积大很多）
        的元素，但光标仍在旧细粒度结果矩形内，就**保留旧结果** —— 否则高亮会跳回整窗
        （整窗矩形总包含光标，读取方的 containment 检查挡不住这种降级）。"""
        old = self._res.get("rect")
        if not new_rect or new_rect.get("width", 0) <= 0:
            # 新查询无效：旧结果仍包含光标就继续沿用
            if old and _rect_contains(old, x, y):
                return old
            return new_rect
        if old and old.get("width", 0) > 0 and _rect_contains(old, x, y):
            old_area = old["width"] * old["height"]
            new_area = new_rect["width"] * new_rect["height"]
            if new_area >= 4 * old_area:  # 明显变粗 → 不降级
                return old
        return new_rect

    def submit(self, x, y):
        """主循环每帧提交最新鼠标坐标（非阻塞）。"""
        with self._lock:
            self._req = {"x": x, "y": y, "valid": True, "seq": self._req["seq"] + 1}
        self._wake.set()

    def latest(self):
        """主循环每帧读最新结果（非阻塞）。"""
        with self._lock:
            return dict(self._res)

    def pause(self):
        """鼠标按住（模态态）时暂停 UIA 查询，避免跨进程调用卡死。"""
        self._paused = True

    def resume(self):
        self._paused = False
        self._wake.set()

    def stop(self):
        self._stop = True
        self._wake.set()


_hover_worker_inst: _HoverWorker | None = None


def _hover_worker() -> _HoverWorker | None:
    """懒启动全局 hover worker。uiautomation 不可用时返回 None。"""
    global _hover_worker_inst
    if _hover_worker_inst is None:
        if not _uia_dependency_ok():
            return None
        _hover_worker_inst = _HoverWorker()
    return _hover_worker_inst


def _stop_hover_worker():
    global _hover_worker_inst, _last_submit_xy
    if _hover_worker_inst is not None:
        try:
            _hover_worker_inst.stop()
        except Exception:
            pass
        _hover_worker_inst = None
    # 重置 submit 坐标：否则下次重建 worker 时若鼠标坐标与上次相同，
    # `(x,y) != _last_submit_xy[0]` 恒 False → 新 worker 收不到首个坐标 → hover 无高亮
    # （多轮捕获：第一轮 Alt+点击后光标几乎没动就进第二轮，必踩此坑）。
    _last_submit_xy[0] = None


def _rect_contains(r, x, y, tol=2):
    """点 (x,y) 是否在矩形 r 内（±tol 容差）。r 为 None 或空矩形返回 False。"""
    if not r or r.get("width", 0) <= 0 or r.get("height", 0) <= 0:
        return False
    return (r["left"] - tol <= x <= r["left"] + r["width"] + tol and
            r["top"] - tol <= y <= r["top"] + r["height"] + tol)


def _get_uia_rect(x, y):
    """悬停 UIA 命中框（异步非阻塞）。返回后台 worker 的最新结果；还没出结果时返回 None。

    主循环绝不阻塞等待 UIA 查询 —— 这是 hover 卡顿的关键：旧实现每帧开新线程 +
    join(超时) 阻塞主循环，Windows Terminal 深搜偶发 >1s 时帧率骤降。改为：主循环
    每帧只 submit 坐标、读最新结果；worker 线程独立做查询。"""
    w = _hover_worker()
    if w is None:
        return None
    # 屏幕外坐标不投递给 worker：UIA ControlFromPoint 对屏幕外点会永久卡死（实测，
    # worker 首查卡进锁内 → 后续坐标永不处理 → hover 永远框整窗）。屏幕外也没有
    # 控件可 hover，直接返回 None 走整窗兜底。
    # 注意必须用虚拟屏边界（多显示器副屏坐标可能为负或超出主屏宽高），否则双屏
    # 笔记本 hover 副屏会被误判为"屏幕外"而永不查询（tdSelector 同样用虚拟屏）。
    if not _in_virtual_screen(x, y):
        return None
    # 坐标没变就不重复 submit（鼠标不动时避免 worker 反复重查同坐标 + seq 膨胀）
    if (x, y) != _last_submit_xy[0]:
        _last_submit_xy[0] = (x, y)
        w.submit(x, y)
    res = w.latest()
    r = res.get("rect")
    if not r or r.get("width", 0) <= 0:
        return None
    # 光标已移出结果矩形 → 结果过期，不采纳（回退整窗，等 worker 新坐标的结果）。
    # 配合 worker 的"总是写回"：深搜慢的应用（Windows Terminal）即使查询期间鼠标
    # 微动，只要光标仍在该元素内就沿用细粒度结果，不再概率性掉回整窗。
    tol = 2
    if (r["left"] - tol <= x <= r["left"] + r["width"] + tol and
            r["top"] - tol <= y <= r["top"] + r["height"] + tol):
        return r
    return None


_last_submit_xy = [None]  # 上次 submit 给 worker 的坐标（用 list 包一层便于在函数内改）


def _pause_hover_uia():
    w = _hover_worker_inst
    if w is not None:
        w.pause()


def _resume_hover_uia():
    w = _hover_worker_inst
    if w is not None:
        w.resume()


# ─── 桌面图标（SysListView32）单项命中：Win32 ListView 消息 ───
# 桌面图标的单个图标项在 UIA3 里暴露极差（ControlFromPoint 命中图标常返回整个
# FolderView → 捕获整窗）。正确做法是直接发 ListView 控件消息：LVM_HITTEST 从鼠标点
# 定位图标索引 + LVM_GETITEMRECT 拿该项矩形（tdSelector 同款做法）。需跨进程读写
# explorer 地址空间传递 LVHITTESTINFO/RECT。
_LVM_FIRST = 0x1000
_LVM_GETITEMCOUNT = _LVM_FIRST + 4    # 0x1004
_LVM_GETITEMRECT = _LVM_FIRST + 14    # 0x100E
_LVM_HITTEST = _LVM_FIRST + 18        # 0x1012
_LVM_GETITEMTEXTW = _LVM_FIRST + 115  # 0x1073
_LVIR_BOUNDS = 0
_PROCESS_VM_RW = 0x0008 | 0x0010 | 0x0020 | 0x0400  # OPERATION|READ|WRITE|QUERY_INFORMATION
_MEM_COMMIT = 0x1000; _MEM_RESERVE = 0x2000; _MEM_RELEASE = 0x8000
_PAGE_READWRITE = 0x04


def _is_desktop_listview(hwnd) -> bool:
    """是否桌面图标列表（SysListView32，父链经 SHELLDLL_DefView，属 Progman/WorkerW）。"""
    if _get_class_name(hwnd) != "SysListView32":
        return False
    try:
        path = _get_ancestor_path(hwnd)
    except Exception:
        return False
    classes = {p.get("class_name") for p in path}
    return "SHELLDLL_DefView" in classes and ("Progman" in classes or "WorkerW" in classes)


def _desktop_icon_at(hwnd, x, y):
    """返回鼠标 (x,y) 命中的桌面图标 {rect, name, index}；未命中图标返回 None。

    跨进程：向 explorer 的 ListView 发 LVM_HITTEST/LVM_GETITEMRECT，结构体分配在目标
    进程地址空间。任何一步失败（权限/提权/UIPI）返回 None → 调用方回退整窗。"""
    pid = wintypes.DWORD()
    _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None
    hproc = _OpenProcess(_PROCESS_VM_RW, False, pid.value)
    if not hproc:
        return None
    # LVHITTESTINFO: POINT pt(8) + UINT flags(4) + int iItem(4) + int iSubItem(4) + int iGroup(4) = 24
    buf_size = 1024
    remote = _VirtualAllocEx(hproc, None, buf_size, _MEM_COMMIT | _MEM_RESERVE, _PAGE_READWRITE)
    if not remote:
        _CloseHandle(hproc)
        return None
    try:
        pt = wintypes.POINT(x, y)
        _ScreenToClient(hwnd, ctypes.byref(pt))
        # 写 LVHITTESTINFO（只需 pt，其余置 0）
        hittest = (ctypes.c_byte * buf_size)()
        ctypes.memmove(hittest, ctypes.byref(pt), 8)
        written = ctypes.c_size_t(0)
        if not _WriteProcessMemory(hproc, remote, hittest, buf_size, ctypes.byref(written)):
            return None
        idx = _SendMessageW(hwnd, _LVM_HITTEST, 0, remote)
        if idx < 0:
            return None  # 点在图标间隙 → 不命中单项
        # LVM_GETITEMRECT: wParam=index, lParam=RECT*（rc.left=LVIR_BOUNDS）
        rectbuf = (ctypes.c_byte * buf_size)()
        ctypes.memset(rectbuf, 0, buf_size)
        if not _WriteProcessMemory(hproc, remote, rectbuf, buf_size, ctypes.byref(written)):
            return None
        if not _SendMessageW(hwnd, _LVM_GETITEMRECT, idx, remote):
            return None
        out = (ctypes.c_byte * buf_size)()
        read = ctypes.c_size_t(0)
        if not _ReadProcessMemory(hproc, remote, out, buf_size, ctypes.byref(read)):
            return None
        rc = wintypes.RECT()
        ctypes.memmove(ctypes.byref(rc), out, 16)
        tl = wintypes.POINT(rc.left, rc.top)
        _ClientToScreen(hwnd, ctypes.byref(tl))
        icon_rect = {"left": tl.x, "top": tl.y,
                     "width": rc.right - rc.left, "height": rc.bottom - rc.top,
                     "right": tl.x + (rc.right - rc.left),
                     "bottom": tl.y + (rc.bottom - rc.top)}
        # 图标名（可选，失败不阻塞）
        name = ""
        try:
            name = _desktop_icon_text(hproc, remote, hwnd, idx)
        except Exception:
            pass
        return {"rect": icon_rect, "name": name, "index": idx}
    except Exception:
        return None
    finally:
        _VirtualFreeEx(hproc, remote, 0, _MEM_RELEASE)
        _CloseHandle(hproc)


def _desktop_icon_text(hproc, remote, hwnd, idx):
    """读桌面图标项文本（LVM_GETITEMTEXTW via LVITEMW）。失败返回空串。"""
    # LVITEMW 布局(64位)：mask(4) iItem(4) iSubItem(4) state(4) stateMask(4) pszText(8)
    #   cchTextMax(4) iImage(4) lParam(8) iIndent(4) iGroupId(4) cColumns(4) puColumns(8) ...
    text_off = 64  # LVITEM 放 remote[0:80]，文本缓冲放 remote[text_off:]
    lvitem = (ctypes.c_byte * text_off)()
    ctypes.memset(lvitem, 0, text_off)
    # mask at offset 0 → LVIF_TEXT（必须设置，否则不返回文本）
    ctypes.memmove(ctypes.addressof(lvitem) + 0, ctypes.byref(ctypes.c_uint(1)), 4)
    # iItem at offset 4
    ctypes.memmove(ctypes.addressof(lvitem) + 4, ctypes.byref(ctypes.c_int(idx)), 4)
    # pszText at offset 24 → remote + text_off
    ctypes.memmove(ctypes.addressof(lvitem) + 24,
                   ctypes.byref(ctypes.c_void_p(remote + text_off)), 8)
    # cchTextMax at offset 32（文本区 = buf_size - text_off 字节，留足宽字符空间）
    ctypes.memmove(ctypes.addressof(lvitem) + 32, ctypes.byref(ctypes.c_int(400)), 4)
    written = ctypes.c_size_t(0)
    if not _WriteProcessMemory(hproc, remote, lvitem, text_off, ctypes.byref(written)):
        return ""
    _SendMessageW(hwnd, _LVM_GETITEMTEXTW, idx, remote)
    out = (ctypes.c_byte * 800)()
    read = ctypes.c_size_t(0)
    if not _ReadProcessMemory(hproc, remote + text_off, out, 800, ctypes.byref(read)):
        return ""
    try:
        return out.value.decode("utf-16-le", errors="ignore")
    except Exception:
        return ""


def _get_best_rect(hwnd, x, y):
    hwnd_rect = _get_window_rect(hwnd)
    # 桌面图标：Win32 ListView 消息直接命中单个图标项（UIA 对 FolderView 单项暴露差，
    # 会把整个桌面列表当整窗）。命中图标则框/捕获单项，间隙则回退整窗。
    if _is_desktop_listview(hwnd):
        icon = _desktop_icon_at(hwnd, x, y)
        if icon:
            return icon["rect"], icon["rect"]
        return hwnd_rect, None
    if _is_skip_uia(hwnd):
        return hwnd_rect, None
    uia_rect = _get_uia_rect(x, y)
    if uia_rect and uia_rect.get("width", 0) > 0:
        return uia_rect, uia_rect
    return hwnd_rect, None


_uia_module = None
_deep_cache = {"hwnd": 0, "x": 0, "y": 0, "t": 0, "rect": None, "info": None}  # 深搜兜底节流缓存（rect + 捕获信息）

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

# ─── 悬浮窗（border/info）对 UIA 不可见的 WndProc ───
# 根治 hover worker 卡死：实测（diag_interfere 对照）主循环 show_border 画出的悬浮窗
# 会被 worker 线程的 ControlFromPoint 命中，而 ctypes 悬浮窗用 DefWindowProc 响应
# WM_GETOBJECT 返回默认 UIA provider，UIA 枚举/命中它时卡死 → hover 高亮冻结。
# 让悬浮窗对 WM_GETOBJECT 返回 0（无 UIA provider），UIA 直接跳过它们，worker 不再被卡。
_WNDPROC = ctypes.WINFUNCTYPE(wintypes.LPARAM, wintypes.HWND, wintypes.UINT,
                              wintypes.WPARAM, wintypes.LPARAM)
_WM_GETOBJECT = 0x003D
_WM_NCHITTEST = 0x0084
_HTTRANSPARENT = -1
# DefWindowProcW 需显式声明签名：64 位下 WPARAM/LPARAM 是指针宽度，不声明会被 ctypes
# 按 c_int 截断/溢出（OverflowError: int too long to convert）。
_DefWindowProcW = _user32.DefWindowProcW
_DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_DefWindowProcW.restype = wintypes.LPARAM

# ─── 捕获期间吞掉捕获手势的点击（"只捕获，不操作"） ───
# 遮罩/悬浮窗是鼠标穿透的（WM_NCHITTEST→HTTRANSPARENT，且区域在光标处抠洞），Alt+点击
# 捕获会把真实点击落到下层应用，触发实际点击副作用。用 WH_MOUSE_LL 低级鼠标钩子在输入
# 到达应用前拦截并吞掉按键消息（返回非零=已处理，消息不再派发）。
# **只吞 Alt+左键（捕获手势）**；普通左键/右键/中键照常透传给应用 —— 捕获期间可正常
# 操作目标应用（取消只用 Esc，右键不再承担取消手势）。
# 注意：低级钩子回调运行在安装它的线程上，该线程必须有消息泵。钩子安装在**独立泵消息
# 线程**上（_hook_pump），与捕获主循环解耦 —— 否则主循环一旦阻塞（遮罩全屏重绘/
# SetWindowRgn/UIA 查询/锁等待），整机鼠标输入就被串行化冻结（实测"鼠标移动卡"）。
# 主循环只读钩子维护的手势状态（_consume_mouse_click/_mouse_down），两者以
# _mouse_hook_lock 保护。钩子只在捕获期间安装，结束即卸载。
_WH_MOUSE_LL = 14
# WM_LBUTTONDOWN/UP 0x0201/0x0202, WM_RBUTTONDOWN/UP 0x0204/0x0205, WM_MBUTTONDOWN/UP 0x0207/0x0208
_SWALLOW_MOUSE_MSGS = {0x0201, 0x0202, 0x0204, 0x0205, 0x0207, 0x0208}
# 需要吞掉的按键手势（down 码 → 配对 up 码）：Alt+左键=捕获。吞掉 down 后对应的 up
# 也要吞，避免孤立 up 落到应用。
_SWALLOW_GESTURE_DOWN_UP = {0x0201: 0x0202}
_HOOKPROC = ctypes.WINFUNCTYPE(wintypes.LPARAM, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
_SetWindowsHookExW = _user32.SetWindowsHookExW
_SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
_SetWindowsHookExW.restype = wintypes.HHOOK
_UnhookWindowsHookEx = _user32.UnhookWindowsHookEx
_UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_UnhookWindowsHookEx.restype = wintypes.BOOL
_CallNextHookEx = _user32.CallNextHookEx
_CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
_CallNextHookEx.restype = wintypes.LPARAM
_mouse_hook_handle = None  # 当前低级鼠标钩子句柄（None=未安装）
_mouse_hook_proc = None    # 模块级持有回调引用，防 GC 后回调悬空
_mouse_hook_lock = threading.Lock()
_mouse_hook_click = None   # 钩子记录的手势：None/("capture",)
_mouse_hook_down = False   # 当前是否有鼠标键被按住（由钩子维护，替代不可靠的 GetAsyncKeyState）
_hook_thread = None        # 独立泵消息线程（安装/处理钩子回调，与主循环解耦）
_hook_thread_tid = None    # 泵线程 OS 线程 id（用于 PostThreadMessageW 唤醒退出）

def _install_mouse_swallow_hook() -> bool:
    """安装吞点击的低级鼠标钩子（WH_MOUSE_LL）。重复调用幂等。返回是否成功。

    钩子安装在**独立泵消息线程**：低级钩子回调运行在安装线程上，若装在主循环线程，
    主循环阻塞（遮罩重绘/SetWindowRgn/UIA 查询/锁等待）会把整机鼠标输入串行化冻结。
    独立线程保证钩子回调始终即时执行，主循环怎么阻塞都不影响系统鼠标。

    只吞 Alt+左键（捕获手势）的按下/抬起；普通左键/右键/中键透传给应用（仅记录按住
    状态供 _mouse_down 判断模态态）。钩子把捕获手势转发给捕获循环（通过模块级状态），
    因为低级钩子拦下的点击**不会**反映到 GetAsyncKeyState —— 捕获循环读它必然错过
    （实测：鼠标事件被钩子吞掉后 GetAsyncKeyState 恒 0）。"""
    global _mouse_hook_handle, _mouse_hook_proc, _hook_thread, _mouse_hook_click, _mouse_hook_down
    if _mouse_hook_handle:
        return True
    # 重置按键状态：本轮捕获前可能残留上一轮的"按住"状态（第一轮 Alt+点击向下
    # 被钩子记 down=True，但 up 发生在卸载钩子之后没被看到 → _mouse_hook_down 恒 True
    # → 下一轮 ov._mouse_down() 恒 True → hover worker 被暂停 → 无高亮。必须清零。）
    with _mouse_hook_lock:
        _mouse_hook_click = None
        _mouse_hook_down = False
    swallowed_ups = set()  # 已吞 down 对应的 up 消息码（吞 down 后 up 也吞，防孤立 up 落到应用）

    def _cb(code, wparam, lparam):
        global _mouse_hook_click, _mouse_hook_down
        if code >= 0 and wparam in _SWALLOW_MOUSE_MSGS:
            with _mouse_hook_lock:
                if wparam in (0x0201, 0x0204, 0x0207):  # 按下
                    _mouse_hook_down = True
                    # Alt+左键 = 捕获（取消只用 Esc，右键不再承担取消手势）
                    if wparam == 0x0201 and (_GetAsyncKeyState(VK_MENU) & 0x8000):
                        _mouse_hook_click = "capture"
                        swallowed_ups.add(_SWALLOW_GESTURE_DOWN_UP[0x0201])
                        return 1  # 吞掉 Alt+点击：不落到下层应用
                    # 普通左键/右键/中键按下：仅记录按住状态，透传给应用
                else:  # 抬起
                    _mouse_hook_down = False
                    if wparam in swallowed_ups:
                        swallowed_ups.discard(wparam)
                        return 1  # 吞掉与已吞 down 配对的 up
            return _CallNextHookEx(None, code, wparam, lparam)
        return _CallNextHookEx(None, code, wparam, lparam)

    installed = threading.Event()
    result = {}

    def _hook_pump():
        """泵线程：本线程安装钩子（钩子与安装线程绑定），阻塞式 GetMessage 泵取，
        保证钩子回调在本线程即时执行。收到 WM_QUIT 退出。"""
        global _mouse_hook_proc, _hook_thread_tid
        _hook_thread_tid = _GetCurrentThreadId()
        proc = _HOOKPROC(_cb)
        _mouse_hook_proc = proc  # 模块级持有引用，防回调悬空
        h = _SetWindowsHookExW(_WH_MOUSE_LL, proc, None, 0)
        result["handle"] = h
        installed.set()
        if not h:
            return
        msg = wintypes.MSG()
        while _GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _TranslateMessage(ctypes.byref(msg))
            _DispatchMessageW(ctypes.byref(msg))
        _UnhookWindowsHookEx(h)

    _hook_thread = threading.Thread(target=_hook_pump, daemon=True)
    _hook_thread.start()
    installed.wait(timeout=2.0)
    _mouse_hook_handle = result.get("handle")
    if not _mouse_hook_handle:
        _mouse_hook_proc = None
        _hook_thread = None
        return False
    return True


def _uninstall_mouse_swallow_hook():
    """卸载吞点击钩子（幂等），并唤醒泵线程退出。"""
    global _mouse_hook_handle, _mouse_hook_proc, _hook_thread, _hook_thread_tid
    global _mouse_hook_click, _mouse_hook_down
    if _mouse_hook_handle:
        _UnhookWindowsHookEx(_mouse_hook_handle)
        _mouse_hook_handle = None
    tid = _hook_thread_tid
    _hook_thread_tid = None
    if tid:
        try:
            _PostThreadMessageW(tid, WM_QUIT, 0, 0)  # 唤醒阻塞中的 GetMessage
        except Exception:
            pass
    _hook_thread = None
    _mouse_hook_proc = None
    # 清理按键状态：防 up 事件在卸载后到达 → 下轮残留"按住"（见 _install 注释）
    with _mouse_hook_lock:
        _mouse_hook_click = None
        _mouse_hook_down = False


def _consume_mouse_click() -> str | None:
    """消费钩子记录的点击手势（"capture"/None；取消只用 Esc，无右键手势）。"""
    global _mouse_hook_click
    with _mouse_hook_lock:
        v = _mouse_hook_click
        _mouse_hook_click = None
        return v


def _mouse_down() -> bool:
    """钩子维护的鼠标键按住状态（替代 GetAsyncKeyState，钩子吞点击后它不可靠）。"""
    with _mouse_hook_lock:
        return _mouse_hook_down


def _overlay_wndproc_cb(hwnd, msg, wparam, lparam):
    if msg == _WM_GETOBJECT:
        return 0  # 无 UIA provider：UIA hit-test/枚举跳过本悬浮窗
    if msg == _WM_NCHITTEST:
        return _HTTRANSPARENT  # 鼠标穿透：悬浮窗盖住目标区域时 hover 仍能命中下层元素
    return _DefWindowProcW(hwnd, msg, wparam, lparam)


_overlay_wndproc = _WNDPROC(_overlay_wndproc_cb)  # 模块级保持引用，防 GC 后回调悬空


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
    wc.lpfnWndProc = ctypes.cast(_overlay_wndproc, ctypes.c_void_p)
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
_border_region_size = (0, 0)  # 上次 SetWindowRgn 的 (w,h)：region 只依赖尺寸，尺寸没变就跳过
                               # 重建 —— SetWindowRgn 会触发 DWM 重排，30ms 高频重建会阻塞
                               # hover worker 的 UIA hit-test（实测 diag_nodraw 定位）


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
    wc.lpfnWndProc = ctypes.cast(_overlay_wndproc, ctypes.c_void_p)
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
    global _border_visible, _border_region_size
    hwnd = _ensure_border_window()
    if rect and rect.get("width", 0) > 0 and rect.get("height", 0) > 0:
        w, h = rect["width"], rect["height"]
        if (w, h) != _border_region_size:  # region 只依赖尺寸，尺寸没变不重建（减少 DWM 重排）
            _set_border_region(hwnd, w, h)
            _border_region_size = (w, h)
        # 用 SetWindowPos 代替 MoveWindow，带 SWP_NOZORDER|SWP_NOACTIVATE|SWP_SHOWWINDOW：
        # 不动 Z 序、不激活，对 DWM 干扰比 MoveWindow 小。MoveWindow 每帧高频会阻塞 hover
        # worker 的 UIA hit-test（实测 diag_nodraw 定位：窗口操作饿死 worker ControlFromPoint）。
        # WS_EX_TOPMOST 创建时已置顶，故用 NOZORDER 保持 Z 序不动。
        _user32.SetWindowPos(hwnd, 0, rect["left"], rect["top"], w, h,
                             0x0004 | 0x0010 | 0x0040)  # NOZORDER|NOACTIVATE|SHOWWINDOW
        _border_visible = True
    elif _border_visible:
        _user32.ShowWindow(hwnd, 0); _border_visible = False


def _flash_once(hwnd, rect, color):
    _set_window_color(hwnd, color)
    _set_border_region(hwnd, rect["width"], rect["height"])  # hollow border
    _user32.MoveWindow(hwnd, rect["left"], rect["top"], rect["width"], rect["height"], True)
    _user32.ShowWindow(hwnd, 1); time.sleep(0.2)
    _user32.ShowWindow(hwnd, 0); time.sleep(0.15)


def flash_element(element: ElementInfo, times=3):
    # 优先用 UIA 目标层级的细粒度 rect（图标/菜单项等），其次 HWND rect
    rect = None
    if element.uia_path:
        tidx = element.uia_target_index
        if not isinstance(tidx, int) or not (0 <= tidx < len(element.uia_path)):
            tidx = len(element.uia_path) - 1
        leaf = element.uia_path[tidx]
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
        idx = lvl.get("index")
        cls = lvl.get("class_name", "")
        if isinstance(idx, int) and idx >= 0:
            # 与 _child_class_index 语义对齐：同类名兄弟中的第 idx 个（仅按类名枚举）
            hwnd = find_child_window(hwnd, class_name=cls, index=idx)
        else:
            hwnd = find_child_window(hwnd, class_name=cls, title=lvl.get("title", ""))
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


def _in_virtual_screen(x, y) -> bool:
    """点是否在虚拟屏内（跨所有显示器）。多显示器副屏坐标可能为负或超出主屏宽高。"""
    vx = _GetSystemMetrics(SM_XVIRTUALSCREEN); vy = _GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = _GetSystemMetrics(SM_CXVIRTUALSCREEN); vh = _GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return vx <= x < vx + vw and vy <= y < vy + vh


def _grab_region_screenshot(rect: dict | None) -> str:
    """截取屏幕指定区域，返回 base64 dataURL。失败返回空串。

    多显示器：ImageGrab.grab(bbox) 只截主屏，目标在副屏（坐标可能为负或超出
    主屏宽高）时会得到全黑图。此时改用 all_screens 全量截取再按虚拟屏原点裁剪。
    """
    if not rect or not rect.get("width", 0) > 0 or not rect.get("height", 0) > 0:
        return ""
    try:
        from PIL import ImageGrab
        import io
        left, top = int(rect["left"]), int(rect["top"])
        right, bottom = left + int(rect["width"]), top + int(rect["height"])
        cx, cy = _GetSystemMetrics(SM_CXSCREEN), _GetSystemMetrics(SM_CYSCREEN)
        on_primary = 0 <= left and 0 <= top and right <= cx and bottom <= cy
        if on_primary:
            img = ImageGrab.grab(bbox=(left, top, right, bottom))
        else:
            vx, vy = _GetSystemMetrics(76), _GetSystemMetrics(77)  # SM_X/YVIRTUALSCREEN
            img = ImageGrab.grab(all_screens=True)
            img = img.crop((left - vx, top - vy, right - vx, bottom - vy))
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


def _top_window_of(hwnd):
    """沿父链上溯到顶层窗口（GetParent 到 0 为止）。"""
    cur = hwnd
    guard = 0
    while cur and guard < 32:
        p = _GetParent(cur)
        if not p:
            return cur
        cur = p
        guard += 1
    return hwnd


_ROUTE_LOG = os.path.join(os.environ.get("TEMP", "."), "rpa_capture_route.log")


def _route_log(msg: str):
    """浏览器路由调试日志（诊断用，追加写 %TEMP%\\rpa_capture_route.log）。"""
    try:
        with open(_ROUTE_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


_ext_online = False
_ext_browsers: set = set()
_ext_online_ts = 0.0


def _extension_online(browser: str | None = None) -> bool:
    """指定浏览器（chrome/edge/firefox）的扩展是否在线（2s 缓存）。

    未指定浏览器 → 任意扩展在线即 True。离线时不切网页会话，保持遮罩 UIA —— 避免
    会话启动即失败（或错开在其它浏览器的窗口上：后端按连接分发，Chrome 的委托不能
    用到 Edge 的连接上）。"""
    global _ext_online, _ext_browsers, _ext_online_ts
    now = time.time()
    if now - _ext_online_ts > 2.0:
        _ext_online_ts = now
        try:
            from scripts.capture_gui.backend_addr import backend_base as _backend_base
            import json
            import urllib.request
            with urllib.request.urlopen(_backend_base() + "/api/extension/status", timeout=2) as r:
                data = json.loads(r.read().decode())
                _ext_online = bool(data.get("online"))
                _ext_browsers = {b.get("browser") for b in (data.get("browsers") or [])}
        except Exception:
            _ext_online = False
            _ext_browsers = set()
    if not browser:
        return _ext_online
    return browser in _ext_browsers


def _browser_of(hwnd) -> str:
    """hwnd 所在进程的浏览器类型（chrome/edge/firefox），非浏览器返回 ''。"""
    exe = os.path.basename(_get_process_exe(hwnd) or "").lower()
    if exe.endswith("chrome.exe"):
        return "chrome"
    if exe.endswith("msedge.exe"):
        return "edge"
    if exe.endswith("firefox.exe"):
        return "firefox"
    return ""


def _browser_viewport(hwnd):
    """hwnd 所在浏览器窗口的**页面内容框** = 渲染宿主（Chrome_RenderWidgetHostHWND）窗口矩形。

    含 Edge 垂直标签页：垂直标签面板占窗口左侧全高，渲染宿主在其右侧 → 内容框矩形
    自动排除标签面板（这正是"以内容框为切换点"的精确边界）。返回 rect dict；
    非浏览器/找不到渲染宿主返回 None。"""
    top = _top_window_of(hwnd)
    if not top or not _is_web_browser(top):
        return None
    if "Chrome_RenderWidgetHostHWND" in _get_class_name(hwnd):
        return _get_window_rect(hwnd)
    vp = [None]

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(child, _lp):
        if "Chrome_RenderWidgetHostHWND" in _get_class_name(child):
            vp[0] = _get_window_rect(child)
            return False  # 找到即停
        return True

    _EnumChildWindows(top, _enum, 0)
    return vp[0]


def _web_capture_target(hwnd, x, y):
    """光标是否在**真实浏览器**窗口的**页面内容框**（渲染宿主视口矩形）内。

    是 → 返回顶层浏览器窗口（供委托扩展网页捕获）；否 → None。
    切换点 = 内容框（渲染宿主矩形）：
      - Chrome/Edge：内容框 = Chrome_RenderWidgetHostHWND 窗口矩形 —— 自动排除顶栏
        与 Edge 垂直标签面板（内容在面板右侧）。
      - Firefox 等无渲染宿主：退回顶栏启发式（BROWSER_CHROME_HEIGHT 以下视为内容）。
    """
    top = _top_window_of(hwnd)
    if not top or not _is_web_browser(top):
        return None
    vp = _browser_viewport(hwnd)
    if vp is not None:
        if vp.get("width", 0) > 0 and vp.get("height", 0) > 0 and _rect_contains(vp, x, y):
            return top
        return None  # 光标在渲染宿主矩形外（顶栏/垂直标签面板）→ 桌面元素
    # 无渲染宿主（Firefox 等）：退回顶栏启发式
    wr = _get_window_rect(top)
    if wr["width"] <= 0 or wr["height"] <= 0:
        return None
    if not (wr["left"] <= x <= wr["left"] + wr["width"]
            and wr["top"] <= y <= wr["top"] + wr["height"]):
        return None
    if y < wr["top"] + BROWSER_CHROME_HEIGHT:
        return None  # 顶栏（标签+地址栏）→ 桌面元素
    return top


class BackToDesktop(Exception):
    """网页拾取中用户切回桌面拾取 —— 结束当前拾取但不结束整场捕获。"""


def _pump_messages():
    """泵取并派发本线程的挂起消息，保持悬浮框窗口响应（避免被标记未响应/假死）。

    悬浮框内容由 GetDC 直接绘制（不走 WM_PAINT），因此 WM_PAINT 只做 ValidateRect，
    避免 DefWindowProc 用背景刷把已绘制内容擦掉。
    """
    msg = wintypes.MSG()
    while _PeekMessageW(ctypes.byref(msg), None, 0, 0, 0x0001):  # PM_REMOVE
        if msg.message == WM_PAINT:
            _ValidateRect(msg.hWnd, None)
            continue
        _TranslateMessage(ctypes.byref(msg))
        _DispatchMessageW(ctypes.byref(msg))


def _capture_via_extension(browser_hwnd, sx, sy, web_only: bool = False,
                           viewport_watch=None) -> ElementInfo | None:
    """委托浏览器插件原生捕获。阻塞等待用户 Alt+Click。

    阻塞的 HTTP 调用放后台线程执行；主线程泵消息保持响应。**不显示桌面悬浮窗** ——
    网页捕获由扩展在页面内自行高亮/提示（用户确认：桌面悬浮窗冗余，去掉）。
    启动前把目标浏览器置前：扩展 launchBrowserCapture 取「当前活动窗口」的活动标签页，
    否则会话会开在错误的窗口上（实测"需要移动到另一个浏览器窗口才能触发"）。

    viewport_watch：可选回调，返回 True 表示光标仍在页面内容框内。每次循环调用，
    返回 False 时取消会话并抛 BackToDesktop（复用"切回桌面拾取"语义）—— 遮罩模式用它
    做"光标离开内容框自动切回"的可靠退出（不再依赖扩展的 mouse-leave 检测）。
    """
    # 扩展 launchBrowserCapture 取 currentWindow 活动标签页 → 必须先置前目标浏览器
    _user32.SetForegroundWindow(browser_hwnd)
    win_rect = _get_window_rect(browser_hwnd)
    vx, vy = _screen_to_viewport(sx, sy, win_rect)
    request_id = str(uuid.uuid4())[:8]
    result_box = {"done": False, "result": None}
    browser = _browser_of(browser_hwnd)  # chrome/edge/firefox，后端按连接分发

    def _run_capture():
        try:
            from scripts.capture_gui.ws_client import launch_browser_capture
            result_box["result"] = launch_browser_capture(
                vx, vy, timeout=300.0, request_id=request_id, web_only=web_only, browser=browser)
        except Exception as e:
            result_box["result"] = {"error": str(e)}
        finally:
            result_box["done"] = True

    threading.Thread(target=_run_capture, daemon=True).start()
    try:
        from scripts.capture_gui.ws_client import cancel_browser_capture
    except Exception:
        result_box["result"] = {"error": "ws_client unavailable"}
        result_box["done"] = True

    cancelled = False
    try:
        while not result_box["done"]:
            _pump_messages()
            # 光标离开页面内容框 → 自动切回桌面拾取
            if viewport_watch is not None and not viewport_watch():
                cancel_browser_capture(request_id)
                raise BackToDesktop()
            if _GetAsyncKeyState(VK_ESCAPE) & 0x8000:
                cancelled = True
                cancel_browser_capture(request_id)
                break
            time.sleep(0.05)
        result = result_box["result"] or {}
        if cancelled:
            return None
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
        # 异常/提前退出且捕获仍挂起 → 兜底取消，避免扩展残留框选模式
        if not cancelled and not result_box["done"]:
            try:
                cancel_browser_capture(request_id)
            except Exception:
                pass


def run_capture(mode: str = "desktop") -> ElementInfo | None:
    """捕获入口。

    - web：委托浏览器扩展 DOM 拾取（网页元素）。
    - 其他模式（desktop / desktop_mask 等）：统一走全屏遮罩桌面捕获
      `run_capture_mask` —— 旧浮窗式桌面捕获已移除（CaptureToolModal 同步清理），
      遮罩模式更稳定，且支持浏览器内容区自动转网页捕获（见 overlay_mask）。

    注意：web 分支**不能安装吞点击钩子** —— 扩展的网页捕获靠页面 DOM click 事件确认
    （content_capture.js onCaptureClick + altKey），钩子会在系统层吞掉 Alt+点击，
    DOM click 不触发 → 网页捕获确认失效（8/13 加钩子后遗留，一并修复）。
    """
    if mode != "web":
        # 延迟导入：overlay_mask 模块级依赖 overlay（import overlay as ov），顶层导入会
        # 循环；运行时两模块都已加载，函数内导入安全。
        from scripts.capture_gui.overlay_mask import run_capture_mask
        return run_capture_mask("desktop")

    editor_hwnd = _hide_editor_window()  # 捕获期间隐藏 RPA 编辑器（Electron）
    try:
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
    finally:
        _restore_editor_window(editor_hwnd)  # 捕获结束恢复并前置 RPA 编辑器


def _latest_worker_uia_info(x, y) -> dict | None:
    """读 hover worker 已算好的捕获信息（与用户看到的高亮一致）。

    深搜慢的 XAML 应用（Windows Terminal/PowerShell 等）在 hover 期间 worker 已经把
    细粒度元素算好了；捕获时直接复用，避免 _try_uia_capture 重新深搜撞 3s 超时降级成
    整窗（"框到 tab、捕获整窗"）。仅当结果存在、含完整 path 且矩形包含捕获点才采纳。
    """
    w = _hover_worker_inst
    if w is None:
        return None
    res = w.latest()
    info = res.get("info")
    if not info or not info.get("path"):
        return None
    r = info.get("rect") or {}
    if r.get("width", 0) <= 0 or not _rect_contains(r, x, y):
        return None
    return info


def _build_element_info(hwnd, x, y) -> ElementInfo:
    cls = _get_class_name(hwnd); title = _get_window_text(hwnd); rect = _get_window_rect(hwnd)
    path = _get_ancestor_path(hwnd)
    info = ElementInfo(name=title or cls, class_name=cls, title=title, rect=rect, hwnd=hwnd, win32_path=path)
    # 桌面捕获始终产出 win32/uia 元素（含浏览器窗口）——web 类型仅由扩展捕获产生
    # （带 candidates/css_selector）。浏览器窗口只影响 UIA 命名，不改元素类型。
    in_browser = _is_browser_window(cls) or _is_browser_in_chain(path)
    info.uia_available = _uia_dependency_ok()  # 依赖缺失时前端提示"仅 Win32 层级"
    info.elevation_blocked = _elevation_blocked(hwnd)  # 目标提权+自身未提权 → UIPI 拦截
    # 桌面图标单项捕获：UIA 对 FolderView 单项暴露差会返回整窗，改用 Win32 ListView
    # 消息命中单个图标（tdSelector 同款），框/截图/命名都对准该图标项。
    if _is_desktop_listview(hwnd):
        icon = _desktop_icon_at(hwnd, x, y)
        if icon:
            best_rect = icon["rect"]
            info.region = best_rect
            if icon.get("name"):
                info.name = icon["name"]
            info.control_type = "ListItem"
            info.screen_size = _screen_size()
            info.screenshot = _grab_region_screenshot(best_rect)
            return info
        # 点在图标间隙 → 回退整窗 FolderView
    # 浏览器内容区优先走 UIA 无障碍树网页拾取（tdSelector 同款，零扩展/零后端）：
    # 鼠标落在 Chromium 渲染根内且深搜到 DOM 节点 → 产出 web 元素（含 DOM 特征链）。
    if in_browser and not _is_skip_uia(hwnd):
        web = _uia_web_capture(x, y)
        if web and web.get("found"):
            info.element_type = "web"
            # 显示名：优先叶子可访问名（placeholder/文本/aria-label），否则用 class/id
            # 生成人类可读名 —— 不能用窗口标题（"Chrome Legacy Window"）当元素名。
            leaf_name = (web.get("name") or "").strip()
            if not leaf_name:
                leaf_name = _web_display_name(web)
            info.name = leaf_name or info.name
            info.control_type = web.get("control_type", "")
            info.automation_id = web.get("automation_id", "")
            # UIA → CSS/XPath 由 _uia_web_capture 里的生成器产出（非空时可直接定位）
            info.css_selector = web.get("css_selector", "")
            info.xpath = web.get("xpath", "")
            info.candidates = web.get("candidates", []) or []
            info.elem_attrs = web.get("elem_attrs", {}) or {}
            info.uia_path = web.get("path", [])
            info.uia_target_index = web.get("target_index", len(info.uia_path) - 1)
            info.dom_path = web.get("dom_path", [])
            # 前端手动编辑 tab 需要：DOM 层级（tag/id/classes）+ 每层属性。
            # _uia_web_capture 已产出 dom_editor_path（编辑器形态）与 attrs（别名），
            # 必须透传到 ElementInfo，否则 _info_to_dict 会把它们丢掉 → 前端层级/属性丢失。
            info.dom_editor_path = web.get("dom_editor_path", []) or []
            info.attrs = web.get("attrs", {}) or {}
            web_rect = web.get("rect") or {}
            if web_rect.get("width", 0) > 0:
                info.region = web_rect
                info.rect = web_rect
            info.screen_size = _screen_size()
            info.screenshot = _grab_region_screenshot(info.region)
            return info
        # UIA 网页拾取未命中（浏览器 UI 骨架/整窗）→ 继续走通用 UIA 逻辑
    uia = None
    if not _is_skip_uia(hwnd):
        # 优先复用 hover worker 已算好的结果（显示什么捕获什么，且不触发超时重查）；
        # 无可用结果再走独立的限时 UIA 查询（快速命中场景秒回，深搜场景有 worker 兜底）。
        uia = _latest_worker_uia_info(x, y) or _try_uia_capture(x, y)
    best_rect = rect
    if uia:
        info.control_type = uia.get("control_type", ""); info.automation_id = uia.get("automation_id", "")
        info.uia_path = uia.get("path", [])
        info.uia_target_index = uia.get("target_index", len(info.uia_path) - 1)
        if not info.name: info.name = uia.get("name", "")
        if in_browser and info.control_type in (
            "EditControl", "ButtonControl", "HyperlinkControl", "TextControl",
            "ComboBoxControl", "CheckBoxControl", "ListItemControl", "TreeItemControl"):
            info.name = uia.get("name") or title
        uia_rect = uia.get("rect") or {}
        if (uia_rect.get("width", 0) > 0
                and 0 < uia_rect.get("width", 0) <= 500
                and 0 < uia_rect.get("height", 0) <= 500):
            best_rect = uia_rect
    # 所有元素统一捕获区域快照（图像兜底数据）
    info.region = best_rect
    info.screen_size = _screen_size()
    info.screenshot = _grab_region_screenshot(best_rect)
    return info


def _finalize_capture(hwnd, x, y) -> ElementInfo | None:
    """捕获手势确认后的收尾：暂停 hover UIA、等鼠标松开、UIA 枚举 + 截图。

    调用方必须先卸载吞点击钩子（本函数不卸载）—— 否则主线程阻塞在 UIA 枚举/截图
    期间，整机鼠标输入会被全局低级钩子串行化冻结。暂停 hover worker 避免与
    _build_element_info 的 UIA 查询并发打满 provider（相互拖慢，XAML 应用深搜期间
    尤为明显，甚至让 _try_uia_capture 超时降级）。
    """
    _pause_hover_uia()
    # 有界等待鼠标松开：目标先退出 SetCapture 模态态，再做 UIA/文本查询，
    # 避免目标不应答导致捕获卡死（最多等 1.5s，超时仍继续）。钩子已卸载/未安装，
    # 这里用 GetAsyncKeyState 轮询物理按键状态（不再有吞点击干扰）。
    wait_deadline = time.time() + 1.5
    while (_GetAsyncKeyState(VK_LBUTTON) | _GetAsyncKeyState(VK_RBUTTON)
           | _GetAsyncKeyState(VK_MBUTTON)) & 0x8000 and time.time() < wait_deadline:
        time.sleep(0.02)
    _dwm_flush()       # 等 DWM 合成完成（有界），确保蓝边已从屏幕移除
    time.sleep(0.1)
    # 尽力等 hover worker 当前查询结束（0.5s 内），期间持锁让 worker 无法再查询，
    # 保证 _build_element_info 的 UIA 枚举独占 provider；等不到就并发（罕见且自限）。
    lock_held = _uia_draw_lock.acquire(timeout=0.5)
    try:
        return _build_element_info(hwnd, x, y)
    finally:
        if lock_held:
            _uia_draw_lock.release()
