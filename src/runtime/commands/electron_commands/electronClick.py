"""点击元素 — electronClick"""
from src.runtime.workflow.handlers.registry import register_handler, Param


@register_handler(
    cmd="electronClick", label="点击元素",
    category="Electron 应用", runtime="backend",
    icon="fa-hand-pointer", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="点击 Electron 应用页面中的元素（CSS/XPath/文本选择器，或元素库 electron 元素）",
    category_order=55, command_order=3,
    summary_tpl="{selector}",
)
class ElectronClickHandler:
    params = [
        Param("elementName", "元素库元素（可选）", "string", default="",
              placeholder="已捕获的 electron 元素名称；提供后优先使用其选择器"),
        Param("selector", "选择器（可选）", "string", default="",
              placeholder="CSS 或 xpath: 或 text:；未填元素库元素时必填"),
        Param("titleFragment", "页面标题筛选（可选）", "string", default="",
              placeholder="匹配含此标题片段的页面，留空取第一个窗口"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from src.runtime.workflow.electron_manager import electron_manager
        from ._utils import resolve_selector, page_fragment, emit_error

        extra = instr.get("extra", {})
        selector = await resolve_selector(runner, extra)
        if not selector:
            return emit_error(runner, step_id, instr, "未提供选择器（selector 或元素库元素）")
        result = await electron_manager.click(selector, page_fragment(extra))
        if result.get("error"):
            return emit_error(runner, step_id, instr, result["error"])
        result["log"] = f"已点击: {result.get('text') or selector}"
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
