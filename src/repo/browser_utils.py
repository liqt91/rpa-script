"""浏览器路径发现、启动和扩展连接等待工具。"""

import os
import shutil
import subprocess
from typing import Optional

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
