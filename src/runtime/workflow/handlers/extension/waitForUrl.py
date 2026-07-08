"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="waitForUrl", label="等待URL变化", category="等待", runtime="extension",
    icon="fa-link", icon_color="text-yellow-500", bg_color="bg-yellow-50", category_order=20, command_order=70)
class WaitForUrlHandler:
    params = [
        Param("expectedUrl", "目标URL包含", "str-input", placeholder="留空则等待任何变化"),
    ]
