"""Command: 查找窗口 (UIA) — findWindowUia

使用 UIAutomation 按标题/类名查找窗口。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref


@register_handler(
    cmd="findWindowUia", label="查找窗口 (UIA)",
    category="桌面操作(UIA)", runtime="backend",
    icon="fa-window-maximize", icon_color="text-green-500",
    bg_color="bg-green-50",
    description="使用 UI Automation 查找桌面窗口",
    category_order=65, command_order=5,
    summary_tpl="{windowTitle} (UIA)",
)
class FindWindowUiaHandler:
    params = [
        Param("windowTitle", "窗口标题", "string", required=True,
              placeholder="如：无标题 - 记事本，支持模糊匹配"),
        Param("searchMode", "搜索模式", "select", default="fuzzy",
              options=[
                  {"label": "模糊匹配 (子串)", "value": "fuzzy"},
                  {"label": "精确匹配", "value": "exact"},
              ]),
        Param("resultVar", "结果存入变量(UIA)", "str-var", default="",
              placeholder="找到的窗口UIA对象存入此变量"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._uia import (
            is_uia_available, find_window_by_title,
            find_window_by_title_fuzzy,
        )

        extra = instr.get("extra", {})
        window_title = convert_value(extra.get("windowTitle", ""), "string", runner.vars)
        search_mode = extra.get("searchMode", "fuzzy")
        result_var = clean_var_ref(extra.get("resultVar", ""))

        if not is_uia_available():
            result = {"error": "UIAutomation 不可用，请 pip install uiautomation"}
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        if search_mode == "exact":
            win = find_window_by_title(window_title)
        else:
            results = find_window_by_title_fuzzy(window_title)
            win = results[0] if results else None

        if not win:
            result = {"found": False, "search": window_title,
                       "error": f"未找到窗口: {window_title}"}
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        if result_var:
            runner.vars[result_var] = win  # 存 dict（含 _uia_ctrl 不可序列化，仅运行时）

        result = {
            "found": True,
            "name": win.get("name", ""),
            "class_name": win.get("class_name", ""),
            "control_type": win.get("control_type", ""),
            "automation_id": win.get("automation_id", ""),
            "log": f"找到窗口: {win.get('name')}",
        }
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
