"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(cmd="ifListContains", label="如果列表包含", category="条件判断", runtime="control",
    is_container=True, closes_with="endIf",
    icon="fa-list", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=60)
class IfListContainsHandler:
    params = [
        Param("listVar", "列表变量", "str-var", required=True),
        Param("value", "查找值", "str-input", required=True),
    ]
