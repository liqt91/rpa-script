"""一次性验证入口 — 子进程调用，输出 JSON。

读取 stdin 传入的 ElementInfo JSON，调用 overlay.flash_element 验证，
输出 {"found": true/false} 到 stdout。
"""
import json
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _root not in sys.path:
    sys.path.insert(0, _root)

import contextlib
import io as _io

with contextlib.redirect_stderr(_io.StringIO()):
    from scripts.capture_gui.overlay import ElementInfo, flash_element
    from scripts.capture_gui.store import _dict_to_info


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try: sys.stdout.reconfigure(encoding="utf-8")
        except Exception: pass
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
        info = _dict_to_info(data)
        with contextlib.redirect_stderr(_io.StringIO()):
            found = flash_element(info, times=3)
        print(json.dumps({"found": bool(found)}))
    except Exception as e:
        print(json.dumps({"found": False, "error": str(e)}))
        sys.exit(0)


if __name__ == "__main__":
    main()
