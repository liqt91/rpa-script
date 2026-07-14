"""Command: 查找父窗口 — findParent (backend)

获取指定控件的父窗口句柄，存入变量供后续使用。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import clean_var_ref


@register_handler(
    cmd="findParentWin32", label="查找父控件 (Win32)",
    category="桌面操作", runtime="backend",
    icon="fa-arrow-up", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="获取指定控件的父窗口句柄",
    category_order=60, command_order=12,
    summary_tpl="{parentWindow} -> parent",
)
class FindParentHandler:
    params = [
        Param("childWindow", "子窗口 (HWND变量)", "str-var", required=True,
              placeholder="引用已知的子控件句柄变量"),
        Param("resultVar", "结果存入变量", "str-var", default="",
              placeholder="父窗口句柄存入此变量"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import get_parent_window, get_window_text, get_class_name, is_windows, window_exists

        extra = instr.get("extra", {})
        child_var = clean_var_ref(extra.get("childWindow", ""))
        result_var = clean_var_ref(extra.get("resultVar", ""))

        if not is_windows():
            result = {"error": "当前系统非 Windows"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        child_hwnd = runner.vars.get(child_var)
        if not child_hwnd or not window_exists(child_hwnd):
            result = {"error": f"子窗口句柄无效: {child_var} = {child_hwnd}"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        parent_hwnd = get_parent_window(child_hwnd)
        if not parent_hwnd:
            result = {"error": "未找到父窗口（可能是顶层窗口）"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        if result_var:
            runner.vars[result_var] = parent_hwnd

        result = {
            "hwnd": parent_hwnd,
            "title": get_window_text(parent_hwnd),
            "class_name": get_class_name(parent_hwnd),
            "log": f"父窗口: {get_class_name(parent_hwnd)} \"{get_window_text(parent_hwnd)}\"",
        }
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
