"""Command: 获取超链接"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="getElementLink", label="获取超链接",
    category="数据提取", runtime="extension",
    icon="fa-link", icon_color="text-blue-500",
    bg_color="bg-blue-50",
    description="获取指定元素的 href 链接地址",
    category_order=40,
    command_order=20,
)
class GetElementLinkHandler:
    params = [
        Param("elementName", "目标元素", "element", required=True, group="主属性", placeholder="选择一个已捕获的链接元素"),
        Param("scope", "匹配范围", "select", default="local", options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}], group="advanced"),
        Param("resultVar", "保存到变量", "string", default="link1", group="output", description="链接地址将保存到此变量中"),
    ]