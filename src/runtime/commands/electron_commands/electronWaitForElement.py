"""等待元素出现 — electronWaitForElement"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import clean_var_ref


@register_handler(
    cmd="electronWaitForElement", label="等待元素出现",
    category="Electron 应用", runtime="backend",
    icon="fa-hourglass-half", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="轮询等待 Electron 应用页面中元素出现（超时返回 found=False 软结果）",
    category_order=55, command_order=2,
    summary_tpl="{selector} ({timeout}s)",
)
class ElectronWaitForElementHandler:
    params = [
        Param("elementName", "元素库元素（可选）", "string", default=""),
        Param("selector", "选择器（可选）", "string", default=""),
        Param("timeout", "超时(秒)", "number", default="10"),
        Param("titleFragment", "页面标题筛选（可选）", "string", default=""),
        Param("resultVar", "结果存入变量", "str-var", default=""),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from src.runtime.workflow.electron_manager import electron_manager
        from ._utils import resolve_selector, page_fragment, emit_error

        extra = instr.get("extra", {})
        selector = await resolve_selector(runner, extra)
        if not selector:
            return emit_error(runner, step_id, instr, "未提供选择器（selector 或元素库元素）")
        try:
            timeout = int(float(extra.get("timeout", 10) or 10) * 1000)
        except (ValueError, TypeError):
            timeout = 10000
        result = await electron_manager.wait_for(selector, timeout, page_fragment(extra))
        if result.get("error"):
            return emit_error(runner, step_id, instr, result["error"])
        if clean_var_ref(extra.get("resultVar", "")):
            runner.vars[clean_var_ref(extra.get("resultVar", ""))] = result.get("found", False)
        result["log"] = f"元素{'已出现' if result.get('found') else '未出现'}: {selector}"
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
