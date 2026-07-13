"""Command: 点击控件 — clickControl (backend)

在指定窗口中按类名/标题查找控件，发送点击消息。

技术路线（分层降级）：
  1. 标准 Win32 控件 → SendMessage(BM_CLICK)
  2. 非 Button 控件  → WM_LBUTTONDOWN + WM_LBUTTONUP
  3. 图像识别兜底   → (TODO)
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref


@register_handler(
    cmd="clickControl", label="点击控件",
    category="桌面操作", runtime="backend",
    icon="fa-hand-pointer", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="在指定窗口中查找控件并点击（支持 Button/Edit/ComboBox 等标准控件）",
    category_order=60, command_order=20,
)
class ClickControlHandler:
    params = [
        Param("parentWindow", "父窗口 (HWND变量)", "str-var", required=True,
              placeholder="引用 findWindow 存入的窗口句柄变量"),
        Param("controlClass", "控件类名", "select", default="Button",
              options=[
                  {"label": "Button (按钮)", "value": "Button"},
                  {"label": "Edit (输入框)", "value": "Edit"},
                  {"label": "ComboBox (下拉框)", "value": "ComboBox"},
                  {"label": "Static (标签/文本)", "value": "Static"},
                  {"label": "ListBox (列表框)", "value": "ListBox"},
                  {"label": "自定义类名", "value": "__custom__"},
              ]),
        Param("controlClassCustom", "自定义控件类名", "string", default="",
              placeholder="选择「自定义类名」时填写此项"),
        Param("controlTitle", "控件标题/文本", "string", default="",
              placeholder="如按钮上的文字：确定、取消、买入"),
        Param("matchIndex", "匹配第几个", "int-number", default=1,
              placeholder="从1开始，第1个匹配的控件"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import (
            find_child_window, click_control, get_window_text,
            get_class_name, activate_window, is_windows, window_exists,
        )

        extra = instr.get("extra", {})
        parent_var = clean_var_ref(extra.get("parentWindow", ""))
        control_class = extra.get("controlClass", "Button")
        control_title = convert_value(extra.get("controlTitle", ""), "string", runner.vars)
        match_index = int(extra.get("matchIndex", 1)) - 1  # 转为 0-based

        if control_class == "__custom__":
            control_class = extra.get("controlClassCustom", "")

        if not is_windows():
            result = {"error": "当前系统非 Windows，不支持桌面控件操作"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        # 解析父窗口句柄
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

        # 激活父窗口（确保消息能被正确处理）
        activate_window(parent_hwnd)

        # 查找子控件
        control_hwnd = find_child_window(
            parent_hwnd,
            class_name=control_class or None,
            title=control_title or None,
            index=match_index,
        )

        if not control_hwnd:
            result = {
                "found": False,
                "parent_window": parent_hwnd,
                "search_class": control_class,
                "search_title": control_title,
                "search_index": match_index + 1,
            }
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "success", "result": result})
            await runner._emit({"type": "stepComplete", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "result": result})
            return True

        # 点击
        control_info = {
            "hwnd": control_hwnd,
            "title": get_window_text(control_hwnd),
            "class_name": get_class_name(control_hwnd),
        }
        ok = click_control(control_hwnd)

        result = {
            "found": True,
            "clicked": ok,
            "control": control_info,
        }
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
