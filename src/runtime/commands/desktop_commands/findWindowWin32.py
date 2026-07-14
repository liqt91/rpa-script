"""Command: 查找窗口 — findWindow (backend)

按窗口标题或类名查找桌面窗口，可选自动激活前置。
支持精确匹配与模糊匹配两种模式。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref


@register_handler(
    cmd="findWindowWin32", label="查找窗口 (Win32)",
    category="桌面操作", runtime="backend",
    icon="fa-window-maximize", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="按标题或类名查找 Windows 桌面窗口，可选自动激活前置",
    category_order=60, command_order=10,
    summary_tpl="{windowTitle} ({searchMode})",
)
class FindWindowHandler:
    params = [
        Param("searchMode", "查找方式", "select", default="fuzzy",
              options=[
                  {"label": "模糊匹配（标题包含）", "value": "fuzzy"},
                  {"label": "精确匹配（标题等于）", "value": "exact"},
                  {"label": "类名匹配", "value": "classname"},
              ]),
        Param("windowTitle", "窗口标题/类名", "string", required=True,
              placeholder="如：记事本、交易客户端"),
        Param("autoActivate", "查找后激活窗口", "boolean", default=True),
        Param("resultVar", "结果存入变量(HWND)", "str-var", default="",
              placeholder="将窗口句柄存入变量，供后续操作使用"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import (
            find_window, find_window_by_title_fuzzy, activate_window,
            get_window_text, get_class_name, get_window_rect, is_windows,
        )

        extra = instr.get("extra", {})
        search_mode = extra.get("searchMode", "fuzzy")
        window_title = convert_value(extra.get("windowTitle", ""), "string", runner.vars)
        auto_activate = convert_value(extra.get("autoActivate", True), "boolean", runner.vars)
        result_var = clean_var_ref(extra.get("resultVar", ""))

        if not is_windows():
            result = {"error": "当前系统非 Windows，不支持桌面窗口操作"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        hwnd = None
        window_info = {}

        if search_mode == "exact":
            hwnd = find_window(title=window_title)
            if hwnd:
                window_info = {
                    "hwnd": hwnd,
                    "title": get_window_text(hwnd),
                    "class_name": get_class_name(hwnd),
                    "rect": get_window_rect(hwnd),
                }
        elif search_mode == "classname":
            hwnd = find_window(class_name=window_title)
            if hwnd:
                window_info = {
                    "hwnd": hwnd,
                    "title": get_window_text(hwnd),
                    "class_name": get_class_name(hwnd),
                    "rect": get_window_rect(hwnd),
                }
        else:  # fuzzy
            matches = find_window_by_title_fuzzy(window_title)
            if matches:
                hwnd = matches[0]["hwnd"]
                window_info = {
                    "hwnd": hwnd,
                    "title": matches[0]["title"],
                    "class_name": matches[0]["class_name"],
                    "rect": get_window_rect(hwnd),
                    "total_matches": len(matches),
                }

        if not hwnd:
            result = {"found": False, "search": window_title, "mode": search_mode,
                      "log": f"未找到窗口: {window_title}"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "success", "result": result})
            await runner._emit({"type": "stepComplete", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "result": result})
            return True

        if auto_activate:
            activate_window(hwnd)
            window_info["activated"] = True

        # 存入变量
        if result_var:
            runner.vars[result_var] = hwnd

        result = {"found": True, "window": window_info,
                  "log": f"找到窗口: {window_info.get('title', window_title)}"}
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
