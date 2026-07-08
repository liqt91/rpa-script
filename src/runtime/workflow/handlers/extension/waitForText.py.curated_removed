"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="waitForText", label="等待文本出现", category="等待", runtime="extension",
    icon="fa-font", icon_color="text-yellow-500", bg_color="bg-yellow-50", category_order=20, command_order=80)
class WaitForTextHandler:
    params = [
        Param("text", "文本内容", "str-input", required=True),
    ]


# ═══════════════════════════════════════════════════════════
# 页面操作
# ═══════════════════════════════════════════════════════════
