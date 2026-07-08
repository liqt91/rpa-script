"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="clickElement", label="点击元素", category="元素操作", runtime="extension",
    icon="fa-hand-pointer", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=10)
class ClickElementHandler:
    params = [
        Param("element_name", "元素", "str-element", required=True),
        Param("scope", "匹配范围", "str-dropdown",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
        Param("loopAnchor", "锚点元素", "str-var", default="", group="anchor"),
        Param("visibilityMode", "元素可见性", "str-dropdown",
              options=[{"label": "仅可见", "value": "visible"}, {"label": "所有", "value": "any"}],
              default="visible", group="advanced"),
    ]
