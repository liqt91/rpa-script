"""桌面元素捕获 — 全屏遮罩层方案（新实现，与 overlay.py 并存对比）。

区别于 overlay.py 的 SetWindowRgn 边框窗方案：本模块用**一张覆盖整个虚拟屏的
layered 全屏遮罩窗**（参考 tdSelector 的 Qt 全屏无边框 + WA_TransparentForMouseEvents
方案的 Win32 等价物），半透明压暗全屏、仅高亮目标控件区域镂空透亮 + 蓝色描边。

- 鼠标穿透遮罩（WM_NCHITTEST→HTTRANSPARENT），主循环轮询 GetCursorPos+WindowFromPoint
- hover 高亮复用 overlay 的 worker UIA 查询 + 桌面图标 Win32 命中（含双屏/DPI 修复）
- Alt+点击 捕获（复用 overlay._build_element_info），Esc/右键 取消
- 不用任何额外悬浮提示框（按需求仅遮罩 + 高亮）
"""
import ctypes
import ctypes.wintypes as wintypes
import time

from scripts.capture_gui import overlay as ov
from scripts.capture_gui.overlay import ElementInfo

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_kernel32 = ctypes.windll.kernel32

# ── Win32 常量 ──
_ULW_ALPHA = 0x02
_AC_SRC_OVER = 0x00
_AC_SRC_ALPHA = 0x01
_WS_EX_LAYERED = 0x00080000
_WS_EX_TOPMOST = 0x00000008
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_TRANSPARENT = 0x00000020
_WS_POPUP = 0x80000000
_MASK_ALPHA = 110          # 遮罩压暗不透明度（0-255）
_BORDER_COLOR_BGRA = (0xF6, 0x82, 0x3B, 255)  # 0x3b82f6 蓝 → BGRA 字节序
_BORDER_W = 2              # 描边宽度（px）


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte), ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_byte), ("AlphaFormat", ctypes.c_byte)]


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


