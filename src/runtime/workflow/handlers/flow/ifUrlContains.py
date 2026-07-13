"""判断 URL 包含 — 控制流"""
from ..registry import register_handler, Param
@register_handler(cmd="ifUrlContains", label="判断URL包含", category="条件判断", runtime="control",
    is_container=True, closes_with="endIf",
    icon="fa-link", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=30,
    description="判断当前页面 URL 是否包含指定文本")
class IfUrlContainsHandler:
    params = [
        Param("urlPattern", "URL 包含", "str-input", required=True, placeholder="URL 包含的文本"),
    ]

    @staticmethod
    async def evaluate(runner, instr):
        extra = runner._resolve_vars(instr.get("extra") or {}, runner.vars)
        url = await runner._get_current_url()
        pattern = extra.get("urlPattern", "")
        return pattern in url
