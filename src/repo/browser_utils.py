"""浏览器路径发现、启动和扩展连接等待工具。"""

import asyncio
import os
import shutil
import subprocess
import time
from typing import Optional

logger = __import__("logging").getLogger(__name__)

# Per-browser-type lock to prevent concurrent launches of the same browser
_launch_locks: dict[str, asyncio.Lock] = {}


def _get_launch_lock(browser_type: str) -> asyncio.Lock:
    if browser_type not in _launch_locks:
        _launch_locks[browser_type] = asyncio.Lock()
    return _launch_locks[browser_type]


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


async def wait_for_extension(
    browser_type: str,
    ext_manager,
    timeout: float = 60.0,
) -> str:
    """等待指定浏览器的扩展 WebSocket 连接上线。

    采用指数退避轮询:
      - 已在线: 立即返回 client_id
      - 不在线: 先尝试启动浏览器，然后轮询等待扩展连接

    返回 client_id，超时抛出 TimeoutError。
    """
    from src.runtime.websocket_manager import ext_manager as _em

    if ext_manager is None:
        ext_manager = _em

    # 1. 已在线？
    conns = ext_manager.connections_by_browser(browser_type)
    if conns:
        logger.info(f"[{browser_type}] 扩展已在线: {conns[0].client_id}")
        return conns[0].client_id

    # 1.5 扩展可能刚连接但还没 register，先等 2 秒避免误启动
    if ext_manager.is_any_online:
        logger.info(f"[{browser_type}] 有扩展在线但尚未注册浏览器类型，等待 2 秒...")
        await asyncio.sleep(2)
        conns = ext_manager.connections_by_browser(browser_type)
        if conns:
            logger.info(f"[{browser_type}] 扩展注册后已在线: {conns[0].client_id}")
            return conns[0].client_id

    # 2. 尝试启动浏览器（加锁防止并发重复启动）
    lock = _get_launch_lock(browser_type)
    async with lock:
        # 抢锁后再次检查，可能别的请求已经启动并连上了
        conns = ext_manager.connections_by_browser(browser_type)
        if conns:
            logger.info(f"[{browser_type}] 扩展已在线(抢锁后): {conns[0].client_id}")
            return conns[0].client_id

        logger.info(f"[{browser_type}] 扩展未连接，尝试启动浏览器...")
        launched = launch_browser(browser_type)
        if not launched:
            raise RuntimeError(f"无法启动 {browser_type}，请确认已安装")

        # 3. 指数退避轮询等待扩展连接
        start = time.time()
        delay = 0.5
        waited_launch = False

        while time.time() - start < timeout:
            conns = ext_manager.connections_by_browser(browser_type)
            if conns:
                return conns[0].client_id

            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 5.0)

            # 启动后前 3 秒多打日志，方便诊断
            if not waited_launch and time.time() - start > 3:
                waited_launch = True
                logger.info(f"等待 {browser_type} 扩展连接中...")

    raise TimeoutError(f"{browser_type} 扩展未在 {timeout}s 内连接，请确认扩展已安装并启用")
