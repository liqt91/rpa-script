"""Command: 获取页面信息"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="getPageInfo", label="获取页面信息",
    category="浏览器元素操作", runtime="extension",
    icon="fa-info-circle", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="获取页面元信息（标题/URL/语言/描述/关键词），可选读取 og:title 等 meta",
    category_order=20,
    command_order=59,
)
class GetPageInfoHandler:
    params = [
        Param("includeMeta", "读取 meta 信息", "boolean", default=True, group="advanced", description="同时读取 meta description/keywords/og:title"),
        Param("resultVar", "保存到变量", "string", default="pageInfo", group="output", description="页面信息对象（含 title/url/lang/description/keywords）将保存到此变量"),
    ]