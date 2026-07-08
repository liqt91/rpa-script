"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="clearInput", label="清空输入框", category="元素操作", runtime="extension",
    icon="fa-eraser", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=40)
class ClearInputHandler:
    params = [
        Param("element_name", "元素", "str-element", required=True, group="主属性"),
        Param("scope", "匹配范围", "str-dropdown",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]
