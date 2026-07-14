"""Command: 等待 — wait (backend)

等待固定时间或随机时间。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value
import asyncio
import random


@register_handler(
    cmd="waitWin32", label="等待 (Win32)",
    category="桌面操作", runtime="backend",
    icon="fa-clock", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="等待固定时间或随机时间（秒）",
    category_order=60, command_order=40,
    summary_tpl="{seconds}s",
)
class WaitHandler:
    params = [
        Param("mode", "等待模式", "select", default="fixed",
              options=[
                  {"label": "固定时间", "value": "fixed"},
                  {"label": "随机时间", "value": "random"},
              ]),
        Param("seconds", "等待时间(秒)", "number", default="1",
              placeholder="固定模式下的等待秒数，支持小数如 0.5"),
        Param("minSeconds", "最少(秒)", "number", default="1",
              placeholder="随机模式下的最少秒数",
              group="advanced"),
        Param("maxSeconds", "最多(秒)", "number", default="5",
              placeholder="随机模式下的最多秒数",
              group="advanced"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra", {})
        mode = extra.get("mode", "fixed")
        seconds = float(extra.get("seconds", 1) or 1)
        min_s = float(extra.get("minSeconds", 1) or 1)
        max_s = float(extra.get("maxSeconds", 5) or 5)

        if mode == "random":
            delay = random.uniform(min_s, max_s)
        else:
            delay = seconds

        delay = max(0.01, delay)
        await asyncio.sleep(delay)

        result = {
            "waited": round(delay, 2),
            "mode": mode,
            "log": f"等待 {round(delay, 2)} 秒",
        }
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
