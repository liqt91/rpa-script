"""遍历列表 — 循环指令"""
from ...workflow.handlers.registry import register_handler, Param
from ...workflow.extension_runner import LoopBreak, LoopContinue, _clean_var_ref, logger

@register_handler(cmd="forList", label="遍历列表", category="循环", runtime="control",
    is_container=True, closes_with="endLoop",
    icon="fa-list-ol", icon_color="text-purple-500", bg_color="bg-purple-50",
    category_order=50, command_order=20,
    description="遍历一个列表变量，对每个值执行循环体",
    summary_tpl="{listVar}")
class ForListHandler:
    params = [
        Param("listVar", "列表变量", "string", required=True, group="主属性"),
        Param("itemVar", "当前项变量", "string", default="item"),
        Param("indexVar", "索引变量", "string", default="index"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, instr, extra):
        raw_extra = instr.get("extra") or {}
        list_var = _clean_var_ref(raw_extra.get("listVar", "items"))
        items = runner.vars.get(list_var, [])
        if not isinstance(items, list):
            items = []
        item_var = _clean_var_ref(raw_extra.get("itemVar", "item"))
        idx_var = _clean_var_ref(raw_extra.get("indexVar", "index"))
        body = instr.get("body", [])
        logger.info(f"forList {list_var} has {len(items)} items")
        for idx, item in enumerate(items):
            if runner._stopped:
                break
            runner.vars[idx_var] = idx
            runner.vars[item_var] = item
            logger.info(f"forList [{idx}] {item_var}={item!r}")
            try:
                if not await runner._run_body(body):
                    return False
            except LoopBreak:
                logger.info("forList break")
                break
            except LoopContinue:
                logger.info("forList continue")
                continue
        runner.completed += 1
        await runner._emit({"type":"stepComplete","stepId":instr.get("stepId"),"nodeId":instr.get("nodeId"),"result":{"forList":len(items)}})
        return True
