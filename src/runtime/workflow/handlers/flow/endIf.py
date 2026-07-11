"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(cmd="endIf", label="结束判断", category="条件判断", runtime="control",
    is_structural=True,
    icon="fa-level-up-alt", icon_color="text-gray-400", bg_color="bg-gray-50", category_order=85, command_order=99)
class EndIfHandler:
    params = []
