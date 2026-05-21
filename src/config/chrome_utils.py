"""Chrome 启动 / 远程调试连接的共享工具,所有 job 复用。"""

import os
import shutil
import subprocess
import time

from DrissionPage import ChromiumPage, ChromiumOptions


USER_DATA_DIR = os.environ.get("CHROME_USER_DATA_DIR", r"D:\Chrome_Work")
DEBUG_PORT = int(os.environ.get("CHROME_DEBUG_PORT", "9222"))


def get_chrome_path():
    """定位 chrome.exe:DrissionPage > 常见安装路径 > 注册表。"""
    try:
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
        if os.path.exists(p):
            return p
    except Exception:
        pass

    return None


def launch_chrome(home_url: str = "about:blank"):
    """以 USER_DATA_DIR + 远程调试端口启动 Chrome。"""
    cp = get_chrome_path()
    if not cp:
        print("X Chrome not found")
        return False
    if not os.path.exists(USER_DATA_DIR):
        print(f"! {USER_DATA_DIR} missing")
        return False
    print(f"Launch Chrome ({USER_DATA_DIR})...")
    subprocess.Popen([
        cp,
        f"--user-data-dir={USER_DATA_DIR}",
        f"--remote-debugging-port={DEBUG_PORT}",
        home_url,
    ])
    time.sleep(3)
    return True


def connect_chrome(port: int | None = None, home_url: str = "about:blank"):
    """连上现有 Chrome,缺则尝试启动并重试。返回 ChromiumPage 或 None。"""
    if port is None:
        port = DEBUG_PORT
    try:
        p = ChromiumPage(port)
        print(f"OK Chrome port {port}")
        return p
    except Exception:
        print("Chrome not running, launching...")
        if launch_chrome(home_url=home_url):
            for i in range(10):
                time.sleep(2)
                try:
                    p = ChromiumPage(port)
                    print(f"OK Chrome port {port}")
                    return p
                except Exception:
                    print(f"  wait {i + 1}/10")
        print("FAIL")
        return None