# GDI / layered 绑定
_CreateDIBSection = _gdi32.CreateDIBSection
_CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                              ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
_CreateDIBSection.restype = wintypes.HBITMAP
_CreateCompatibleDC = _gdi32.CreateCompatibleDC
_CreateCompatibleDC.argtypes = [wintypes.HDC]; _CreateCompatibleDC.restype = wintypes.HDC
_DeleteDC = _gdi32.DeleteDC
_DeleteDC.argtypes = [wintypes.HDC]; _DeleteDC.restype = wintypes.BOOL
_DeleteObject = _gdi32.DeleteObject
_DeleteObject.argtypes = [wintypes.HGDIOBJ]; _DeleteObject.restype = wintypes.BOOL
_SelectObject = _gdi32.SelectObject
_SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]; _SelectObject.restype = wintypes.HGDIOBJ
_CreateRectRgn = _gdi32.CreateRectRgn
_CreateRectRgn.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
_CreateRectRgn.restype = wintypes.HRGN
_CombineRgn = _gdi32.CombineRgn
_CombineRgn.argtypes = [wintypes.HRGN, wintypes.HRGN, wintypes.HRGN, ctypes.c_int]
_CombineRgn.restype = ctypes.c_int
_SetWindowRgn = _user32.SetWindowRgn
_SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
_SetWindowRgn.restype = ctypes.c_int
_RGN_DIFF = 4
_UpdateLayeredWindow = _user32.UpdateLayeredWindow
_UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                 ctypes.POINTER(_SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                 wintypes.DWORD, ctypes.POINTER(_BLENDFUNCTION), wintypes.DWORD]
_UpdateLayeredWindow.restype = wintypes.BOOL
_RegisterClassW = _user32.RegisterClassW
_CreateWindowExW = _user32.CreateWindowExW
_DestroyWindow = _user32.DestroyWindow


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", ctypes.c_void_p),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HICON), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class _MaskLayer:
    """全屏遮罩层：半透明压暗全屏 + 高亮 rect 镂空 + 蓝描边。"""

    def __init__(self):
        self.hwnd = None
        self.vx = ov._GetSystemMetrics(ov.SM_XVIRTUALSCREEN)
        self.vy = ov._GetSystemMetrics(ov.SM_YVIRTUALSCREEN)
        self.vw = ov._GetSystemMetrics(ov.SM_CXVIRTUALSCREEN)
        self.vh = ov._GetSystemMetrics(ov.SM_CYVIRTUALSCREEN)
        self._last_rect = None  # 上次高亮 rect（去重防每帧重绘）
        self._rendered = False  # 是否已上过屏（首帧强制渲染）
        self._last_region_key = None  # 上次 region 键（高亮洞或光标量化网格）
        self._cursor = (0, 0)   # 当前光标（屏幕物理坐标）：其周围恒物理抠洞，保证
        # UIA/WindowFromPoint 对光标点的 hit-test 永远不受遮罩影响（哪怕高亮尚未出现）

    def _ensure_window(self):
        if self.hwnd:
            return self.hwnd
        hinst = _kernel32.GetModuleHandleW(None)
        wc = _WNDCLASSW()
        wc.lpfnWndProc = ctypes.cast(ov._overlay_wndproc, ctypes.c_void_p)  # HTTRANSPARENT + WM_GETOBJECT=0
        wc.hInstance = hinst
        wc.lpszClassName = "RpaMask"
        wc.hbrBackground = 0
        try:
            _RegisterClassW(ctypes.byref(wc))
        except Exception:
            pass
        self.hwnd = _CreateWindowExW(
            _WS_EX_LAYERED | _WS_EX_TOPMOST | _WS_EX_TOOLWINDOW | _WS_EX_TRANSPARENT,
            "RpaMask", "", _WS_POPUP,
            self.vx, self.vy, self.vw, self.vh,
            None, None, hinst, None)
        return self.hwnd

    def needs_update(self, rect, cursor):
        """无锁预检：本次 show 是否会真正绘制/改 region。主循环每帧调用它决定是否抢
        `_uia_draw_lock`——绝不能每帧无条件抢锁：worker 的 UIA 查询持同一把锁，主线程
        30fps 高频抢锁会把 worker 的阻塞 acquire 饿死数秒（实测首次查询 4.5s+）。"""
        key = None if not rect else (rect.get("left"), rect.get("top"),
                                     rect.get("width"), rect.get("height"))
        if not self._rendered or key != self._last_rect:
            return True
        if key:
            region_key = ("h", key)
        else:
            region_key = ("c", (cursor[0] - self.vx) // 48, (cursor[1] - self.vy) // 48)
        return region_key != self._last_region_key

    def show(self, rect, cursor=None):
        """显示遮罩并把 rect（屏幕物理坐标）镂空 + 描边。rect None=仅全遮罩。
        cursor=(x,y)：光标位置（无高亮时其周围物理抠洞，保证 UIA hit-test 不受遮罩影响）。

        性能关键：SetWindowRgn 会触发 DWM 重排，每帧调用会把 worker 的 UIA hit-test
        饿死到 5s 级（实测）。因此 region 只在高亮变化、或无高亮时光标跨 48px 网格才
        更新；位图只在高亮变化时重绘。"""
        if cursor:
            self._cursor = cursor
        key = None if not rect else (rect.get("left"), rect.get("top"),
                                     rect.get("width"), rect.get("height"))
        need_paint = not self._rendered or key != self._last_rect
        # region 键：有高亮→高亮洞（恒含光标，无需光标洞）；无高亮→光标所在量化网格
        if key:
            region_key = ("h", key)
        else:
            qx = (self._cursor[0] - self.vx) // 48
            qy = (self._cursor[1] - self.vy) // 48
            region_key = ("c", qx, qy)
        need_region = region_key != self._last_region_key
        if not need_paint and not need_region:
            return
        self._last_rect = key
        self._last_region_key = region_key
        hwnd = self._ensure_window()
        # 先确保窗口已显示（UpdateLayeredWindow 要求窗口可见才生效），再绘制上屏
        if not _user32.IsWindowVisible(hwnd):
            _user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE（不抢焦点）
        if need_paint:
            self._rendered = True
            self._hole = self._render_pixels(rect)
        if need_region:
            self._apply_region(getattr(self, "_hole", None) if key else None)

    def hide(self):
        self._last_rect = None
        self._rendered = False
        self._last_region_key = None
        if self.hwnd:
            _user32.ShowWindow(self.hwnd, 0)

    def destroy(self):
        if self.hwnd:
            _DestroyWindow(self.hwnd)
            self.hwnd = None

    def _render_pixels(self, rect):
        """在内存 DC 绘制整张 RGBA 位图并 UpdateLayeredWindow 上屏。返回高亮洞（本地坐标）。"""
        vw, vh = self.vw, self.vh
        hdc_screen = _user32.GetDC(None)
        hdc_mem = _CreateCompatibleDC(hdc_screen)
        bmi = _BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = vw
        bmi.bmiHeader.biHeight = -vh  # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0  # BI_RGB
        bits = ctypes.c_void_p()
        hbmp = _CreateDIBSection(hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        if not hbmp or not bits:
            _DeleteDC(hdc_mem); _user32.ReleaseDC(None, hdc_screen)
            return None
        old = _SelectObject(hdc_mem, hbmp)
        try:
            hole = self._paint(bits.value, vw, vh, rect)
            size = _SIZE(vw, vh)
            dst = wintypes.POINT(self.vx, self.vy)
            src = wintypes.POINT(0, 0)
            blend = _BLENDFUNCTION(_AC_SRC_OVER, 0, 255, _AC_SRC_ALPHA)
            _UpdateLayeredWindow(self.hwnd, hdc_screen, ctypes.byref(dst),
                                 ctypes.byref(size), hdc_mem, ctypes.byref(src),
                                 0, ctypes.byref(blend), _ULW_ALPHA)
            return hole
        finally:
            _SelectObject(hdc_mem, old)
            _DeleteObject(hbmp)
            _DeleteDC(hdc_mem)
            _user32.ReleaseDC(None, hdc_screen)

    def _apply_region(self, hole):
        """窗口 region = 全屏 − 高亮洞（− 光标小块，仅无高亮时）。

        有高亮时**只切高亮洞**，不再额外切光标块：高亮洞已覆盖光标所在元素（光标在元素
        内），再加 ±56px 光标方块会在悬停小元素（tab/文字，如 217×32）时露出一个比蓝框
        大一圈的透明正方形区（用户实测“蓝框对但多一个高亮方区跟着元素”）。
        无高亮时才用光标块：全屏 layered 遮罩即使 WM_GETOBJECT=0/HTTRANSPARENT，仍会
        让 UIA 对遮罩覆盖点的 hit-test 失效（实测 worker 深搜永不返回细粒度）——把光标
        周围物理抠掉后，光标处根本不存在遮罩窗口，UIA 查询如同无遮罩。"""
        full = _CreateRectRgn(0, 0, self.vw, self.vh)
        holes = (hole,) if hole else (self._cursor_hole(),)
        for h in holes:
            if h:
                L, T, R, B = h
                rgn = _CreateRectRgn(L, T, R, B)
                _CombineRgn(full, full, rgn, _RGN_DIFF)
                _DeleteObject(rgn)
        _SetWindowRgn(self.hwnd, full, True)  # 系统接管 region，不再 DeleteObject

    def _cursor_hole(self, half=56):
        """光标周围 ±half px 的本地坐标方块（无高亮时的抠洞；half 需 ≥ 量化网格 48，
        保证光标在网格内移动时仍被洞覆盖）。"""
        cx, cy = self._cursor
        L = cx - self.vx - half; T = cy - self.vy - half
        R = cx - self.vx + half; B = cy - self.vy + half
        L = max(0, L); T = max(0, T); R = min(self.vw, R); B = min(self.vh, B)
        return (L, T, R, B) if R > L and B > T else None

    def _paint(self, base, vw, vh, rect):
        """填像素：全屏半透明黑 → 高亮区镂空（alpha 0）→ 高亮区边缘蓝描边。
        返回物理抠洞区域（本地坐标 (L,T,R,B)，高亮区内缩描边宽度）；无高亮返回 None。"""
        stride = vw * 4
        # 半透明黑行 pattern
        mask_px = bytes((0, 0, 0, _MASK_ALPHA))
        mask_row = mask_px * vw
        for row in range(vh):
            ctypes.memmove(base + row * stride, mask_row, stride)
        if not rect or rect.get("width", 0) <= 0 or rect.get("height", 0) <= 0:
            return None
        # rect 是屏幕物理坐标 → 遮罩本地坐标（减虚拟屏原点）
        L = int(rect["left"]) - self.vx
        T = int(rect["top"]) - self.vy
        W = int(rect["width"])
        H = int(rect["height"])
        R = L + W; B = T + H
        # clamp 到遮罩范围
        L = max(0, L); T = max(0, T); R = min(vw, R); B = min(vh, B)
        if R <= L or B <= T:
            return None
        # 1) 镂空：高亮区内部 alpha=0
        clear_w = R - L
        clear_row = bytes(clear_w * 4)  # 全 0（含 alpha）
        for row in range(T, B):
            ctypes.memmove(base + row * stride + L * 4, clear_row, clear_w * 4)
        # 2) 描边：高亮区边缘 _BORDER_W px 蓝色不透明
        bp = bytes(_BORDER_COLOR_BGRA)
        bw = _BORDER_W
        # 上/下横边
        top_row = bp * (R - L)
        for row in range(T, min(T + bw, B)):
            ctypes.memmove(base + row * stride + L * 4, top_row, (R - L) * 4)
        for row in range(max(B - bw, T), B):
            ctypes.memmove(base + row * stride + L * 4, top_row, (R - L) * 4)
        # 左/右竖边
        vseg = bp * bw
        for row in range(T, B):
            ctypes.memmove(base + row * stride + L * 4, vseg, bw * 4)          # 左
            ctypes.memmove(base + row * stride + (R - bw) * 4, vseg, bw * 4)   # 右
        # 物理抠洞 = 高亮区内缩描边宽度（描边环保留在窗口内，洞从窗口 region 移除）
        return (L + bw, T + bw, R - bw, B - bw)


def run_capture_mask(mode: str = "desktop") -> ElementInfo | None:
    """全屏遮罩式桌面元素捕获。hover 高亮 + Alt+点击捕获 + Esc/右键取消。"""
    ov._com_init()
    mask = _MaskLayer()
    pt = wintypes.POINT()
    last_hwnd = None
    captured = None
    editor_hwnd = ov._hide_editor_window()  # 捕获期间隐藏 RPA 编辑器
    try:
        ov._uia_init()
        # 吞点击钩子：遮罩是鼠标穿透的，Alt+点击/右键取消会把真实点击落到下层应用。
        # 低级鼠标钩子在输入到达应用前拦截按键消息 → 只捕获，不触发实际点击。
        # 钩子拦下的点击不会反映到 GetAsyncKeyState（实测恒 0），因此捕获/取消手势
        # 一律从钩子状态读（_consume_mouse_click / _mouse_down）。
        hook_ok = ov._install_mouse_swallow_hook()
        mask.show(None)  # 先出全遮罩
        # Esc 取消防粘连：进入捕获瞬间就按着的 Esc 不算取消意图（残留的合成按键、
        # 点击按钮时粘连，会让 GetAsyncKeyState 恒为按下 → 首次循环即 break）。
        # 改为"armed"逻辑：只有进入后松开再按下的 Esc 才触发取消。
        # （右键取消走钩子信号，天然只有"新按下"才产生 → 无粘连问题。）
        esc_armed = not bool(ov._GetAsyncKeyState(ov.VK_ESCAPE) & 0x8000)
        while True:
            # 泵消息：遮罩窗属于主线程 STA，UIA hit-test 会向它发 WM_GETOBJECT；
            # 主循环若不泵消息，worker 线程的 ControlFromPoint 会跨线程阻塞到超时
            # （实测 10s+）。每帧泵取保持遮罩窗响应，同时驱动低级鼠标钩子回调。
            ov._pump_messages()
            # 取消：Esc（键盘，GetAsyncKeyState 可靠）或 右键（钩子信号）
            if ov._GetAsyncKeyState(ov.VK_ESCAPE) & 0x8000:
                if esc_armed:
                    break
            else:
                esc_armed = True  # 松开过 → 之后按下视为新的取消意图
            if hook_ok:
                gesture = ov._consume_mouse_click()
                if gesture == "cancel":
                    break
                if gesture == "capture" and last_hwnd:
                    # Alt+点击 → 捕获（销毁遮罩：捕获线程 UIA 枚举顶层窗口会向遮罩窗
                    # 发 WM_GETOBJECT，主线程此时不再泵消息 → 跨线程阻塞到超时（实测
                    # 3s 超时回退整窗）。窗口销毁后 UIA 直接跳过。）
                    mask.destroy()
                    deadline = time.time() + 1.5
                    while ov._mouse_down() and time.time() < deadline:
                        time.sleep(0.02)  # 等鼠标松开（目标退出 SetCapture 模态态）
                    ov._dwm_flush()
                    time.sleep(0.1)
                    captured = ov._build_element_info(last_hwnd, pt.x, pt.y)
                    break
            elif (ov._GetAsyncKeyState(ov.VK_LBUTTON) & 0x8000) and \
                 (ov._GetAsyncKeyState(ov.VK_MENU) & 0x8000) and last_hwnd:
                # 钩子未装上的兜底：轮询 GetAsyncKeyState 检测 Alt+点击
                mask.destroy()
                deadline = time.time() + 1.5
                while (ov._GetAsyncKeyState(ov.VK_LBUTTON) & 0x8000) and time.time() < deadline:
                    time.sleep(0.02)
                ov._dwm_flush()
                time.sleep(0.1)
                captured = ov._build_element_info(last_hwnd, pt.x, pt.y)
                break

            ov._GetCursorPos(ctypes.byref(pt))
            target = ov._WindowFromPoint(pt) if ov._in_virtual_screen(pt.x, pt.y) else None
            if target and ov._get_class_name(target) == "RpaMask":
                target = None  # 跳过遮罩自身（HTTRANSPARENT 已让 WindowFromPoint 跳过，防御）
            if not target and last_hwnd and _user32.IsWindow(last_hwnd):
                target = last_hwnd

            mouse_down = ov._mouse_down() if hook_ok else bool(
                (ov._GetAsyncKeyState(ov.VK_LBUTTON) | ov._GetAsyncKeyState(ov.VK_RBUTTON)
                 | ov._GetAsyncKeyState(ov.VK_MBUTTON)) & 0x8000)
            # 鼠标按住：目标可能在 SetCapture 模态态，暂停 hover 查询避免跨进程 UIA 卡死
            if mouse_down:
                ov._pause_hover_uia()
            else:
                ov._resume_hover_uia()

            # hover → 高亮目标控件（复用 worker UIA + 桌面图标命中）
            if not mouse_down and target:
                rect, _ = ov._get_best_rect(target, pt.x, pt.y)
                # 绘制与 worker 的 UIA 查询互斥（同一把锁），但**先无锁预检有无变化**，
                # 有变化才抢锁——主线程每帧抢锁会把 worker 的阻塞 acquire 饿死（实测
                # 首次查询被拖到 4.5s+）。
                show_rect = rect if (rect and rect.get("width", 0) > 0) else None
                if mask.needs_update(show_rect, (pt.x, pt.y)):
                    if ov._uia_draw_lock.acquire(timeout=0.05):
                        try:
                            mask.show(show_rect, (pt.x, pt.y))
                        finally:
                            ov._uia_draw_lock.release()
                if show_rect:
                    last_hwnd = target
            elif not target:
                if mask.needs_update(None, (pt.x, pt.y)):
                    if ov._uia_draw_lock.acquire(timeout=0.05):
                        try:
                            mask.show(None, (pt.x, pt.y))
                        finally:
                            ov._uia_draw_lock.release()

            time.sleep(0.03)
    finally:
        mask.destroy()
        ov._uninstall_mouse_swallow_hook()  # 恢复鼠标点击透传给应用
        ov._stop_hover_worker()
        ov._uia_done()
        ov._restore_editor_window(editor_hwnd)
    return captured
