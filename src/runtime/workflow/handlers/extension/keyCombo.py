"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="keyCombo", label="组合键", category="页面操作", runtime="extension",
    icon="fa-keyboard", icon_color="text-purple-500", bg_color="bg-purple-50", category_order=60, command_order=35)
class KeyComboHandler:
    params = [
        Param("keys", "按键序列", "text", required=True, placeholder="Ctrl+C / Alt+Tab"),
    ]


# ═══════════════════════════════════════════════════════════
# 数据表格
# ═══════════════════════════════════════════════════════════
