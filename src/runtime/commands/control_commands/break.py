"""Command: 跳出循环"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="break", label="跳出循环",
    category="", runtime="control",
    icon="fa-right-from-bracket", icon_color="text-red-500",
    bg_color="bg-gray-50",
    description="跳出当前循环，继续执行循环后的指令",
    category_order=0,
    command_order=50,
)
class BreakHandler: