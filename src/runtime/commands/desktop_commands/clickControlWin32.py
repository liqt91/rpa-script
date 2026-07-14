"""Command: 点击控件 — clickControl (backend)

点击指定 HWND 的控件。

技术路线（分层降级）：
  1. 标准 Win32 控件 → SendMessage(BM_CLICK)
  2. 非 Button 控件  → WM_LBUTTONDOWN + WM_LBUTTONUP
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref


@register_handler(
    cmd="clickControlWin32", label="点击控件 (Win32)",
    category="桌面操作", runtime="backend",
    icon="fa-hand-pointer", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="点击指定控件句柄",
    category_order=60, command_order=20,
    summary_tpl="{targetHwnd}",
)
class ClickControlHandler:
    params = [
        Param("targetHwnd", "目标控件句柄 (HWND变量)", "str-var", required=True,
              placeholder="控件句柄变量，如 {{btnHWND}}"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import (
            click_control, get_window_text, get_class_name,
            activate_window, is_windows, window_exists,
        )

        extra = instr.get("extra", {})
        target_var = clean_var_ref(extra.get("targetHwnd", ""))

        if not is_windows():
            result = {"error": "当前系统非 Windows"}
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        hwnd = runner.vars.get(target_var)
        if not hwnd or not window_exists(hwnd):
            result = {"error": f"目标控件句柄无效: {target_var} = {hwnd}"}
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        activate_window(hwnd)
        ok = click_control(hwnd)
        result = {
            "found": True, "clicked": ok, "hwnd": hwnd,
            "title": get_window_text(hwnd), "class_name": get_class_name(hwnd),
            "log": f"{get_class_name(hwnd)} \"{get_window_text(hwnd)}\"",
        }
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
