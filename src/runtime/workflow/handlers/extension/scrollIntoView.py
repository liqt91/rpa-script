"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(cmd="scrollIntoView", label="滚动到元素", category="页面操作", runtime="extension",
    icon="fa-arrow-down", icon_color="text-purple-500", bg_color="bg-purple-50", category_order=60, command_order=10)
class ScrollIntoViewHandler:
    params = [
        Param("element_name", "元素", "str-element", required=True),
        Param("scope", "匹配范围", "str-dropdown",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
        Param("loopAnchor", "锚点元素", "str-var", default="", group="anchor"),
    ]
