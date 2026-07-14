"""Command: 滚动到元素"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="scrollIntoView", label="滚动到元素",
    category="页面操作", runtime="extension",
    icon="fa-arrow-down", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="将页面滚动到指定元素可见的位置",
    category_order=60,
    command_order=10,
    summary_tpl="{elementName}",
)
class ScrollIntoViewHandler:
    params = [
        Param("elementName", "目标元素", "element", group="主属性", placeholder="选择一个已捕获的元素"),
        Param("scope", "匹配范围", "select", default="local", options=[{"label": "当前循环元素内", "value": "local"}, {"label": "全页面", "value": "global"}], group="advanced"),
    ]