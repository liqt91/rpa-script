"""
读取屏幕/显示器信息 — readScreenInfoWin32 (backend)

枚举所有显示器（分辨率/坐标/工作区/DPI/刷新率/主屏标志）+ 主屏与虚拟屏幕指标，
返回结构化结果并可写入变量供后续流程引用。仅支持 Windows。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import clean_var_ref


@register_handler(cmd="readScreenInfoWin32", label="读取屏幕信息",
    category="桌面操作", runtime="backend",
    icon="fa-desktop", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="读取所有显示器信息（分辨率/坐标/工作区/DPI/刷新率/主屏标志）及屏幕指标，结果可写入变量供下游引用",
    category_order=50,
    command_order=23,
)
class ReadScreenInfoWin32Handler:
    params = [
        Param("resultVar", "结果存入变量", "str-var", default="", group="output", placeholder="读取到的屏幕信息字典存入此变量，如 screenInfo"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import get_screen_info, is_windows

        extra = instr.get("extra", {})
        result_var = clean_var_ref(extra.get("resultVar", ""))

        if not is_windows():
            result = {"error": "当前系统非 Windows，无法读取屏幕信息"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                   "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        info = get_screen_info()
        if not info:
            result = {"error": "未能读取到显示器信息"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                   "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        if result_var:
            runner.vars[result_var] = info

        result = {
            **info,
            "log": f"读取屏幕信息成功：{info['count']} 个显示器，"
                   f"主屏 {info['screen']['width']}x{info['screen']['height']}，"
                   f"系统 DPI {info['systemDpi']}",
        }
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                               "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
