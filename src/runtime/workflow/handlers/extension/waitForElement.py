"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(cmd="waitForElement", label="等待元素出现", category="等待", runtime="extension",
    icon="fa-eye", icon_color="text-yellow-500", bg_color="bg-yellow-50", category_order=20, command_order=40)
class WaitForElementHandler:
    params = [
        Param("element_name", "元素", "str-element", required=True),
        Param("visibilityMode", "元素可见性", "str-dropdown",
              options=[{"label": "仅可见", "value": "visible"}, {"label": "所有", "value": "any"}], default="visible"),
    ]
