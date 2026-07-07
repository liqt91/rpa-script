"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="scrollOneScreen", label="滚动一屏", category="页面操作", runtime="extension",
    icon="fa-arrows-alt-v", icon_color="text-purple-500", bg_color="bg-purple-50", category_order=60, command_order=50)
class ScrollOneScreenHandler:
    params = [
        Param("scrollContainer", "滚动容器", "elementName", required=False, group="主属性"),
        Param("direction", "方向", "select",
              options=[{"label": "向下", "value": "down"}, {"label": "向上", "value": "up"}], default="down"),
    ]
