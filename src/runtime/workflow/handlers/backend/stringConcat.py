"""字典操作 — setDictValue, getDictValue, removeDictKey, stringConcat"""
from ..registry import register_handler, Param
from ..utils import resolve_vars

@register_handler(type="stringConcat", label="字符串拼接", category="变量操作", runtime="backend",
    icon="fa-plus", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=70)
class StringConcatHandler:
    params = [
        Param("parts", "拼接内容", "text", required=True, placeholder='用 + 连接, 如 "hello" + ${name}'),
        Param("saveToVar", "保存到变量", "varName", group="output"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        parts = extra.get("parts", "")
        save_to = extra.get("saveToVar") or extra.get("varName", "")
        result = resolve_vars(parts, runner.vars)
        if save_to:
            runner.vars[save_to] = result
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "success",
            "result": {"stringConcat": result[:200]}})
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"),
            "result": {"stringConcat": str(result)[:200]}})
        return True
