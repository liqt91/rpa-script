"""Command: 关闭窗口 — closeWindow (backend)

向指定窗口发送 WM_CLOSE 消息关闭窗口。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import clean_var_ref


@register_handler(
    cmd="closeWindowWin32", label="关闭窗口 (Win32)",
    category="桌面操作", runtime="backend",
    icon="fa-window-close", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="向指定窗口发送 WM_CLOSE 消息关闭窗口",
    category_order=60, command_order=35,
    summary_tpl="{parentWindow}",
)
class CloseWindowHandler:
    params = [
        Param("parentWindow", "窗口 (HWND变量)", "str-var", required=True,
              placeholder="引用 findWindow 或 openApp 存入的窗口句柄变量"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import close_window, get_window_text, is_windows, window_exists

        extra = instr.get("extra", {})
        parent_var = clean_var_ref(extra.get("parentWindow", ""))

        if not is_windows():
            result = {"error": "当前系统非 Windows，不支持桌面窗口操作"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        hwnd = runner.vars.get(parent_var)
        if not hwnd or not window_exists(hwnd):
            result = {"error": f"窗口句柄无效: {parent_var} = {hwnd}",
                      "hint": "请先使用 findWindow 或 openApp 获取窗口句柄"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        title = get_window_text(hwnd)
        ok = close_window(hwnd)
        result = {
            "closed": ok,
            "window_title": title,
            "log": f"已关闭窗口: {title}" if ok else f"关闭失败: {title}",
        }
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success" if ok else "error", "result": result})
        if ok:
            await runner._emit({"type": "stepComplete", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "result": result})
        else:
            result["error"] = f"关闭失败: {title}"
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
        return ok
