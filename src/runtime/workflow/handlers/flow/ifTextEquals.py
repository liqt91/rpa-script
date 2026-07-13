"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(cmd="ifTextEquals", label="如果文本相等", category="条件判断", runtime="control",
    is_container=True, closes_with="endIf",
    icon="fa-equals", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=30)
class IfTextEqualsHandler:
    params = [
        Param("text", "文本A", "str-input", required=True),
        Param("compareTo", "文本B", "str-input", required=True),
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
        met = text == expected
        logger.info(f"ifTextEquals text={text!r} expected={expected!r} met={met}")
        return met

