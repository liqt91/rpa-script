"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(cmd="ifVarEquals", label="如果变量相等", category="条件判断", runtime="control",
    is_container=True, closes_with="endIf",
    icon="fa-equals", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=40)
class IfVarEqualsHandler:
    params = [
        Param("varName", "变量名", "str-var", required=True),
        Param("compareTo", "比较值", "str-input", required=True),
    ]
    @staticmethod
    async def evaluate(runner, instr):
        from src.runtime.workflow.extension_runner import _clean_var_ref
        extra = runner._resolve_vars(instr.get("extra") or {}, runner.vars)
        var_name = _clean_var_ref(extra.get("varName", ""))
        expected = extra.get("value", "")
        vtype = extra.get("valueType", "string")
        op = extra.get("operator", "equals")
        actual = runner.vars.get(var_name)
        if vtype == "number":
            try:
                fa, fe = float(actual), float(expected)
                if op == "greaterThan": return fa > fe
                if op == "lessThan": return fa < fe
                return fa == fe
            except (ValueError, TypeError):
                return False
        if vtype == "bool":
            return bool(actual) == (str(expected).lower() in ("true", "1", "yes"))
        if op == "greaterThan": return str(actual) > str(expected)
        if op == "lessThan": return str(actual) < str(expected)
        return str(actual) == str(expected)

