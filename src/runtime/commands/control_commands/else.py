"""否则分支 — 条件分支结构标记"""
from src.runtime.workflow.handlers.registry import register_handler


@register_handler(
    cmd="else", label="否则", category="条件判断", runtime="control",
    is_container=True, is_branch=True,
    icon="fa-code-branch", icon_color="text-cyan-500",
    bg_color="bg-cyan-50",
    category_order=85, command_order=15,
    description="标记条件分支的否则分支（自动由条件指令添加）",
)
class ElseHandler:
    params = []
