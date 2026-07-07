"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="rightClick", label="右键元素", category="元素操作", runtime="extension",
    icon="fa-mouse-pointer", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=12)
class RightClickHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]
