"""取元素文本 — electronGetText"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import clean_var_ref


@register_handler(
    cmd="electronGetText", label="取元素文本",
    category="Electron 应用", runtime="backend",
    icon="fa-font", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="读取 Electron 应用页面元素的内文文本",
    category_order=55, command_order=5,
    summary_tpl="{selector}",
)
class ElectronGetTextHandler:
    params = [
        Param("elementName", "元素库元素（可选）", "string", default=""),
        Param("selector", "选择器（可选）", "string", default=""),
        Param("titleFragment", "页面标题筛选（可选）", "string", default=""),
        Param("resultVar", "文本存入变量", "str-var", default=""),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from src.runtime.workflow.electron_manager import electron_manager
        from ._utils import resolve_selector, page_fragment, emit_error

        extra = instr.get("extra", {})
        selector = await resolve_selector(runner, extra)
        if not selector:
            return emit_error(runner, step_id, instr, "未提供选择器（selector 或元素库元素）")
        result = await electron_manager.get_text(selector, page_fragment(extra))
        if result.get("error"):
            return emit_error(runner, step_id, instr, result["error"])
        if clean_var_ref(extra.get("resultVar", "")):
            runner.vars[clean_var_ref(extra.get("resultVar", ""))] = result.get("text", "")
        result["log"] = f"文本: {(result.get('text') or '')[:40]}"
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
