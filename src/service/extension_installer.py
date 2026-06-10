"""一键安装 bundled 浏览器扩展（开发版 / 打包版均支持）。"""

import os
import subprocess
import time

from src.config import settings
from src.repo.chrome_utils import get_chrome_path, _chrome_already_running
from src.service.extension_scanner import scan_installed_extensions


def _bundled_extension_dir() -> str:
    """定位打包进应用里的 extension 文件夹。"""
    candidates = [
        os.path.join(settings.REPO_DIR, "extension"),
        os.path.join(os.path.dirname(settings.REPO_DIR), "extension"),
    ]
    for path in candidates:
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "manifest.json")):
            return path
    return ""


def install_chrome_extension():
    """关闭 Chrome 后用 --load-extension 重新启动并加载 bundled 扩展。"""
    ext_dir = _bundled_extension_dir()
    if not ext_dir:
        return {"success": False, "error": "未找到 bundled extension 目录"}

    chrome_path = get_chrome_path()
    if not chrome_path:
        return {"success": False, "error": "未找到 Chrome 浏览器"}

    if _chrome_already_running():
        return {
            "success": False,
            "need_close_browser": True,
            "error": "Chrome 正在运行，请先关闭所有 Chrome 窗口后再点击安装",
        }

    user_data_dir = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    # 启动 Chrome 并加载本地扩展；使用默认用户数据目录保留用户登录态
    subprocess.Popen(
        [
            chrome_path,
            f"--user-data-dir={user_data_dir}",
            "--remote-debugging-port=9222",
            f"--load-extension={ext_dir}",
            "chrome://extensions/",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 给 Chrome 和扩展 service worker 留足初始化时间
    time.sleep(5)

    installed = scan_installed_extensions()
    chrome_installed = any(i.get("browser") == "chrome" for i in installed)
    return {
        "success": chrome_installed,
        "installed": chrome_installed,
        "need_close_browser": False,
        "chrome_path": chrome_path,
        "extension_dir": ext_dir,
        "error": "" if chrome_installed else "Chrome 已启动，但扩展尚未生效，请稍等后刷新页面",
    }
