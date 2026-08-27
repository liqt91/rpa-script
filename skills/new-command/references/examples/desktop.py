# desktop 黄金样例（照抄改 cmd 名与逻辑）
# 放 src/runtime/commands/desktop_commands/myCommand.py
# 底层能力放 _win32.py / _uia.py / _desktop_ref.py，execute 里 from ._xxx import ...

from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import clean_var_ref


@register_handler(cmd="myCommand", label="我的桌面指令", category="桌面操作", runtime="backend",
    icon="fa-cog", icon_color="text-purple-500", bg_color="bg-purple-50",
    category_order=50, command_order=10, description="指令描述")
class MyCommandHandler:
    params = [
        Param("resultVar", "结果存入变量", "str-var", default="", group="output"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import is_windows  # 或 from ._uia import ... / from ._desktop_ref import ...

        extra = instr.get("extra", {})
        result_var = clean_var_ref(extra.get("resultVar", ""))

        if not is_windows():
            result = {"error": "当前系统非 Windows"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                   "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        # 业务逻辑（调 _win32/_uia 的底层函数）
        pos = {"x": 0, "y": 0}
        if result_var:
            runner.vars[result_var] = pos

        result = {**pos}
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                               "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
