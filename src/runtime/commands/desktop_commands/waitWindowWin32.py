"""Command: 等待窗口出现 — waitWindow (backend)

启动软件后轮询等待指定窗口出现，找到返回窗口句柄（存入 resultVar），
超时返回 found=False（软结果，不中断流程，可按业务自行判断）。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref
import asyncio


@register_handler(
    cmd="waitWindowWin32", label="等待窗口出现",
    category="桌面操作", runtime="backend",
    icon="fa-hourglass-half", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="轮询等待指定窗口出现（常用于启动软件后等待窗口就绪），找到返回窗口句柄",
    category_order=50, command_order=2,
    summary_tpl="{windowTitle} ({timeout}s)",
)
class WaitWindowHandler:
    params = [
        Param("windowTitle", "窗口标题", "string", required=True,
              placeholder="标题包含此内容的窗口，如：记事本"),
        Param("classFilter", "窗口类名（可选）", "string", default="",
              placeholder="如 Notepad；留空则只按标题匹配"),
        Param("timeout", "超时(秒)", "number", default="10"),
        Param("resultVar", "结果存入变量(HWND)", "str-var", default="",
              placeholder="窗口句柄存入此变量，供后续操作使用"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import (
            find_window, find_window_by_title_fuzzy,
            get_window_text, get_class_name, is_windows,
        )

        extra = instr.get("extra", {})
        window_title = convert_value(extra.get("windowTitle", ""), "string", runner.vars)
        class_filter = convert_value(extra.get("classFilter", ""), "string", runner.vars)
        try:
            timeout = float(extra.get("timeout", 10) or 10)
        except (ValueError, TypeError):
            timeout = 10.0
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

        import time
        deadline = time.monotonic() + max(timeout, 0)
        found_hwnd = None
        while time.monotonic() < deadline:
            if class_filter:
                # 类名 + 标题同时匹配：先精确、再模糊候选里筛类名
                h = find_window(title=window_title)
                if h and get_class_name(h) == class_filter:
                    found_hwnd = h
                if not found_hwnd:
                    for m in find_window_by_title_fuzzy(window_title):
                        if get_class_name(m["hwnd"]) == class_filter:
                            found_hwnd = m["hwnd"]
                            break
            else:
                found_hwnd = find_window(title=window_title)
                if not found_hwnd:
                    matches = find_window_by_title_fuzzy(window_title)
                    if matches:
                        found_hwnd = matches[0]["hwnd"]
            if found_hwnd:
                break
            await asyncio.sleep(0.5)

        if result_var and found_hwnd:
            runner.vars[result_var] = found_hwnd

        if found_hwnd:
            result = {"found": True, "hwnd": found_hwnd,
                      "title": get_window_text(found_hwnd),
                      "class_name": get_class_name(found_hwnd),
                      "log": f"窗口已出现: {get_window_text(found_hwnd)}"}
        else:
            result = {"found": False, "search": window_title, "timeout": timeout,
                      "log": f"等待 {timeout}s 窗口未出现: {window_title}"}
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
