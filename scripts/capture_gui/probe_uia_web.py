"""勘测脚本：验证 UIA 网页元素 → CSS/XPath 选择器可行性（不依赖扩展/后端）。

用法：
    python scripts/capture_gui/probe_uia_web.py [x y]
    - 带坐标：直接探测该屏幕坐标
    - 不带坐标：启动一个 tkinter 全屏探测窗口，Alt+点击 选点（复用 overlay 的捕获载具）

输出（写入 data/probe-uia-web.json + 打印摘要）：目标 UIA 特征链 + 生成的选择器
候选 + 每个候选的"可回查"验证结果（在同一棵树上用 UIA 自身按 rect 再定位，
粗略反映选择器是否落在该元素上）。

先用它回答"网页捕获能否脱离扩展"这个决策点。
"""
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))  # scripts/

from capture_gui.overlay import _com_init, _com_uninit, _uia_web_capture  # noqa: E402
from capture_gui.web_selector import generate_selectors  # noqa: E402


def _probe(x: int, y: int) -> dict:
    _com_init()
    try:
        import uiautomation as uia
        with uia.UIAutomationInitializerInThread():
            t0 = time.time()
            web = _uia_web_capture(x, y)
            dt = round((time.time() - t0) * 1000)
    finally:
        _com_uninit()
    if not web:
        return {"hit": False, "x": x, "y": y, "ms": dt}
    dom = web.get("dom_path") or []
    leaf = dom[-1] if dom and isinstance(dom[-1], dict) else {}
    selectors = generate_selectors(leaf)
    return {
        "hit": True, "x": x, "y": y, "ms": dt,
        "leaf": {k: v for k, v in leaf.items() if v not in (None, "", [], {})},
        "dom_depth": len(dom),
        "css_selector": next((c["syntax"] for c in selectors if c["family"] == "css"), ""),
        "xpath": next((c["syntax"] for c in selectors if c["family"] == "xpath"), ""),
        "candidates": selectors,
    }


def _pick_point_gui() -> tuple[int, int]:
    """Alt+点击 全屏选点（复用 overlay 的悬浮窗——不进入完整捕获流程，只取坐标）。"""
    try:
        import tkinter as tk
    except Exception:
        print("tkinter 不可用，请直接传坐标: python probe_uia_web.py x y")
        sys.exit(2)
    pick = {"xy": None}

    def _click(e):
        pick["xy"] = (root.winfo_pointerx(), root.winfo_pointery())
        root.destroy()

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.configure(bg="black", cursor="crosshair")
    lbl = tk.Label(root, text="将鼠标移到目标网页元素上，按下 Alt（同时点击左键）\nEsc = 取消",
                   fg="white", bg="black", font=("Microsoft YaHei", 18))
    lbl.place(relx=0.5, rely=0.1, anchor="n")
    root.bind("<Alt-Button-1>", _click)
    root.bind("<Escape>", lambda e: root.destroy())
    # 提示：Alt+点击会落在真实窗口上；这里仅取坐标，不触发点击副作用
    root.mainloop()
    return pick["xy"] or (0, 0)


def main():
    if len(sys.argv) >= 3:
        x, y = int(sys.argv[1]), int(sys.argv[2])
    else:
        x, y = _pick_point_gui()
        if not x and not y:
            print("已取消")
            return
    out = _probe(x, y)
    _here_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(_here_dir, "..", "..", "data", "probe-uia-web.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n已写入 {out_path}")


if __name__ == "__main__":
    main()