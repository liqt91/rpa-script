"""Command: 统计包含文本的元素"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="countElementsByText", label="统计包含文本的元素",
    category="浏览器元素操作", runtime="extension",
    icon="fa-list-ol", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="统计页面上文本包含/匹配指定内容（支持正则）的元素数量，结果保存到变量",
    category_order=20,
    command_order=60,
)
class CountElementsByTextHandler:
    params = [
        Param("text", "查找文本", "string", required=True, group="主属性", placeholder="支持 ${var} 变量", description="要查找的文本内容，支持 ${var} 变量"),
        Param("elementName", "范围内元素", "element", group="主属性", placeholder="不填则统计全页面", description="仅在指定的已捕获元素内部统计；不填则在整页统计"),
        Param("matchType", "匹配方式", "select", default="contains", options=[{"label": "包含文本", "value": "contains"}, {"label": "完全等于", "value": "equals"}, {"label": "正则匹配", "value": "regex"}], group="advanced"),
        Param("onlyVisible", "仅统计可见元素", "boolean", default=False, group="advanced"),
        Param("resultVar", "保存到变量", "string", default="count", group="output", description="统计得到的元素数量（整数）将保存到此变量"),
    ]