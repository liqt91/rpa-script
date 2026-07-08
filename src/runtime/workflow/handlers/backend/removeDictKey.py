"""字典操作 — setDictValue, getDictValue, removeDictKey, stringConcat"""
from ..registry import register_handler, Param
from ..utils import resolve_vars, clean_var_ref

@register_handler(type="removeDictKey", label="删除字典键", category="变量操作", runtime="backend",
    icon="fa-trash-alt", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=60)
class RemoveDictKeyHandler:
    params = [
        Param("dictName", "字典变量名", "str-var", required=True),
        Param("key", "键名", "str-input", required=True),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        name = clean_var_ref(extra.get("dictName", ""))
        key = extra.get("key", "")
        if name in runner.vars and isinstance(runner.vars[name], dict):
            runner.vars[name].pop(key, None)
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "success",
            "result": {"removeDictKey": name, "key": key}})
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"),
            "result": {"removeDictKey": name}})
        return True
