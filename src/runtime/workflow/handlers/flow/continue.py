"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(type="continue", label="继续下一轮", category="循环", runtime="control",
    icon="fa-forward", icon_color="text-gray-400", bg_color="bg-gray-50", category_order=80, command_order=96)
class ContinueHandler:
    params = []
