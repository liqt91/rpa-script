"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(cmd="ifVarContains", label="如果变量包含", category="条件判断", runtime="control",
    is_container=True, closes_with="endIf",
    icon="fa-search", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=50)
class IfVarContainsHandler:
    params = [
        Param("varName", "变量名", "str-var", required=True),
        Param("substring", "包含文本", "str-input", required=True),
    ]
    @staticmethod
    async def evaluate(runner, instr):
        from src.runtime.workflow.extension_runner import _clean_var_ref
        extra = runner._resolve_vars(instr.get("extra") or {}, runner.vars)
        var_name = _clean_var_ref(extra.get("varName", ""))
        expected = extra.get("value", "")
        op = extra.get("operator", "contains")
        actual = runner.vars.get(var_name)
        if isinstance(actual, list):
            has = expected in actual
            return not has if op == "notContains" else has
        s = str(actual)
        if op == "notContains": return expected not in s
        if op == "startsWith": return s.startswith(expected)
        if op == "endsWith": return s.endswith(expected)
        return expected in s

