"""跳出循环"""
from ...workflow.handlers.registry import register_handler
from ...workflow.extension_runner import LoopBreak

@register_handler(cmd="break", label="跳出循环", category="循环", runtime="control",
    icon="fa-right-from-bracket", icon_color="text-red-500",
    category_order=50, command_order=50,
    description="跳出当前循环，继续执行循环后的指令")
class BreakHandler:
    params = []

    @staticmethod
    async def execute(runner, cmd_type, instr, extra):
        raise LoopBreak()
