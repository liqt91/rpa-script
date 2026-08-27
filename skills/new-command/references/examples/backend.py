# backend 黄金样例（照抄改 cmd 名与逻辑）
# 放 src/runtime/commands/backend_commands/myCommand.py

from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import clean_var_ref


@register_handler(cmd="myCommand", label="我的指令", category="其他", runtime="backend",
    icon="fa-cog", icon_color="text-blue-500", bg_color="bg-blue-50",
    category_order=50, command_order=10, description="指令描述", summary_tpl="{paramName}")
class MyCommandHandler:
    params = [
        Param("paramName", "参数显示名", "string", required=True),
        Param("resultVar", "结果存入变量", "str-var", default="", group="output"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra", {})
        val = extra.get("paramName")
        result_var = clean_var_ref(extra.get("resultVar", ""))

        # 业务逻辑
        result = {"value": val}
        if result_var:
            runner.vars[result_var] = val

        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                               "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
