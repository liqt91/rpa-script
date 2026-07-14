"""Command: 输入文本 — inputControl (backend)

向指定 HWND 的控件输入文本。
技术路线：WM_SETTEXT → keybd_event 降级
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref


@register_handler(
    cmd="inputControlWin32", label="控件输入 (Win32)",
    category="桌面操作", runtime="backend",
    icon="fa-keyboard", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="向指定控件句柄输入文本",
    category_order=60, command_order=30,
    summary_tpl="{text}",
)
class InputControlHandler:
    params = [
        Param("targetHwnd", "目标控件句柄 (HWND变量)", "str-var", required=True,
              placeholder="控件句柄变量，如 {{editHWND}}"),
        Param("text", "输入内容", "string", required=True,
              placeholder="要输入的文本，支持 {{变量}} 引用"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import (
            set_control_text, get_control_text, get_class_name,
            activate_window, is_windows, window_exists, focus_control,
        )
        import asyncio

        extra = instr.get("extra", {})
        target_var = clean_var_ref(extra.get("targetHwnd", ""))
        text = convert_value(extra.get("text", ""), "string", runner.vars)

        if not is_windows():
            result = {"error": "当前系统非 Windows"}
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        edit_hwnd = runner.vars.get(target_var)
        if not edit_hwnd or not window_exists(edit_hwnd):
            result = {"error": f"目标控件句柄无效: {target_var} = {edit_hwnd}"}
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        activate_window(edit_hwnd)
        ctrl_class = get_class_name(edit_hwnd)
        old_text = get_control_text(edit_hwnd)

        method = "WM_SETTEXT"
        set_control_text(edit_hwnd, text)
        await asyncio.sleep(0.05)
        new_text = get_control_text(edit_hwnd)
        ok = (new_text == text)

        if not ok:
            method = "WM_CHAR"
            focus_control(edit_hwnd)
            await asyncio.sleep(0.05)
            from ._win32 import send_char
            for ch in text:
                send_char(edit_hwnd, ch)
                await asyncio.sleep(0.03)
            ok = True  # WM_CHAR 已完成，不校验（模态对话框可能拿不到返回值）

        result = {
            "found": True, "method": method,
            "hwnd": edit_hwnd, "class_name": ctrl_class,
            "log": f"输入: {text}",
        }
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
