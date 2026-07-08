"""追加到列表 — appendToList"""
from ..registry import register_handler, Param
from ..utils import resolve_vars, clean_var_ref


@register_handler(type="appendToList", label="追加到列表", category="变量操作", runtime="backend",
    icon="fa-list-ol", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=20)
class AppendToListHandler:
    params = [
        Param("listName", "列表变量名", "str-var", required=True),
        Param("value", "追加的值", "str-input"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        list_name = clean_var_ref(extra.get("listName", ""))
        value = resolve_vars(str(extra.get("value", "")), runner.vars)
        if list_name not in runner.vars or not isinstance(runner.vars[list_name], list):
            runner.vars[list_name] = []
        runner.vars[list_name].append(value)
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "success", "result": {"appendToList": list_name}})
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"), "result": {"appendToList": list_name}})
        return True
