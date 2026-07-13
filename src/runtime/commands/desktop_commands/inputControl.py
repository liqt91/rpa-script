"""Command: 输入文本 — inputControl (backend)

在指定窗口的 Edit 控件中输入文本。
通过 WM_SETTEXT 消息直接设置控件文本，无需模拟键盘输入。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref


@register_handler(
    cmd="inputControl", label="控件输入",
    category="桌面操作", runtime="backend",
    icon="fa-keyboard", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="向指定窗口的 Edit 控件输入文本",
    category_order=60, command_order=30,
)
class InputControlHandler:
    params = [
        Param("parentWindow", "父窗口 (HWND变量)", "str-var", required=True,
              placeholder="引用 findWindow 存入的窗口句柄变量"),
        Param("controlTitle", "控件标题/文本", "string", default="",
              placeholder="输入框旁边的标签文字，或输入框当前内容"),
        Param("text", "输入内容", "string", required=True,
              placeholder="要输入的文本，支持 {{变量}} 引用"),
        Param("matchIndex", "匹配第几个 Edit", "int-number", default=1,
              placeholder="从1开始，第1个匹配的 Edit 控件"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import (
            find_child_window, set_control_text, get_control_text,
            get_class_name, activate_window, is_windows, window_exists,
        )

        extra = instr.get("extra", {})
        parent_var = clean_var_ref(extra.get("parentWindow", ""))
        control_title = convert_value(extra.get("controlTitle", ""), "string", runner.vars)
        text = convert_value(extra.get("text", ""), "string", runner.vars)
        match_index = int(extra.get("matchIndex", 1)) - 1

        if not is_windows():
            result = {"error": "当前系统非 Windows，不支持桌面控件操作"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        parent_hwnd = runner.vars.get(parent_var)
        if not parent_hwnd or not window_exists(parent_hwnd):
            result = {"error": f"父窗口句柄无效: {parent_var} = {parent_hwnd}",
                      "hint": "请先使用 findWindow 查找窗口并存入变量"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        activate_window(parent_hwnd)

        # 查找 Edit 控件
        edit_hwnd = find_child_window(
            parent_hwnd,
            class_name="Edit",
            title=control_title or None,
            index=match_index,
        )

        if not edit_hwnd:
            result = {
                "found": False,
                "parent_window": parent_hwnd,
                "search_title": control_title,
                "search_index": match_index + 1,
            }
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "success", "result": result})
            await runner._emit({"type": "stepComplete", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "result": result})
            return True

        # 记录输入前的内容
        old_text = get_control_text(edit_hwnd)

        # 设置文本
        ok = set_control_text(edit_hwnd, text)

        result = {
            "found": True,
            "input_ok": ok,
            "control": {
                "hwnd": edit_hwnd,
                "class_name": get_class_name(edit_hwnd),
                "before": old_text,
                "after": text,
            },
        }
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
