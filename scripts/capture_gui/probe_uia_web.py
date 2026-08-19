"""勘测脚本：连续捕获多个网页元素，验证 UIA→CSS/XPath 可行性（不依赖扩展/后端）。

复用现有全屏遮罩捕获（overlay_mask.run_capture_mask）——半透明遮罩 + 鼠标穿透 +
hover 蓝框 + Alt+点击。并把 `_extension_online` 临时钉死为 False，**强制走本地
UIA 网页拾取**，验证"网页捕获脱离扩展"。

用法：
    python scripts/capture_gui/probe_uia_web.py

交互（循环）：
    1. 半透明遮罩覆盖全屏，透过它能看到网页；
    2. 移动鼠标到目标网页元素上 → hover 蓝框实时高亮（本地 UIA DOM 深搜）；
    3. Alt+点击 捕获该元素 → 遮罩消失，结果打印并写入
       data/probe-uia-web-序号.json；
    4. 按 Enter 继续捕获下一个元素；直接 Ctrl+C / Esc 退出。

每次捕获后还会打印一条 `document.querySelector(...)` 验证命令：把它贴到浏览器
DevTools Console 执行，返回的元素若就是刚捕获的那个（或唯一/可见），即证明该
选择器可用。
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_HERE)          # scripts/
_ROOT = os.path.dirname(_SCRIPTS)          # 仓库根（overlay_mask 用 scripts.xxx 绝对导入）
sys.path.insert(0, _SCRIPTS)
sys.path.insert(0, _ROOT)

from capture_gui import overlay as ov  # noqa: E402
from capture_gui import overlay_mask  # noqa: E402
from capture_gui.store import _info_to_dict  # noqa: E402


def _print_info(info, seq: int):
    print("=" * 60)
    print(f"[{seq}] element_type : {info.element_type}")
    print(f"[{seq}] name         : {info.name}")
    print(f"[{seq}] css_selector : {info.css_selector!r}")
    print(f"[{seq}] xpath        : {info.xpath!r}")
    print(f"[{seq}] control_type : {info.control_type}")
    if info.automation_id:
        print(f"[{seq}] automation_id: {info.automation_id}")
    if info.uia_path:
        print(f"[{seq}] uia_path     : {len(info.uia_path)} 层")
    if info.candidates:
        print(f"[{seq}] candidates:")
        for c in info.candidates[:8]:
            print(f"  [{c.get('score', 0):>3}] {c.get('family', ''):<6} {c.get('syntax', '')}")
    else:
        print(f"[{seq}] !! 无 candidates —— 该元素无可派生定位线索（纯视觉 div），需图像/父级兜底")
    # 验证命令：浏览器 DevTools 里执行确认选择器可命中
    if info.css_selector:
        print(f"[{seq}] 验证（浏览器 DevTools Console 执行）:")
        print(f"      document.querySelector({info.css_selector!r})   // 应返回刚捕获的元素")
    print()


def main():
    ov._extension_online = lambda *a, **k: False  # 强制本地 UIA 路径
    out_dir = os.path.join(_ROOT, "data")
    os.makedirs(out_dir, exist_ok=True)
    seq = 0
    while True:
        seq += 1
        print(f">>> 第 {seq} 次捕获：把鼠标移到目标网页元素上，Alt+点击（Enter=继续，Ctrl+C=退出）")
        info = overlay_mask.run_capture_mask("desktop")
        if info is None:
            print("（取消本轮）")
        else:
            _print_info(info, seq)
            out_path = os.path.join(out_dir, f"probe-uia-web-{seq}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(_info_to_dict(info, keep_screenshot=False), f,
                          ensure_ascii=False, indent=2)
            print(f"已写入 {out_path}")
        try:
            input("按 Enter 捕获下一个元素（Ctrl+C 退出）...")
        except (KeyboardInterrupt, EOFError):
            print("\n退出")
            break


if __name__ == "__main__":
    main()