"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="waitForElementHide", label="等待元素消失", category="等待", runtime="extension",
    icon="fa-eye-slash", icon_color="text-yellow-500", bg_color="bg-yellow-50", category_order=20, command_order=50)
class WaitForElementHideHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True),
    ]
