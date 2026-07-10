"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(type="ifTextEquals", label="如果文本相等", category="条件判断", runtime="control",
    is_container=True, closes_with="endIf",
    icon="fa-equals", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=30)
class IfTextEqualsHandler:
    params = [
        Param("text", "文本A", "str-input", required=True),
        Param("compareTo", "文本B", "str-input", required=True),
    ]
