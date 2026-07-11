"""字典操作 — setDictValue, getDictValue, removeDictKey, stringConcat"""
from ..registry import register_handler, Param
from ..utils import resolve_vars, clean_var_ref

@register_handler(cmd="getDictValue", label="读取字典值", category="变量操作", runtime="backend",
    icon="fa-book-open", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=50)
class GetDictValueHandler:
    params = [
        Param("dictName", "字典变量名", "str-var", required=True),
        Param("key", "键名", "str-input", required=True),
        Param("saveToVar", "保存到变量", "str-var", group="output"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        name = clean_var_ref(extra.get("dictName", ""))
        key = extra.get("key", "")
        save_to = clean_var_ref(extra.get("saveToVar") or extra.get("varName", ""))
        val = runner.vars.get(name, {}).get(key)
        if save_to:
            runner.vars[save_to] = val
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "success",
            "result": {"getDictValue": name, "key": key, "value": val}})
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"),
            "result": {"getDictValue": name}})
        return True
