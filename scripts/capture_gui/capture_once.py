"""一次性捕获入口 — 子进程调用，输出 JSON。

供两处使用：
  - FastAPI 端点 /api/commands/gui-picker（后端调起）
  - DSH 插件 rpa_capture 工具（spawn 并透传 --workspace 就地写回）

用法：
  python capture_once.py [mode] [--workspace <工作区目录>]
  mode: web | desktop_mask（默认 desktop_mask，统一遮罩捕获，含浏览器内容区自动转网页）
  --workspace: 捕获成功后把元素就地写进该工作区 workflow.json + images/
"""
import argparse
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
    from scripts.capture_gui.store import _info_to_dict, save_element_to_workspace


def main():
    parser = argparse.ArgumentParser(description="统一元素捕获（遮罩 Alt+点击）")
    parser.add_argument("mode", nargs="?", default="desktop_mask",
                        help="web | desktop_mask（默认 desktop_mask）")
    parser.add_argument("--workspace", default=None,
                        help="捕获成功后就地写回的工作区目录（须含 rpa.json）")
    parser.add_argument("--name", default=None, help="元素命名（默认自动生成）")
    args = parser.parse_args()
    mode = args.mode
    try:
        with contextlib.redirect_stderr(_io.StringIO()):  # 压制 libpng 警告
            if mode == "web":
                info = run_capture("web")            # 浏览器 DOM 拾取（委托扩展，网页元素）
            else:
                info = run_capture_mask("desktop")   # 全屏遮罩式桌面捕获（含浏览器内容区自动转网页）
        if not info:
            print(json.dumps({"cancelled": True}))
            return
        d = _info_to_dict(info, keep_screenshot=True)
        # 就地写回工作区（可选）；保持 d 的字段在顶层（前端 /gui-picker 读顶层
        # candidates/dom_path 等），额外加 writeback 字段不破坏现有调用方。
        writeback = None
        if args.workspace:
            try:
                writeback = save_element_to_workspace(args.workspace, d, name=args.name)
            except Exception as e:
                writeback = {"ok": False, "error": str(e)}
        d["writeback"] = writeback
        print(json.dumps(d, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
