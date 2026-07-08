"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="pressKey", label="按键", category="页面操作", runtime="extension",
    icon="fa-keyboard", icon_color="text-purple-500", bg_color="bg-purple-50", category_order=60, command_order=30,
    description="发送键盘按键")
class PressKeyHandler:
    params = [
        Param("key", "按键", "str-input", required=True, default="Enter", placeholder="Enter / Tab / Escape / ..."),
        Param("modifiers", "修饰键", "str-input", default="", placeholder="如 Ctrl,Alt,Shift", group="advanced",
              description="逗号分隔的修饰键"),
    ]


# ═══════════════════════════════════════════════════════════
# 数据表格
# ═══════════════════════════════════════════════════════════
