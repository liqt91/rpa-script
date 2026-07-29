"""结束条件 — 控制流结构标记"""
from src.runtime.workflow.handlers.registry import register_handler


@register_handler(
    cmd="endIf", label="结束条件", category="流程控制", runtime="control",
    is_structural=True,
    icon="fa-right-to-bracket", icon_color="text-gray-400",
    bg_color="bg-gray-50",
    description="标记条件分支结束（自动由条件指令添加）",
    category_order=40, command_order=90,
)
class EndIfHandler:
    params = []
