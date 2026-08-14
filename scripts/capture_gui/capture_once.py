"""一次性捕获入口 — 子进程调用，输出 JSON。

供 FastAPI 端点 /api/commands/gui-picker 使用：
    1. web → overlay.run_capture("web")（委托扩展 DOM 拾取）
    2. 其余 → overlay_mask.run_capture_mask("desktop")（全屏遮罩桌面捕获，含浏览器内容区自动转网页）
"""
import json
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _root not in sys.path:
    sys.path.insert(0, _root)

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

import contextlib
import io as _io
_sink = _io.StringIO()
# 压制 PIL/libpng 的 C 级警告到 stderr
with contextlib.redirect_stderr(_sink):
    from scripts.capture_gui.overlay import run_capture
    from scripts.capture_gui.overlay_mask import run_capture_mask
    from scripts.capture_gui.store import _info_to_dict


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "desktop_mask"  # web | desktop_mask
    try:
        with contextlib.redirect_stderr(_io.StringIO()):  # 压制 libpng 警告
            if mode == "web":
                info = run_capture("web")            # 浏览器 DOM 拾取（委托扩展，网页元素）
            else:
                info = run_capture_mask("desktop")   # 全屏遮罩式桌面捕获（含浏览器内容区自动转网页）
        if not info:
            print(json.dumps({"cancelled": True}))
            return
        print(json.dumps(_info_to_dict(info, keep_screenshot=True), ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
