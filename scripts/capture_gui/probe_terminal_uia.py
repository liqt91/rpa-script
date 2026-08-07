"""Windows Terminal UIA 诊断探针（只读，不进主流程）。

用法：把鼠标停在 Windows Terminal 的某个标签上，然后运行：
    python scripts/capture_gui/probe_terminal_uia.py

结果打印到屏幕，并追加到 %TEMP%\\rpa_uia_debug.log。
三段探测各自带超时保护，任一卡死不会拖垮脚本：
  A. 命中测试 ElementFromPoint（当前 hover 用到的轻量查询）
  B. 从命中元素沿父链上走（此前导致终端卡死的重遍历路径）
  C. ElementFromHandle 拿根 + 有界后代搜索（计划中的「点下最深元素」方案）
"""
import ctypes
import ctypes.wintypes as wintypes
import os
import sys
import threading

_user32 = ctypes.windll.user32
_GetCursorPos = _user32.GetCursorPos
_GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
_WindowFromPoint = _user32.WindowFromPoint
_WindowFromPoint.argtypes = [wintypes.POINT]
_WindowFromPoint.restype = wintypes.HWND
_GetWindowRect = _user32.GetWindowRect
_GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_GetWindowRect.restype = ctypes.c_int
_GetParent = _user32.GetParent
_GetParent.argtypes = [wintypes.HWND]
_GetParent.restype = wintypes.HWND

LOG = os.path.join(os.environ.get("TEMP", "."), "rpa_uia_debug.log")


def log(msg):
    print(msg)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _desc(elem):
    try:
        br = elem.BoundingRectangle
        return (f"{elem.ControlTypeName} | name='{elem.Name}' | {elem.ClassName} | "
                f"rect={int(br.left)},{int(br.top)} {int(br.width())}x{int(br.height())}")
    except Exception as e:
        return f"<desc-error {e!r}>"


def _probe_with_timeout(name, fn, secs=6):
    """在工作线程执行 fn，超时则记录 TIMEOUT。"""
    out = {}

    def _run():
        try:
            fn(out)
        except Exception as e:
            out["error"] = repr(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(secs)
    if t.is_alive():
        log(f"[{name}] TIMEOUT(>{secs}s) — 该查询会卡住，请勿在正常捕获中执行")
    else:
        for k, v in out.items():
            log(f"[{name}] {k}: {v}")


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    pt = wintypes.POINT()
    _GetCursorPos(ctypes.byref(pt))
    hwnd = _WindowFromPoint(pt)
    log(f"=== probe at ({pt.x},{pt.y}) hwnd={hwnd} ===")
    if not hwnd:
        log("no window under cursor")
        return
    # Win32 窗口矩形链（看是否有子窗口正好覆盖标签栏）
    rects = []
    cur_hwnd = hwnd
    for _ in range(8):
        if not cur_hwnd:
            break
        r = wintypes.RECT()
        _GetWindowRect(cur_hwnd, ctypes.byref(r))
        rects.append(f"{cur_hwnd}: {r.left},{r.top} {r.right - r.left}x{r.bottom - r.top}")
        cur_hwnd = _GetParent(cur_hwnd)
    log("Win32 rect chain:\n  " + "\n  ".join(rects))
    try:
        import uiautomation as uia
    except ImportError as e:
        log(f"缺少 uiautomation 依赖：{e}")
        log('请用系统 Python 运行（捕获用的那个）：')
        log('  & "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\'
            'Python312\\python.exe" scripts/capture_gui/probe_terminal_uia.py')
        return

    def probe_hit(out):
        with uia.UIAutomationInitializerInThread():  # 工作线程各自初始化 COM
            c = uia.ControlFromPoint(pt.x, pt.y)
            out["result"] = _desc(c) if c else "None"
    _probe_with_timeout("A.hit-test", probe_hit, 4)

    def probe_parent_walk(out):
        with uia.UIAutomationInitializerInThread():
            c = uia.ControlFromPoint(pt.x, pt.y)
            if not c:
                out["result"] = "None"
                return
            lines = []
            cur = c
            seen = set()
            for _ in range(8):
                if not cur or id(cur) in seen:
                    break
                seen.add(id(cur))
                lines.append(_desc(cur))
                try:
                    p = cur.GetParentControl()
                    if not p or p.ControlTypeName == "DesktopControl":
                        break
                    cur = p
                except Exception:
                    break
            out["result"] = "  <-up--\n".join(lines)
    _probe_with_timeout("B.parent-walk", probe_parent_walk, 6)

    def probe_descend(out):
        with uia.UIAutomationInitializerInThread():
            root = uia.ControlFromPoint2(pt.x, pt.y)
            if not root:
                out["root"] = "None"
                return
            out["root"] = _desc(root)
            best = None
            best_area = None
            stack = [(root, 0)]
            seen = set()
            nodes = 0
            while stack:
                node, depth = stack.pop()
                if id(node) in seen or depth > 8 or nodes >= 400:
                    continue
                seen.add(id(node))
                nodes += 1
                try:
                    br = node.BoundingRectangle
                except Exception:
                    br = None
                # 候选判定：含光标 → 记最小；但无论如何都继续下钻子树（父节点可能 0x0）
                if br and br.width() > 0 and br.height() > 0 \
                        and (br.left <= pt.x <= br.right and br.top <= pt.y <= br.bottom):
                    area = br.width() * br.height()
                    if best is None or area < best_area:
                        best = node
                        best_area = area
                try:
                    kids = node.GetChildren()
                except Exception:
                    kids = []
                for k in kids:
                    stack.append((k, depth + 1))
            out["deepest_nodes"] = str(nodes)
            out["deepest"] = _desc(best) if best else "None"
    _probe_with_timeout("C.descend", probe_descend, 8)


if __name__ == "__main__":
    main()
