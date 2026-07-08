"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(type="whileCondition", label="条件循环", category="循环", runtime="emitter",
    is_container=True, closes_with="endFor",
    icon="fa-infinity", icon_color="text-indigo-500", bg_color="bg-indigo-50", category_order=80, command_order=50,
    description="当条件满足时持续循环")
class WhileConditionHandler:
    params = [
        Param("condition", "条件表达式", "any-expr", required=True, placeholder="如 ${i} < 10"),
    ]


# ─── 条件判断 ────────────────────────────────────────────────
