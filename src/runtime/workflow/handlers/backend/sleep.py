"""等待 — sleep"""
from ..registry import register_handler, Param
import asyncio


@register_handler(cmd="sleep", label="等待", category="等待", runtime="backend",
    icon="fa-clock", icon_color="text-yellow-500", bg_color="bg-yellow-50", category_order=20, command_order=10)
class SleepHandler:
    params = [
        Param("seconds", "等待秒数", "int-number", default=3),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        secs = float(instr.get("extra", {}).get("seconds", 1))
        await asyncio.sleep(secs)
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "success", "result": {"sleep": secs}})
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"), "result": {"sleep": secs}})
        return True
