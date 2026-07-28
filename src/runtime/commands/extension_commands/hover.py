"""Command: 鼠标悬停"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="hover", label="鼠标悬停",
    category="元素操作", runtime="extension",
    icon="fa-hand-pointer", icon_color="text-blue-500",
    bg_color="bg-blue-50",
    description="将鼠标悬停在指定元素上",
    category_order=40,
    command_order=30,
)
class HoverHandler:
    params = [
        Param("elementName", "目标元素", "element", group="主属性", placeholder="选择一个已捕获的元素"),
        Param("scope", "匹配范围", "select", default="local", options=[{"label": "当前循环元素内", "value": "local"}, {"label": "全页面", "value": "global"}], group="advanced"),
    ]