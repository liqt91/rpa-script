"""一次性捕获入口 — 子进程调用，输出 JSON。

供 FastAPI 端点 /api/commands/gui-picker 使用：
    1. 调用 overlay.run_capture()（桌面+浏览器浮窗捕获）
    2. 将 ElementInfo 序列化为 JSON 输出到 stdout
"""
import json
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _root not in sys.path:
    sys.path.insert(0, _root)

from scripts.capture_gui.overlay import run_capture
from scripts.capture_gui.store import _info_to_dict


def main():
    try:
        info = run_capture()
        if not info:
            print(json.dumps({"cancelled": True}))
            return
        print(json.dumps(_info_to_dict(info), ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
