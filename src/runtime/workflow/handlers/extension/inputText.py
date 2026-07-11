"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(cmd="inputText", label="输入文本", category="元素操作", runtime="extension",
    icon="fa-keyboard", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=20)
class InputTextHandler:
    params = [
        Param("element_name", "元素", "str-element", required=True),
        Param("text", "文本内容", "str-input", required=True),
        Param("scope", "匹配范围", "str-dropdown",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
        Param("loopAnchor", "锚点元素", "str-var", default="", group="anchor"),
        Param("clearFirst", "先清空", "bool-check", default=True, group="advanced"),
    ]
