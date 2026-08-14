"""Command: 窗口截图 — screenshotWindow (backend)

将指定窗口截图为 PNG 图片保存到本地。
优先用 PrintWindow（后台渲染，窗口被遮挡/最小化也能截取）；
PrintWindow 对自绘控件无效时自动退回前台区域抓取（ImageGrab）。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref


@register_handler(
    cmd="screenshotWindowWin32", label="窗口截图",
    category="桌面操作", runtime="backend",
    icon="fa-camera", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="截取指定窗口图像保存为 PNG（PrintWindow 后台渲染，遮挡/最小化也可截取）",
    category_order=50, command_order=22,
    summary_tpl="{savePath}",
)
class ScreenshotWindowHandler:
    params = [
        Param("parentWindow", "窗口 (HWND变量)", "str-var", required=True,
              placeholder="要截图的窗口句柄变量"),
        Param("savePath", "保存路径", "string", required=True,
              placeholder="如 D:\\shots\\win.png，支持 {{变量}}"),
        Param("resultVar", "结果存入变量(路径)", "str-var", default="",
              placeholder="实际保存路径存入此变量"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import resolve_hwnd, get_window_rect, is_windows, window_exists

        extra = instr.get("extra", {})
        win_var = clean_var_ref(extra.get("parentWindow", ""))
        save_path = convert_value(extra.get("savePath", ""), "string", runner.vars)
        result_var = clean_var_ref(extra.get("resultVar", ""))

        if not is_windows():
            result = {"error": "当前系统非 Windows，不支持桌面窗口操作"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        hwnd = resolve_hwnd(runner.vars.get(win_var))
        if not hwnd or not window_exists(hwnd):
            result = {"error": f"窗口句柄无效: {win_var} = {hwnd}"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        if not save_path:
            result = {"error": "保存路径为空"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        import ctypes
        from ctypes import wintypes
        import os

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        # 显式声明 GDI/user32 签名（句柄为 64 位，未声明时 ctypes 按 c_int 传参会溢出）
        user32.GetWindowDC.argtypes = [wintypes.HWND]
        user32.GetWindowDC.restype = wintypes.HDC
        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        user32.ReleaseDC.restype = ctypes.c_int
        user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
        user32.PrintWindow.restype = wintypes.BOOL
        gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi32.CreateCompatibleDC.restype = wintypes.HDC
        gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        gdi32.SelectObject.restype = wintypes.HGDIOBJ
        gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        gdi32.DeleteObject.restype = wintypes.BOOL
        gdi32.DeleteDC.argtypes = [wintypes.HDC]
        gdi32.DeleteDC.restype = wintypes.BOOL

        rect = get_window_rect(hwnd)
        if not rect or rect["width"] <= 0 or rect["height"] <= 0:
            result = {"error": f"窗口矩形无效: {rect}"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        w, h = rect["width"], rect["height"]

        try:
            from PIL import Image, ImageGrab
        except ImportError:
            result = {"error": "缺少 Pillow 依赖，无法截图"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        img = None
        source = "printwindow"
        hwnd_dc = user32.GetWindowDC(hwnd)
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        bmp = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
        old = gdi32.SelectObject(mem_dc, bmp)
        try:
            PW_RENDERFULLCONTENT = 0x00000002
            pw_ok = bool(user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT))
            if pw_ok:
                class _BITMAPINFOHEADER(ctypes.Structure):
                    _fields_ = [
                        ("biSize", wintypes.DWORD),
                        ("biWidth", ctypes.c_long),
                        ("biHeight", ctypes.c_long),
                        ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD),
                        ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD),
                        ("biXPelsPerMeter", ctypes.c_long),
                        ("biYPelsPerMeter", ctypes.c_long),
                        ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD),
                    ]
                bmi = _BITMAPINFOHEADER()
                bmi.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
                bmi.biWidth = w
                bmi.biHeight = -h  # top-down
                bmi.biPlanes = 1
                bmi.biBitCount = 32
                bmi.biCompression = 0  # BI_RGB
                buf = ctypes.create_string_buffer(w * h * 4)
                gdi32.GetDIBits.argtypes = [
                    wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                    ctypes.c_void_p, ctypes.POINTER(_BITMAPINFOHEADER), wintypes.UINT,
                ]
                gdi32.GetDIBits.restype = ctypes.c_int
                got = gdi32.GetDIBits(mem_dc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
                if got:
                    img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
        finally:
            gdi32.SelectObject(mem_dc, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(hwnd, hwnd_dc)

        if img is None:
            # PrintWindow 对自绘控件无效 → 退回前台区域抓取
            source = "foreground"
            img = ImageGrab.grab(bbox=(rect["left"], rect["top"],
                                       rect["right"], rect["bottom"]))

        dirname = os.path.dirname(os.path.abspath(save_path))
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        img.save(save_path)

        if result_var:
            runner.vars[result_var] = save_path

        result = {"saved": True, "path": save_path, "width": w, "height": h,
                  "source": source, "log": f"窗口截图已保存: {save_path} ({w}x{h})"}
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
