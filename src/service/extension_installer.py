"""一键安装 bundled 浏览器扩展（开发版 / 打包版均支持）。"""

import os
import subprocess

from src.config import settings
from src.repo.chrome_utils import get_chrome_path, _chrome_already_running


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
    """关闭 Chrome 后用 --load-extension 重新启动并加载 bundled 扩展。

    返回值只表示是否成功启动 Chrome；真正的安装结果应由调用方通过
    WebSocket 在线状态或扩展扫描二次确认。
    """
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

    return {
        "success": True,
        "launched": True,
        "need_close_browser": False,
        "chrome_path": chrome_path,
        "extension_dir": ext_dir,
        "error": "",
    }
