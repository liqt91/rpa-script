"""Command: 提取邮箱地址"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="extractEmails", label="提取邮箱地址",
    category="浏览器元素操作", runtime="extension",
    icon="fa-envelope", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="提取页面上的邮箱地址（mailto 链接与正文文本），支持自定义正则",
    category_order=20,
    command_order=58,
)
class ExtractEmailsHandler:
    params = [
        Param("pattern", "匹配正则", "string", default="", group="主属性", placeholder="留空使用内置邮箱正则", description="留空使用内置邮箱正则"),
        Param("deduplicate", "去重", "boolean", default=True, group="advanced"),
        Param("resultVar", "保存到变量", "string", default="emails", group="output", description="提取到的邮箱列表（数组，含 email/source）将保存到此变量"),
    ]