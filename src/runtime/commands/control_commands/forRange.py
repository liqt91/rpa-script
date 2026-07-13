"""循环次数 — 循环指令"""
from ...workflow.handlers.registry import register_handler, Param
from ...workflow.extension_runner import LoopBreak, LoopContinue, _clean_var_ref, logger

@register_handler(cmd="forRange", label="循环次数", category="循环", runtime="control",
    is_container=True, closes_with="endLoop",
    icon="fa-rotate", icon_color="text-purple-500", bg_color="bg-purple-50",
    category_order=50, command_order=30,
    description="循环指定次数，从起始值到结束值")
class ForRangeHandler:
    params = [
        Param("start", "起始值", "number", default="0"),
        Param("end", "结束值", "number", required=True),
        Param("step", "步长", "number", default="1"),
        Param("itemVar", "当前值变量", "string", default="i"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, instr, extra):
        raw_extra = instr.get("extra") or {}
        try: start = int(raw_extra.get("start", 0))
        except (ValueError, TypeError): start = 0
        try: end = int(raw_extra.get("end", 0))
        except (ValueError, TypeError): end = 0
        try: step = int(raw_extra.get("step", 1))
        except (ValueError, TypeError): step = 1
        if step == 0: step = 1
        item_var = _clean_var_ref(raw_extra.get("itemVar", "i"))
        body = instr.get("body", [])
        values = range(start, end + 1, step) if step > 0 else range(start, end - 1, step)
        logger.info(f"forRange {start}..{end} step={step}")
        count = 0
        for val in values:
            if runner._stopped:
                break
            runner.vars[item_var] = val
            count += 1
            try:
                if not await runner._run_body(body):
                    return False
            except LoopBreak:
                logger.info("forRange break")
                break
            except LoopContinue:
                continue
        runner.completed += 1
        await runner._emit({"type":"stepComplete","stepId":instr.get("stepId"),"nodeId":instr.get("nodeId"),"result":{"forRange":count}})
        return True
