"""
RPA Script 桌面应用入口
启动 FastAPI 后端 + pywebview 窗口
"""

import argparse
import os
import sys
import time
import threading

# 开发模式下从 src/desktop.py 运行时，需要把仓库根目录加入 sys.path
# 否则 import src.runtime.main 会解析失败
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import webview
import uvicorn

# ---------------------------------------------------------------------------
# PyInstaller 路径适配
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    # 运行在 PyInstaller 打包后的 exe 中
    BUNDLE_DIR = sys._MEIPASS
    # --windowed 模式下 stdout/stderr 为 None，print 会报错
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
else:
    # 开发环境 — 仓库根目录，使静态文件路径正确解析
    BUNDLE_DIR = _REPO_ROOT

# ---------------------------------------------------------------------------
# 数据目录：数据库、日志等持久化文件放到用户目录，避免打包目录只读
# ---------------------------------------------------------------------------

USER_DATA_DIR = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "RPA Script")
os.makedirs(USER_DATA_DIR, exist_ok=True)

# 通过环境变量覆盖配置
os.environ.setdefault("RPA_REPO_ROOT", BUNDLE_DIR)
os.environ.setdefault("RPA_LOG_DIR", USER_DATA_DIR)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(USER_DATA_DIR, 'data.db')}")

# 桌面端自动生成/复用 JWT 密钥，避免用户手动配置环境变量
_SECRET_KEY_PATH = os.path.join(USER_DATA_DIR, ".secret_key")
if not os.environ.get("SECRET_KEY"):
    if os.path.isfile(_SECRET_KEY_PATH):
        with open(_SECRET_KEY_PATH, "r", encoding="utf-8") as f:
            _secret_key = f.read().strip()
    else:
        import secrets

        _secret_key = secrets.token_hex(32)
        with open(_SECRET_KEY_PATH, "w", encoding="utf-8") as f:
            f.write(_secret_key)
    os.environ["SECRET_KEY"] = _secret_key

# 打包后默认端口 8811，与开发环境 8000 区分，避免冲突
# 如需多实例运行，可在启动前设置环境变量 PORT 覆盖
os.environ.setdefault("HOST", "127.0.0.1")
os.environ.setdefault("PORT", "8811")

# ---------------------------------------------------------------------------
# Uvicorn 服务线程
# ---------------------------------------------------------------------------

_server_ready = threading.Event()
_server_should_stop = threading.Event()
_server_instance = None


def _run_server():
    """在后台线程运行 uvicorn。"""
    global _server_instance
    config = uvicorn.Config(
        "src.runtime.main:app",
        host=os.environ["HOST"],
        port=int(os.environ["PORT"]),
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    _server_instance = server

    # 启动守护线程：当收到停止信号时设置 should_exit
    def _shutdown_watcher():
        _server_should_stop.wait()
        server.should_exit = True

    threading.Thread(target=_shutdown_watcher, daemon=True).start()

    # 通知主线程服务器即将启动
    threading.Thread(target=_wait_for_startup, args=(server,), daemon=True).start()
    server.run()


def _wait_for_startup(server: uvicorn.Server):
    """轮询直到服务器开始监听。"""
    while not _server_ready.is_set():
        if server.started:
            _server_ready.set()
            break
        time.sleep(0.05)


def _wait_for_server(timeout: float = 30.0) -> bool:
    """阻塞等待服务器就绪。"""
    return _server_ready.wait(timeout=timeout)


# ---------------------------------------------------------------------------
# JS API：供前端 pywebview 桥接调用
# ---------------------------------------------------------------------------

class Api:
    def saveFileDialog(self, content, defaultFilename, fileTypes=None):
        """弹出系统保存文件对话框，将 content 写入用户选择的文件"""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            ext = os.path.splitext(defaultFilename)[1].lower()
            if fileTypes:
                dialog_types = [(t["name"], t["pattern"]) for t in fileTypes]
            elif ext == ".csv":
                dialog_types = [("CSV", "*.csv"), ("All files", "*.*")]
            elif ext == ".json":
                dialog_types = [("JSON", "*.json"), ("All files", "*.*")]
            else:
                dialog_types = [("All files", "*.*")]
            default_ext = ext or ".txt"
            file_path = filedialog.asksaveasfilename(
                defaultextension=default_ext,
                initialfile=defaultFilename,
                filetypes=dialog_types,
            )
            root.destroy()
            if not file_path:
                return {"success": False, "cancelled": True}
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[desktop] saveFileDialog OK: {file_path}")
            return {"success": True, "path": str(file_path)}
        except Exception as e:
            print(f"[desktop] saveFileDialog error: {e}")
            return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="RPA Script Desktop")
    parser.add_argument("--debug", action="store_true", help="开启 pywebview 调试模式（右键审查元素）")
    args = parser.parse_args()

    host = os.environ["HOST"]
    port = os.environ["PORT"]
    url = f"http://{host}:{port}/admin/commands"

    # 启动后端线程
    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    if not _wait_for_server(timeout=15.0):
        print("[desktop] ERROR: server failed to start within 15s", file=sys.stderr)
        sys.exit(1)

    print(f"[desktop] Server ready at {url}")

    api = Api()

    # 创建桌面窗口
    webview.create_window(
        title="RPA Script",
        url=url,
        width=1400,
        height=900,
        min_size=(1024, 640),
        text_select=True,
        js_api=api,
    )

    webview.start(
        debug=args.debug,
        private_mode=False,
        storage_path=os.path.join(USER_DATA_DIR, "webview"),
    )

    print("[desktop] Window closed, shutting down server...")
    _server_should_stop.set()
    server_thread.join(timeout=3.0)
    print("[desktop] Exited")


if __name__ == "__main__":
    main()
