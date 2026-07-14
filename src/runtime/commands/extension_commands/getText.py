"""Command: 获取文本"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="getText", label="获取文本",
    category="data", runtime="extension",
    icon="fa-font", icon_color="text-green-500",
    bg_color="bg-green-50",
    description="获取页面元素的文本内容",
    category_order=40,
    command_order=10,
    summary_tpl="{elementName}",
)
class GetTextHandler:
    params = [
        Param("elementName", "目标元素", "element", group="主属性", placeholder="选择一个已捕获的元素"),
        Param("scope", "匹配范围", "select", default="local", options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}], group="advanced"),
        Param("resultVar", "保存到变量", "string", default="text1", group="output"),
    ]