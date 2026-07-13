"""Command: 遍历元素列表"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="forEachElement", label="遍历元素列表",
    category="", runtime="control",
    icon="fa-list-check", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    is_container=True,
    closes_with="endLoop",
    description="遍历页面上匹配的元素列表，对每个元素执行循环体",
    category_order=50,
    command_order=10,
)
class ForEachElementHandler:
    params = [
        Param("elementName", "目标元素列表", "element-list", required=True, group="主属性"),
        Param("itemVar", "当前项变量", "string", default="item"),
        Param("indexVar", "索引变量", "string", default="index"),
        Param("scope", "匹配范围", "select", default="local", options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}], group="advanced"),
    ]