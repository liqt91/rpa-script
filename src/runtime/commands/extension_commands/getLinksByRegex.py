"""Command: 正则获取链接"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="getLinksByRegex", label="正则获取链接",
    category="浏览器元素操作", runtime="extension",
    icon="fa-link", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="获取页面上所有匹配正则表达式的链接，支持按 href 或链接文本匹配",
    category_order=20,
    command_order=55,
)
class GetLinksByRegexHandler:
    params = [
        Param("pattern", "匹配正则", "string", required=True, group="主属性", placeholder="如 https://example\\.com/.*"),
        Param("matchField", "匹配对象", "select", default="href", options=[{"label": "链接地址（href）", "value": "href"}, {"label": "链接文本", "value": "text"}, {"label": "两者任一", "value": "any"}], group="advanced"),
        Param("onlyVisible", "仅可见链接", "boolean", default=False, group="advanced"),
        Param("deduplicate", "去重", "boolean", default=True, group="advanced"),
        Param("resultVar", "保存到变量", "string", default="links", group="output", description="匹配到的链接列表（数组，含 href 与 text）将保存到此变量"),
    ]