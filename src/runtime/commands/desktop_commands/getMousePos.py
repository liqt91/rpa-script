"""
读取鼠标坐标 — getMousePos (backend)

读取当前鼠标在屏幕上的坐标 (x, y)。使用 Win32 GetCursorPos 获取虚拟屏幕坐标系
坐标（多显示器时副屏可为负）。结果可写入变量供下游引用。仅支持 Windows。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import clean_var_ref


@register_handler(cmd="getMousePos", label="读取鼠标坐标",
    category="桌面操作", runtime="backend",
    icon="fa-location-arrow", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="读取当前鼠标在屏幕上的坐标 (x, y)，结果可写入变量供下游引用",
    category_order=50,
    command_order=24,
)
class GetMousePosHandler:
    params = [
        Param("resultVar", "结果存入变量", "str-var", default="", group="output", placeholder="坐标字典存入此变量，如 mousePos"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import get_cursor_pos, is_windows

        extra = instr.get("extra", {})
        result_var = clean_var_ref(extra.get("resultVar", ""))

        if not is_windows():
            result = {"error": "当前系统非 Windows，无法读取鼠标坐标"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                   "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        pos = get_cursor_pos()
        if pos is None:
            result = {"error": "未能读取到鼠标坐标"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                   "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        if result_var:
            runner.vars[result_var] = pos

        result = {**pos, "log": f"鼠标坐标 ({pos['x']}, {pos['y']})"}
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                               "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True