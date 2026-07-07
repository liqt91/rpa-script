"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="scrollBy", label="滚动指定距离", category="页面操作", runtime="extension",
    icon="fa-arrows-alt-v", icon_color="text-purple-500", bg_color="bg-purple-50", category_order=60, command_order=60)
class ScrollByHandler:
    params = [
        Param("scrollContainer", "滚动容器", "elementName", required=False, group="主属性"),
        Param("x", "X像素", "number", default=0),
        Param("y", "Y像素", "number", default=300),
    ]
