"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="clickIfExists", label="点击元素(如果存在)", category="元素操作", runtime="extension",
    icon="fa-hand-pointer", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=13)
class ClickIfExistsHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]
