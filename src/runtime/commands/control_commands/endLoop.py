"""Command: 结束循环"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="endLoop", label="结束循环",
    category="", runtime="control",
    icon="fa-right-to-bracket", icon_color="text-gray-400",
    bg_color="bg-gray-50",
    is_structural=True,
    description="标记循环体结束（自动由循环指令添加）",
    category_order=0,
    command_order=0,
)
class EndLoopHandler: