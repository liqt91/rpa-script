"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(cmd="ifTextContains", label="如果文本包含", category="条件判断", runtime="control",
    is_container=True, closes_with="endIf",
    icon="fa-font", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=20)
class IfTextContainsHandler:
    params = [
        Param("text", "源文本", "str-input", required=True, placeholder="支持 ${var} 变量"),
        Param("substring", "包含文本", "str-input", required=True),
    ]
    @staticmethod
    async def evaluate(runner, instr):
        import logging
        logger = logging.getLogger(__name__)
        extra = runner._resolve_vars(instr.get("extra") or {}, runner.vars)
        locator = instr.get("locator") or extra.get("locator", "")
        selector_family = instr.get("selectorFamily") or extra.get("selector_family", "css")
        timeout = extra.get("timeout", 3)
        text = await runner._get_element_text(locator, selector_family, timeout=timeout, extra=extra)
        expected = extra.get("text", "")
        op = extra.get("operator", "contains")
        if op == "notContains": met = expected not in text
        elif op == "startsWith": met = text.startswith(expected)
        elif op == "endsWith": met = text.endswith(expected)
        else: met = expected in text
        logger.info(f"ifTextContains text={text!r} expected={expected!r} op={op} met={met}")
        return met

