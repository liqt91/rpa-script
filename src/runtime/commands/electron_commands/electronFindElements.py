"""遍历元素列表 — electronFindElements"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import clean_var_ref


@register_handler(
    cmd="electronFindElements", label="遍历元素列表",
    category="Electron 应用", runtime="backend",
    icon="fa-list", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="查找 Electron 应用页面中匹配选择器的所有元素（返回 [{index, text}]）",
    category_order=55, command_order=6,
    summary_tpl="{selector}",
)
class ElectronFindElementsHandler:
    params = [
        Param("elementName", "元素库元素（可选）", "string", default=""),
        Param("selector", "选择器（可选）", "string", default=""),
        Param("titleFragment", "页面标题筛选（可选）", "string", default=""),
        Param("resultVar", "列表存入变量", "str-var", default=""),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from src.runtime.workflow.electron_manager import electron_manager
        from ._utils import resolve_selector, page_fragment, emit_error

        extra = instr.get("extra", {})
        selector = await resolve_selector(runner, extra)
        if not selector:
            return emit_error(runner, step_id, instr, "未提供选择器（selector 或元素库元素）")
        items = await electron_manager.find_elements(selector, page_fragment(extra))
        rv = clean_var_ref(extra.get("resultVar", ""))
        if rv:
            runner.vars[rv] = items
        result = {"found": len(items), "items": items[:50],
                  "log": f"找到 {len(items)} 个元素"}
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
