"""Command: 继续下次循环"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="continue", label="继续下次循环",
    category="", runtime="control",
    icon="fa-forward", icon_color="text-orange-500",
    bg_color="bg-gray-50",
    description="跳过当前循环剩余指令，进入下一次迭代",
    category_order=0,
    command_order=51,
)
class ContinueHandler: