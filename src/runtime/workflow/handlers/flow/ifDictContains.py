"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(cmd="ifDictContains", label="如果字典包含键", category="条件判断", runtime="control",
    is_container=True, closes_with="endIf",
    icon="fa-book", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=70)
class IfDictContainsHandler:
    params = [
        Param("dictVar", "字典变量", "str-var", required=True),
        Param("key", "键名", "str-input", required=True),
    ]


# ─── 异常处理 ────────────────────────────────────────────────
    @staticmethod
    async def evaluate(runner, instr):
        import logging
        logger = logging.getLogger(__name__)
        from src.runtime.workflow.extension_runner import _clean_var_ref
        extra = runner._resolve_vars(instr.get("extra") or {}, runner.vars)
        dict_name = _clean_var_ref(extra.get("dictName", ""))
        key = runner._resolve_vars(str(extra.get("key", "")), runner.vars)
        actual = runner.vars.get(dict_name)
        if isinstance(actual, dict):
            return key in actual
        logger.warning(f"ifDictContains: {dict_name} is not a dict")
        return False

