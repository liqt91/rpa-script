"""Command: 查找子控件 — findChild (backend)

在父窗口中按类名/标题查找第 N 个子控件，存入变量。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref


@register_handler(
    cmd="findChildWin32", label="查找子控件 (Win32)",
    category="桌面操作", runtime="backend",
    icon="fa-arrow-down", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="在父窗口中按类名/标题查找第 N 个子控件",
    category_order=60, command_order=14,
    summary_tpl="{classFilter}#{matchIndex}",
)
class FindChildHandler:
    params = [
        Param("parentWindow", "父窗口 (HWND变量)", "str-var", required=True,
              placeholder="引用已知的父窗口句柄变量"),
        Param("classFilter", "控件类名", "select", default="Edit",
              options=[
                  {"label": "Edit (输入框)", "value": "Edit"},
                  {"label": "Button (按钮)", "value": "Button"},
                  {"label": "ComboBox (下拉框)", "value": "ComboBox"},
                  {"label": "ComboBoxEx32", "value": "ComboBoxEx32"},
                  {"label": "Static (标签)", "value": "Static"},
                  {"label": "ListBox (列表框)", "value": "ListBox"},
                  {"label": "ListView (列表视图)", "value": "SysListView32"},
                  {"label": "TreeView (树形视图)", "value": "SysTreeView32"},
                  {"label": "不筛选", "value": ""},
              ]),
        Param("titleFilter", "标题筛选", "string", default="",
              placeholder="模糊匹配控件标题，留空不筛选"),
        Param("matchIndex", "匹配第几个", "int-number", default="1",
              placeholder="从1开始"),
        Param("resultVar", "结果存入变量", "str-var", default="",
              placeholder="找到的控件句柄存入此变量"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import (
            find_child_window, enum_child_windows, get_window_text,
            get_class_name, is_windows, window_exists,
        )

        extra = instr.get("extra", {})
        parent_var = clean_var_ref(extra.get("parentWindow", ""))
        class_filter = extra.get("classFilter", "Edit") or None
        title_filter = convert_value(extra.get("titleFilter", ""), "string", runner.vars)
        match_index = max(0, int(extra.get("matchIndex", 1) or 1)) - 1
        result_var = clean_var_ref(extra.get("resultVar", ""))

        if not is_windows():
            result = {"error": "当前系统非 Windows"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        parent_hwnd = runner.vars.get(parent_var)
        if not parent_hwnd or not window_exists(parent_hwnd):
            result = {"error": f"父窗口句柄无效: {parent_var} = {parent_hwnd}"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        # 先尝试直接 FindWindowEx 精确匹配标题
        if title_filter:
            child_hwnd = find_child_window(parent_hwnd, class_name=class_filter,
                                            title=title_filter, index=0)
        else:
            child_hwnd = None

        # 标题匹配不上则枚举筛选
        if not child_hwnd:
            children = enum_child_windows(parent_hwnd)
            matched = 0
            for child in children:
                if class_filter and child["class_name"] != class_filter:
                    continue
                if title_filter and title_filter.lower() not in child["title"].lower():
                    continue
                if matched == match_index:
                    child_hwnd = child["hwnd"]
                    break
                matched += 1

        if not child_hwnd:
            result = {
                "found": False,
                "error": f"未找到子控件: class={class_filter} title={title_filter} index={match_index+1}",
            }
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        if result_var:
            runner.vars[result_var] = child_hwnd

        result = {
            "found": True,
            "hwnd": child_hwnd,
            "title": get_window_text(child_hwnd),
            "class_name": get_class_name(child_hwnd),
            "log": f"子控件: {get_class_name(child_hwnd)} \"{get_window_text(child_hwnd)}\"",
        }
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
