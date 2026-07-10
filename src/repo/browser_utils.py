"""浏览器路径发现、启动和扩展连接等待工具。"""

import os
import shutil
import subprocess
from typing import Optional

from src.config import runtime_config as config

logger = __import__("logging").getLogger(__name__)


def get_chrome_path() -> Optional[str]:
    """定位 chrome.exe: DrissionPage > 常见安装路径 > 注册表。"""
    try:
        from DrissionPage import ChromiumOptions
        co = ChromiumOptions()
        p = co.browser_path
        if p and os.path.exists(p):
            return p
        if p == "chrome":
            r = shutil.which("chrome")
            if r and os.path.exists(r):
                return r
    except Exception:
        pass

    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p

    try:
        import winreg
        k = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
        )
        p = winreg.QueryValue(k, None)
        winreg.CloseKey(k)
        if p and os.path.exists(p):
            return p
    except Exception:
        pass

    return None


def get_edge_path() -> Optional[str]:
    """定位 msedge.exe: 常见安装路径 > 注册表。"""
    candidates = [
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p

    try:
        import winreg
        k = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
        )
        p = winreg.QueryValue(k, None)
        winreg.CloseKey(k)
        if p and os.path.exists(p):
            return p
    except Exception:
        pass

    return None


def detect_browser_paths() -> dict:
    """检测系统中 Chrome 和 Edge 的安装路径。"""
    return {
        "chrome": get_chrome_path(),
        "edge": get_edge_path(),
    }


def launch_browser(browser_type: str) -> bool:
    """启动浏览器（不指定 user-data-dir，复用现有用户配置）。

    如果浏览器已经在运行，会打开一个新窗口，不会报错。
    返回是否成功发起启动。
    """
    path = get_chrome_path() if browser_type == "chrome" else get_edge_path()
    if not path:
        logger.warning(f"未找到 {browser_type} 安装路径")
        return False

    try:
        subprocess.Popen(
            [path, "--no-first-run", "--no-default-browser-check"],
            shell=False,
            # Windows 下避免子进程继承控制台
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        logger.info(f"已启动 {browser_type}: {path}")
        return True
    except Exception as e:
        logger.error(f"启动 {browser_type} 失败: {e}")
        return False


def find_extension_dir() -> Optional[str]:
    """定位扩展文件夹：统一用 dist/desktop/extension/。"""
    candidates = [
        os.path.join(config.REPO_DIR, "dist", "desktop", "extension"),
    ]
    for path in candidates:
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "manifest.json")):
            return path
    return None


def is_browser_running(browser_type: str) -> bool:
    """Windows 下通过 tasklist 检测浏览器主进程是否正在运行。"""
    if os.name != "nt":
        return False
    image = "msedge.exe" if browser_type == "edge" else "chrome.exe"
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        return image.lower() in result.stdout.lower()
    except Exception:
        return False


def focus_browser_window(browser_type: str) -> bool:
    """Windows 下尝试将已有浏览器窗口前置。

    通过窗口标题匹配（Chrome 窗口标题含 "Google Chrome"，Edge 含 "Microsoft Edge"）。
    找不到窗口或非 Windows 平台返回 False。
    """
    if os.name != "nt":
        return False

    import ctypes
    from ctypes import wintypes

    target_suffix = "Microsoft Edge" if browser_type == "edge" else "Google Chrome"
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd, _lparam):
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        if target_suffix in buf.value:
            found.append(hwnd)
            return False
        return True

    ctypes.windll.user32.EnumWindows(enum_proc, 0)
    if not found:
        return False

    hwnd = found[0]
    SW_RESTORE = 9
    if ctypes.windll.user32.IsIconic(hwnd):
        ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    return True


def launch_browser_with_extension(browser_type: str) -> bool:
    """以默认用户目录启动浏览器，并自动加载 RPA Script 扩展。

    若浏览器已经在运行，则不会重复启动（也不会重新加载扩展）。
    返回是否成功发起启动。
    """
    path = get_chrome_path() if browser_type == "chrome" else get_edge_path()
    if not path:
        logger.warning(f"未找到 {browser_type} 安装路径")
        return False

    ext_dir = find_extension_dir()
    if not ext_dir:
        logger.warning("未找到 RPA Script 扩展目录")
        return False

    if is_browser_running(browser_type):
        logger.info(f"{browser_type} 已经在运行，跳过自动启动")
        return False

    try:
        subprocess.Popen(
            [
                path,
                f"--load-extension={ext_dir}",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            shell=False,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info(f"已启动 {browser_type} 并加载扩展: {ext_dir}")
        return True
    except Exception as e:
        logger.error(f"启动 {browser_type} 失败: {e}")
        return False
