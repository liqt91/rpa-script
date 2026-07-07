"""字典操作 — setDictValue, getDictValue, removeDictKey, stringConcat"""
from ..registry import register_handler, Param
from ..utils import resolve_vars

@register_handler(type="setDictValue", label="设置字典值", category="变量操作", runtime="backend",
    icon="fa-book", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=40)
class SetDictValueHandler:
    params = [
        Param("dictName", "字典变量名", "varName", required=True),
        Param("key", "键名", "text", required=True),
        Param("value", "值", "text"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        name = extra.get("dictName", "")
        key = extra.get("key", "")
        value = resolve_vars(str(extra.get("value", "")), runner.vars)
        if name not in runner.vars or not isinstance(runner.vars[name], dict):
            runner.vars[name] = {}
        runner.vars[name][key] = value
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "success",
            "result": {"setDictValue": name, "key": key}})
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"),
            "result": {"setDictValue": name}})
        return True
