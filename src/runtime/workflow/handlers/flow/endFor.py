"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(cmd="endFor", label="结束循环", category="循环", runtime="control",
    is_structural=True,
    icon="fa-level-up-alt", icon_color="text-gray-400", bg_color="bg-gray-50", category_order=80, command_order=99)
class EndForHandler:
    params = []
