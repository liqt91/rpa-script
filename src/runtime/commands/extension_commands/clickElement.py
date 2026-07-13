"""点击元素 — 扩展端注册桩"""
from src.runtime.workflow.handlers.registry import register_handler, Param


@register_handler(
    cmd="clickElement", label="点击元素", category="元素操作", runtime="extension",
    icon="fa-hand-pointer", icon_color="text-blue-500", bg_color="bg-blue-50",
    category_order=40, command_order=10,
    description="点击页面上的一个元素")
class ClickElementHandler:
    params = [
        Param("elementName", "元素", "str-element", required=True),
        Param("scope", "匹配范围", "str-dropdown", default="local",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              group="advanced"),
        Param("loopAnchor", "锚点元素", "str-var", default="", group="anchor"),
        Param("visibilityMode", "元素可见性", "str-dropdown", default="visible",
              options=[{"label": "仅可见", "value": "visible"}, {"label": "所有", "value": "any"}],
              group="advanced"),
    ]
    # JS handler: doClick
