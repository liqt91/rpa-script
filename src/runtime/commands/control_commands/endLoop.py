"""结束循环 — 控制流结构标记"""
from src.runtime.workflow.handlers.registry import register_handler


@register_handler(
    cmd="endLoop", label="结束循环", category="循环", runtime="control",
    is_structural=True,
    icon="fa-right-to-bracket", icon_color="text-gray-400",
    bg_color="bg-gray-50",
    description="标记循环体结束（自动由循环指令添加）",
    category_order=40, command_order=80,
)
class EndLoopHandler:
    params = []
