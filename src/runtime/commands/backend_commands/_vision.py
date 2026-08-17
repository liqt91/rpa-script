"""Command: 图像识别共享工具 — _vision

供 findImage / clickImage 使用的模板匹配与截图获取。

- template_match: FFT 互相关 + 积分图归一化（纯 numpy，O(HW log HW)）
- capture_page: 调扩展 takeScreenshot 截取当前浏览器页面，附视口屏幕坐标

M1 仅支持浏览器页面（scope=page）；桌面窗口（scope=window）M2 提供。
"""
from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image


def template_match(hay: Image.Image, needle: Image.Image, similarity: float):
    """在 haystack 中模板匹配 needle，返回 (x, y, w, h, confidence) 或 None。

    坐标单位为截图像素（haystack 尺寸）。confidence 为归一化相关系数 [-1, 1]。
    """
    hg = np.asarray(hay.convert("L"), dtype=np.float64)
    ng = np.asarray(needle.convert("L"), dtype=np.float64)
    hh, hw = hg.shape
    nh, nw = ng.shape
    if nw > hw or nh > hh:
        return None

    # FFT 互相关：模板左上角填充到整图尺寸，conj(fft(g)) 实现时域翻转相关
    fh = np.fft.fft2(hg)
    gpad = np.zeros((hh, hw))
    gpad[:nh, :nw] = ng
    fg = np.conj(np.fft.fft2(gpad))
    cross = np.fft.ifft2(fh * fg).real

    # 有效匹配位置（模板不环绕的前缀区）
    ys, xs = np.ogrid[: hh - nh + 1, : hw - nw + 1]

    # 积分图（和、平方和）→ 每个窗口的均值/方差 O(1)
    pad = np.zeros((hh + 1, hw + 1))
    pad2 = np.zeros((hh + 1, hw + 1))
    pad[1:, 1:] = hg
    pad2[1:, 1:] = hg * hg
    s = np.cumsum(np.cumsum(pad, axis=0), axis=1)
    s2 = np.cumsum(np.cumsum(pad2, axis=0), axis=1)

    win_sum = s[ys + nh, xs + nw] - s[ys, xs + nw] - s[ys + nh, xs] + s[ys, xs]
    win_sq = s2[ys + nh, xs + nw] - s2[ys, xs + nw] - s2[ys + nh, xs] + s2[ys, xs]
    n = nh * nw
    mean = win_sum / n
    var = win_sq / n - mean * mean

    nmean = float(ng.mean())
    nvar = float(ng.var())
    if nvar < 1e-12:
        return None

    denom = np.sqrt(var * nvar) * n
    with np.errstate(divide="ignore", invalid="ignore"):
        conf = (cross[ys, xs] - n * mean * nmean) / denom
    conf[~np.isfinite(conf)] = -1.0

    idx = np.unravel_index(int(np.argmax(conf)), conf.shape)
    best = float(conf[idx])
    if best < similarity:
        return None
    return int(idx[1]), int(idx[0]), nw, nh, best


async def capture_page(runner, timeout: float = 10.0):
    """截取当前浏览器页面。

    :returns: (PIL.Image, screen_x_css, screen_y_css, dpr)
        截图是物理像素（captureVisibleTab 语义）；screen_x/y 为视口左上角屏幕坐标（CSS px）。
        目标屏幕物理坐标 = (screen_x*dpr + px, screen_y*dpr + py)。
    """
    resp = await runner._call_extension_handler(
        "takeScreenshot",
        {"locator": "", "selectorFamily": "css", "extra": {"timeout": timeout}},
        timeout=timeout + 5,
    )
    data_url = resp.get("dataUrl", "")
    b64 = data_url.split(",", 1)[-1] if "," in data_url else data_url
    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    return (
        img,
        float(resp.get("screenX", 0) or 0),
        float(resp.get("screenY", 0) or 0),
        float(resp.get("dpr", 1) or 1),
    )


def screen_coords(screen_x_css: float, screen_y_css: float, dpr: float, px_x: int, px_y: int):
    """截图内像素坐标 → 屏幕物理坐标（浏览器视口路径）。"""
    return round(screen_x_css * dpr + px_x), round(screen_y_css * dpr + px_y)


def capture_screen():
    """截取虚拟屏幕（所有显示器并集，纯 Python，mss）。

    :returns: (PIL.Image, offset_left, offset_top)
        mss monitors[0] 是全部显示器的并集，left/top 为其左上角的屏幕物理坐标（可为负，副屏场景）。
        屏幕物理坐标 = (offset_left + x, offset_top + y)，匹配坐标即屏幕坐标，无需额外换算。
    """
    import mss
    with mss.mss() as sct:
        mon = sct.monitors[0]
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        return img, int(mon["left"]), int(mon["top"])


def capture_window(hwnd: int):
    """截取指定桌面窗口（PrintWindow 后台渲染，遮挡/最小化也可截）。

    :returns: (PIL.Image, win_left, win_top)
        截图尺寸 = 窗口外框 rect 尺寸；目标屏幕坐标 = (win_left + px_x, win_top + px_y)。
    """
    import ctypes
    from ctypes import wintypes
    from src.runtime.commands.desktop_commands._win32 import get_window_rect

    rect = get_window_rect(hwnd)
    if not rect or rect["width"] <= 0 or rect["height"] <= 0:
        raise ValueError(f"窗口矩形无效: {rect}")

    w, h = rect["width"], rect["height"]
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
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

    img = None
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
        from PIL import ImageGrab
        img = ImageGrab.grab(bbox=(rect["left"], rect["top"], rect["right"], rect["bottom"]))

    return img.convert("RGB"), rect["left"], rect["top"]
