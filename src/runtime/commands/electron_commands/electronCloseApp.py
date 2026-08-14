"""关闭 Electron 应用 — electronCloseApp"""
from src.runtime.workflow.handlers.registry import register_handler


@register_handler(
    cmd="electronCloseApp", label="关闭 Electron 应用",
    category="Electron 应用", runtime="backend",
    icon="fa-window-close", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="关闭当前 Electron 应用（终止进程）",
    category_order=55, command_order=7,
    summary_tpl="关闭应用",
)
class ElectronCloseHandler:
    params = []

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from src.runtime.workflow.electron_manager import electron_manager

        result = await electron_manager.close()
        if result.get("error"):
            result = {"error": result["error"]}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False
        result["log"] = "Electron 应用已关闭"
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
