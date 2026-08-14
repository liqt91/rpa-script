"""输入文本 — electronInput"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value


@register_handler(
    cmd="electronInput", label="输入文本",
    category="Electron 应用", runtime="backend",
    icon="fa-keyboard", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="向 Electron 应用页面的输入框输入文本（React 兼容：原生 value setter + input 事件）",
    category_order=55, command_order=4,
    summary_tpl="{text}",
)
class ElectronInputHandler:
    params = [
        Param("elementName", "元素库元素（可选）", "string", default=""),
        Param("selector", "选择器（可选）", "string", default="",
              placeholder="CSS 或 xpath:；未填元素库元素时必填"),
        Param("text", "输入内容", "string", required=True,
              placeholder="要输入的文本，支持 {{变量}}"),
        Param("titleFragment", "页面标题筛选（可选）", "string", default=""),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from src.runtime.workflow.electron_manager import electron_manager
        from ._utils import resolve_selector, page_fragment, emit_error

        extra = instr.get("extra", {})
        selector = await resolve_selector(runner, extra)
        if not selector:
            return emit_error(runner, step_id, instr, "未提供选择器（selector 或元素库元素）")
        text = convert_value(extra.get("text", ""), "string", runner.vars)
        result = await electron_manager.input_text(selector, text, page_fragment(extra))
        if result.get("error"):
            return emit_error(runner, step_id, instr, result["error"])
        result["log"] = f"已输入: {text}"
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
