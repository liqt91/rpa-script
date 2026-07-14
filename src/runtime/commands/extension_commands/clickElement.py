"""Command: 点击元素"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="clickElement", label="点击元素",
    category="element", runtime="extension",
    icon="fa-hand-pointer", icon_color="text-blue-500",
    bg_color="bg-blue-50",
    description="点击页面上的一个元素",
    category_order=40,
    command_order=10,
    summary_tpl="{elementName}",
)
class ClickElementHandler:
    params = [
        Param("elementName", "元素", "element", required=True),
        Param("scope", "匹配范围", "select", default="local", options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}], group="advanced"),
        Param("loopAnchor", "锚点元素", "string", default="", group="anchor"),
        Param("visibilityMode", "元素可见性", "select", default="visible", options=[{"label": "仅可见", "value": "visible"}, {"label": "所有", "value": "any"}], group="advanced"),
    ]