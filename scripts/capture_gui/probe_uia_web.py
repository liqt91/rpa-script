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

    # ── 完整层级打印（排查用）──
    # dom_editor_path：前端手动编辑 tab 的形态（tag/id/classes/attrs）
    editor_path = getattr(info, "dom_editor_path", None) or []
    if editor_path:
        print(f"[{seq}] == dom_editor_path（前端手动编辑形态，{len(editor_path)} 层，含叶子） ===")
        _print_path_min(editor_path, seq)
    # uia_path：原始 UIA 链（control_type/class/automation_id/name/aria）
    uia_path = getattr(info, "uia_path", None) or (info.dom_path or [])
    if uia_path:
        print(f"[{seq}] == uia_path（原始 UIA 链，{len(uia_path)} 层） ===")
        _print_path_raw(uia_path, seq)

    if info.candidates:
        print(f"[{seq}] candidates:")
        for c in info.candidates[:8]:
            print(f"  [{c.get('score', 0):>3}] {c.get('family', ''):<6} {c.get('syntax', '')}")
    else:
        print(f"[{seq}] !! 无 candidates —— 该元素无可派生定位线索（纯视觉 div），需图像/父级兜底")
    if info.css_selector:
        print(f"[{seq}] 验证（浏览器 DevTools Console 执行）:")
        print(f"      document.querySelector({info.css_selector!r})   // 应返回刚捕获的元素")
    print()


def _print_path_min(path, seq):
    """打印 dom_editor_path：tag#id.class classes attrs"""
    for i, nd in enumerate(path):
        if not isinstance(nd, dict):
            print(f"  [{i}] {nd!r}")
            continue
        tag = nd.get("tag") or "?"
        pid = nd.get("id") or ""
        cls = nd.get("classes") or []
        attrs = nd.get("attrs") or {}
        # attrs 只打印非空且非 id/class 的（id/class 已单列）
        extra = {k: v for k, v in attrs.items() if v not in (None, "")}
        sel = tag
        if pid:
            sel += f"#{pid}"
        if cls:
            sel += "." + ".".join(cls[:3])
        name = nd.get("name") or nd.get("control_type") or ""
        print(f"  [{i:>2}] <{sel}> name={name!r} attrs={extra!r}")


def _print_path_raw(path, seq):
    """打印 uia_path：control_type | class_name | automation_id | name | aria_role"""
    for i, nd in enumerate(path):
        if not isinstance(nd, dict):
            print(f"  [{i}] {nd!r}")
            continue
        ct = nd.get("control_type") or ""
        cls = nd.get("class_name") or ""
        aid = nd.get("automation_id") or ""
        nm = (nd.get("name") or "")[:30]
        role = nd.get("aria_role") or ""
        print(f"  [{i:>2}] {ct:<22} class={cls!r} id={aid!r} role={role!r} name={nm!r}")


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