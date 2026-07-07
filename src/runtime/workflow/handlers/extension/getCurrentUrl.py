"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="getCurrentUrl", label="获取当前URL", category="页面导航", runtime="extension",
    icon="fa-link", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=10, command_order=40,
    description="获取当前页面 URL，保存到变量")
class GetCurrentUrlHandler:
    params = [
        Param("saveToVar", "保存到变量", "varName", required=True, group="output"),
    ]


# ═══════════════════════════════════════════════════════════
# 等待
# ═══════════════════════════════════════════════════════════
