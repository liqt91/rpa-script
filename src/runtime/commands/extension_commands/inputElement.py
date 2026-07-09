"""输入文本 — 扩展端注册桩"""
from src.runtime.workflow.handlers.registry import register_handler, Param


@register_handler(type="inputElement", label="输入文本", category="元素操作", runtime="extension",
    icon="fa-keyboard", icon_color="text-blue-500", bg_color="bg-blue-50",
    category_order=40, command_order=20,
    description="在页面输入框中输入文本，可选输入完成后按回车")
class InputElementHandler:
    params = [
        Param("element_name", "元素", "str-element", required=True),
        Param("text", "输入内容", "str-input", required=True),
        Param("pressEnter", "输入后按回车", "bool-check", default=False),
        Param("scope", "匹配范围", "str-dropdown", default="local",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              group="advanced"),
        Param("loopAnchor", "锚点元素", "str-var", default="", group="anchor"),
        Param("visibilityMode", "元素可见性", "str-dropdown", default="visible",
              options=[{"label": "仅可见", "value": "visible"}, {"label": "所有", "value": "any"}],
              group="advanced"),
    ]
    # JS handler: doInput
