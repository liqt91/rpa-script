"""Command: 循环次数"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="forRange", label="循环次数",
    category="", runtime="control",
    icon="fa-rotate", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    is_container=True,
    closes_with="endLoop",
    description="循环指定次数，从起始值到结束值",
    category_order=50,
    command_order=30,
)
class ForRangeHandler:
    params = [
        Param("start", "起始值", "number", default=0),
        Param("end", "结束值", "number", required=True),
        Param("step", "步长", "number", default=1),
        Param("itemVar", "当前值变量", "string", default="i"),
    ]