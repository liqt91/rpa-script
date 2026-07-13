"""遍历元素列表 — 循环指令"""
from ...workflow.handlers.registry import register_handler, Param
from ...workflow.extension_runner import LoopBreak, LoopContinue, _clean_var_ref, logger

@register_handler(cmd="forEachElement", label="遍历元素列表", category="循环", runtime="control",
    is_container=True, closes_with="endLoop",
    icon="fa-list-check", icon_color="text-purple-500", bg_color="bg-purple-50",
    category_order=50, command_order=10,
    description="遍历页面上匹配的元素列表，对每个元素执行循环体")
class ForEachElementHandler:
    params = [
        Param("elementName", "目标元素列表", "element-list", required=True, group="主属性"),
        Param("itemVar", "当前项变量", "string", default="item"),
        Param("indexVar", "索引变量", "string", default="index"),
        Param("scope", "匹配范围", "str-dropdown",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, instr, extra):
        locator = instr.get("locator") or extra.get("locator", "")
        selector_family = instr.get("selectorFamily") or extra.get("selector_family", "css")
        item_var = _clean_var_ref(extra.get("itemVar", "item"))
        idx_var = _clean_var_ref(extra.get("indexVar", "index"))
        timeout = extra.get("timeout", 10)
        body = instr.get("body", [])
        logger.info(f"forEachElement visibilityMode={extra.get('visibilityMode', 'visible')}")
        elements = await runner._find_elements(locator, selector_family, timeout=timeout, extra=extra)
        logger.info(f"forEachElement found {len(elements)} elements")
        runner.vars.setdefault("__loop_ctx", []).append(None)
        try:
            for idx, item in enumerate(elements):
                if runner._stopped:
                    break
                runner.vars[idx_var] = idx
                runner.vars[item_var] = item.get("text", "") if isinstance(item, dict) else str(item)
                base_ctx = {
                    "sourceLocator": locator, "sourceSelectorFamily": selector_family,
                    "sourceIndex": idx, "sourceTotal": len(elements),
                    "loopElementName": instr.get("elementName"),
                }
                if isinstance(item, dict) and item.get("contextLocator"):
                    runner.vars["__loop_ctx"][-1] = {
                        **base_ctx,
                        "locator": item["contextLocator"],
                        "selectorFamily": item.get("contextLocatorType", selector_family),
                        "index": 0, "total": 1,
                    }
                else:
                    runner.vars["__loop_ctx"][-1] = {
                        **base_ctx,
                        "locator": locator, "selectorFamily": selector_family,
                        "index": idx, "total": len(elements),
                    }
                logger.info(f"forEachElement [{idx}] {item_var}={runner.vars[item_var]!r}")
                try:
                    if not await runner._run_body(body):
                        return False
                except LoopBreak:
                    logger.info("forEachElement break")
                    break
                except LoopContinue:
                    logger.info("forEachElement continue")
                    continue
        finally:
            runner.vars["__loop_ctx"].pop()
            if not runner.vars["__loop_ctx"]:
                runner.vars.pop("__loop_ctx", None)
        runner.completed += 1
        await runner._emit({"type":"stepComplete","stepId":instr.get("stepId"),"nodeId":instr.get("nodeId"),"result":{"forEachElement":len(elements)}})
        return True
