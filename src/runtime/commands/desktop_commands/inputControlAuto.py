"""Command: 输入文字（自动选择）— inputControlAuto

向目标控件输入文本，自动识别引用类型选择实现通道：
  - int HWND / win32 统一引用 → Win32（WM_SETTEXT，失败降级 WM_CHAR）
  - UIA 元素 / uia 统一引用  → UIA（ValuePattern set_text）
兼容旧指令产物变量（findWindowWin32 的 hwnd、findWindowUia 的 UIA 对象）。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref
import asyncio


@register_handler(
    cmd="inputControlAuto", label="输入文字",
    category="桌面操作", runtime="backend",
    icon="fa-keyboard", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="向目标控件输入文本，自动识别引用类型选择 UIA/Win32 实现，兼容新旧捕获方式的变量",
    category_order=50, command_order=15,
    summary_tpl="{text}",
)
class InputControlAutoHandler:
    params = [
        Param("targetControl", "目标控件", "str-var", required=True,
              placeholder="统一控件引用/HWND/UIA 变量，如 {{edit}}"),
        Param("text", "输入内容", "string", required=True,
              placeholder="要输入的文本，支持 {{变量}} 引用"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._desktop_ref import resolve_target
        from ._win32 import (
            set_control_text, get_control_text, get_class_name,
            activate_window, is_windows, window_exists, focus_control, send_char,
        )
        from ._uia import is_uia_available, set_text, get_text, get_control_type

        extra = instr.get("extra", {})
        target_var = clean_var_ref(extra.get("targetControl", ""))
        text = convert_value(extra.get("text", ""), "string", runner.vars)

        if not is_windows():
            result = {"error": "当前系统非 Windows，不支持桌面操作"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        value = runner.vars.get(target_var)
        channel, target = resolve_target(value)
        if channel is None:
            result = {"error": f"无法识别目标控件类型: {target_var} = {type(value).__name__}"
                               f"（支持 HWND 整数、UIA 对象或统一控件引用）"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        if channel == "win32":
            hwnd = target
            if not hwnd or not window_exists(hwnd):
                result = {"error": f"目标控件句柄无效: {target_var} = {hwnd}"}
                runner.completed += 1
                runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                        "status": "error", "result": result})
                await runner._emit({"type": "stepError", "stepId": step_id,
                                    "nodeId": instr.get("nodeId"), "error": result["error"]})
                return False
            activate_window(hwnd)
            ctrl_class = get_class_name(hwnd)
            method = "WM_SETTEXT"
            set_control_text(hwnd, text)
            await asyncio.sleep(0.05)
            ok = (get_control_text(hwnd) == text)
            if not ok:
                method = "WM_CHAR"
                focus_control(hwnd)
                await asyncio.sleep(0.05)
                for ch in text:
                    send_char(hwnd, ch)
                    await asyncio.sleep(0.03)
                ok = True  # WM_CHAR 已完成，不校验（模态对话框可能拿不到返回值）
            result = {"found": True, "via": "win32", "method": method, "input_ok": ok,
                      "hwnd": hwnd, "class_name": ctrl_class, "log": f"输入: {text}"}
        else:  # uia
            elem = target
            if not elem:
                result = {"error": f"UIA 控件变量无效: {target_var} = {value}"}
                runner.completed += 1
                runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                        "status": "error", "result": result})
                await runner._emit({"type": "stepError", "stepId": step_id,
                                    "nodeId": instr.get("nodeId"), "error": result["error"]})
                return False
            if not is_uia_available():
                result = {"error": "UIAutomation 不可用"}
                runner.completed += 1
                runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                        "status": "error", "result": result})
                await runner._emit({"type": "stepError", "stepId": step_id,
                                    "nodeId": instr.get("nodeId"), "error": result["error"]})
                return False
            ok = set_text(elem, text)
            result = {"found": True, "via": "uia", "input_ok": ok,
                      "name": get_text(elem), "control_type": get_control_type(elem),
                      "log": f"输入: {text}"}
            if not ok:
                result["error"] = f"输入失败: {text}"
                runner.completed += 1
                runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                        "status": "error", "result": result})
                await runner._emit({"type": "stepError", "stepId": step_id,
                                    "nodeId": instr.get("nodeId"), "error": result["error"]})
                return False

        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
