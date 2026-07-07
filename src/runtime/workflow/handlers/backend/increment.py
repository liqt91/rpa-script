"""递增/递减 — increment"""
from ..registry import register_handler, Param


@register_handler(type="increment", label="递增/递减", category="变量操作", runtime="backend",
    icon="fa-sort-numeric-up", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=30)
class IncrementHandler:
    params = [
        Param("varName", "变量名", "varName", required=True),
        Param("step", "步长", "number", default=1),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        var_name = extra.get("varName", "")
        step = float(extra.get("step", 1))
        runner.vars[var_name] = runner.vars.get(var_name, 0) + step
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "success",
            "result": {"increment": var_name}})
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"),
            "result": {"increment": var_name}})
        return True
