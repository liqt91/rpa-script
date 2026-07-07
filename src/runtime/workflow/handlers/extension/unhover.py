"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="unhover", label="取消悬停", category="元素操作", runtime="extension",
    icon="fa-hand-pointer", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=31)
class UnhoverHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
    ]
