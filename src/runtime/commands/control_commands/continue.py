"""继续下次循环"""
from ...workflow.handlers.registry import register_handler
from ...workflow.extension_runner import LoopContinue

@register_handler(cmd="continue", label="继续下次循环", category="循环", runtime="control",
    icon="fa-forward", icon_color="text-orange-500",
    category_order=50, command_order=51,
    description="跳过当前循环剩余指令，进入下一次迭代")
class ContinueHandler:
    params = []

    @staticmethod
    async def execute(runner, cmd_type, instr, extra):
        raise LoopContinue()
