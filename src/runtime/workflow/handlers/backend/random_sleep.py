"""随机等待 — randomSleep"""
from ..registry import register_handler, Param
import asyncio, random


@register_handler(type="randomSleep", label="随机等待", category="等待", runtime="backend",
    icon="fa-random", icon_color="text-yellow-500", bg_color="bg-yellow-50", category_order=20, command_order=20)
class RandomSleepHandler:
    params = [
        Param("minSeconds", "最小秒数", "number", default=1),
        Param("maxSeconds", "最大秒数", "number", default=5),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        dur = random.uniform(float(extra.get("minSeconds", 1)), float(extra.get("maxSeconds", 5)))
        await asyncio.sleep(dur)
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "success", "result": {"randomSleep": dur}})
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"), "result": {"randomSleep": dur}})
        return True
