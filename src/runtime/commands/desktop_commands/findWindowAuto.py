"""Command: 查找窗口（自动选择）— findWindowAuto

按标题/类名查找桌面窗口，自动选择实现通道：
  - UIA 优先（信息更全：名称/类名/控件类型/自动化ID）；
  - UIA 不可用或未找到时自动回退 Win32；
  - 也可手动指定只用 UIA 或只用 Win32。
结果以统一控件引用存入 resultVar，可直接交给「点击控件/输入文字」自动指令消费。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref


@register_handler(
    cmd="findWindowAuto", label="查找窗口",
    category="桌面操作", runtime="backend",
    icon="fa-window-maximize", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="按标题查找桌面窗口，自动选择实现（优先 UIA，失败回退 Win32），结果可直接用于点击/输入",
    category_order=50, command_order=3,
    summary_tpl="{windowTitle} ({method})",
)
class FindWindowAutoHandler:
    params = [
        Param("windowTitle", "窗口标题", "string", required=True,
              placeholder="如：记事本，支持模糊匹配"),
        Param("searchMode", "搜索模式", "select", default="fuzzy",
              options=[
                  {"label": "模糊匹配 (子串)", "value": "fuzzy"},
                  {"label": "精确匹配", "value": "exact"},
              ]),
        Param("method", "实现方式", "select", default="auto",
              options=[
                  {"label": "自动（UIA 优先）", "value": "auto"},
                  {"label": "仅 UIA", "value": "uia"},
                  {"label": "仅 Win32", "value": "win32"},
              ]),
        Param("autoActivate", "查找后激活窗口", "boolean", default=True),
        Param("resultVar", "结果存入变量", "str-var", default="",
              placeholder="统一控件引用存入此变量，供后续指令使用"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._desktop_ref import make_win32_ref, make_uia_ref
        from ._uia import is_uia_available, find_window_by_title, find_window_by_title_fuzzy as uia_fuzzy
        from ._win32 import (
            find_window, find_window_by_title_fuzzy, activate_window,
            get_window_text, get_class_name, get_window_rect, is_windows,
        )

        extra = instr.get("extra", {})
        window_title = convert_value(extra.get("windowTitle", ""), "string", runner.vars)
        search_mode = extra.get("searchMode", "fuzzy")
        method = extra.get("method", "auto")
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

        if not window_title:
            result = {"error": "窗口标题为空"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        # 尝试顺序：auto → [uia, win32]，否则只试指定通道
        channels = {"auto": ["uia", "win32"], "uia": ["uia"], "win32": ["win32"]}.get(method, ["uia", "win32"])

        ref = None
        via = None
        for ch in channels:
            if ch == "uia":
                if not is_uia_available():
                    continue
                win = None
                try:
                    if search_mode == "exact":
                        win = find_window_by_title(window_title)
                    elif search_mode == "classname":
                        from ._uia import find_window_by_class
                        win = find_window_by_class(window_title)
                    else:
                        res = uia_fuzzy(window_title)
                        win = res[0] if res else None
                except Exception:
                    win = None
                if win:
                    ref = make_uia_ref(win)
                    via = "uia"
                    break
            else:  # win32
                if search_mode == "classname":
                    hwnd = find_window(class_name=window_title)
                else:
                    hwnd = find_window(title=window_title)
                    if not hwnd and search_mode != "exact":
                        matches = find_window_by_title_fuzzy(window_title)
                        if matches:
                            hwnd = matches[0]["hwnd"]
                if hwnd:
                    ref = make_win32_ref(hwnd,
                                         title=get_window_text(hwnd),
                                         class_name=get_class_name(hwnd),
                                         rect=get_window_rect(hwnd))
                    via = "win32"
                    if auto_activate:
                        activate_window(hwnd)
                    break

        if not ref:
            result = {"found": False, "search": window_title, "method": method,
                      "log": f"未找到窗口: {window_title}"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "success", "result": result})
            await runner._emit({"type": "stepComplete", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "result": result})
            return True

        if result_var:
            runner.vars[result_var] = ref

        result = {"found": True, "via": via,
                  "name": ref.get("name") or ref.get("title", ""),
                  "class_name": ref.get("class_name", ""),
                  "control_type": ref.get("control_type", ""),
                  "log": f"找到窗口({via}): {ref.get('name') or ref.get('title')}"}
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
