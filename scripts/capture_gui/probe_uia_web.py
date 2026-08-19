"""勘测脚本：验证 UIA 网页元素 → CSS/XPath 选择器可行性（不依赖扩展/后端）。

复用现有全屏遮罩捕获（overlay_mask.run_capture_mask）——半透明遮罩 + 鼠标穿透 +
hover 蓝框 + Alt+点击。并把 `_extension_online` 临时钉死为 False，**强制走本地
UIA 网页拾取**（不管浏览器扩展是否在线），验证"网页捕获脱离扩展"这一决策点。

用法：
    python scripts/capture_gui/probe_uia_web.py

交互：
    1. 半透明遮罩覆盖全屏，能透过它看到下方网页；
    2. 把鼠标移到目标网页元素上 → hover 蓝框实时高亮（走本地 UIA DOM 深搜）；
    3. Alt+点击 捕获该元素 → 遮罩消失；
    4. 结果打印并写入 data/probe-uia-web.json（UIA 特征链 + 生成的 css/xpath 候选）。
    Esc 取消。
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


def main():
    # 强制本地 UIA 路径：扩展在线与否都不影响验证（扩展路径验证的是扩展，不是 UIA）
    ov._extension_online = lambda *a, **k: False
    info = overlay_mask.run_capture_mask("desktop")
    if info is None:
        print("已取消或未捕获到元素")
        return
    d = _info_to_dict(info, keep_screenshot=False)
    out_path = os.path.join(_HERE, "..", "..", "data", "probe-uia-web.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print(f"element_type : {info.element_type}")
    print(f"name         : {info.name}")
    print(f"css_selector : {info.css_selector!r}")
    print(f"xpath        : {info.xpath!r}")
    print(f"control_type : {info.control_type}")
    if info.automation_id:
        print(f"automation_id: {info.automation_id}")
    if info.uia_path:
        print(f"uia_path     : {len(info.uia_path)} 层")
    if info.candidates:
        print("candidates:")
        for c in info.candidates[:12]:
            print(f"  [{c.get('score', 0):>3}] {c.get('family', ''):<6} {c.get('syntax', '')}")
    elif info.element_type == "web":
        print("!! 无 candidates —— 该元素无可派生定位线索（纯视觉 div），需图像/父级兜底")
    print(f"\n已写入 {out_path}")


if __name__ == "__main__":
    main()