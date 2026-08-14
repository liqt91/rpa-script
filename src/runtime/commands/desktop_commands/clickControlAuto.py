"""Command: 点击控件（自动选择）— clickControlAuto

点击目标控件，自动识别引用类型选择实现通道：
  - int HWND / win32 统一引用 → Win32（SendMessage BM_CLICK / WM_LBUTTON）
  - UIA 元素 / uia 统一引用  → UIA（InvokePattern）
兼容旧指令产物变量（findWindowWin32 的 hwnd、findWindowUia 的 UIA 对象）。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import clean_var_ref


@register_handler(
    cmd="clickControlAuto", label="点击控件",
    category="桌面操作", runtime="backend",
    icon="fa-hand-pointer", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="点击目标控件，自动识别引用类型选择 UIA/Win32 实现，兼容新旧捕获方式的变量",
    category_order=50, command_order=12,
    summary_tpl="{targetControl}",
)
class ClickControlAutoHandler:
    params = [
        Param("targetControl", "目标控件", "str-var", required=True,
              placeholder="统一控件引用/HWND/UIA 变量，如 {{win}}、{{edit}}"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._desktop_ref import resolve_target
        from ._win32 import (
            click_control, get_window_text, get_class_name,
            activate_window, is_windows, window_exists,
        )
        from ._uia import is_uia_available, click_element, get_text, get_control_type

        extra = instr.get("extra", {})
        target_var = clean_var_ref(extra.get("targetControl", ""))

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
            ok = click_control(hwnd)
            result = {"found": True, "via": "win32", "clicked": ok, "hwnd": hwnd,
                      "title": get_window_text(hwnd), "class_name": get_class_name(hwnd),
                      "log": f"{get_class_name(hwnd)} \"{get_window_text(hwnd)}\""}
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
            ok = click_element(elem)
            result = {"found": True, "via": "uia", "clicked": ok,
                      "name": get_text(elem), "control_type": get_control_type(elem),
                      "log": f"{get_control_type(elem)} \"{get_text(elem)}\""}

        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
