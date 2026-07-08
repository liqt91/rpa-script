"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(type="ifTextContains", label="如果文本包含", category="条件判断", runtime="emitter",
    is_container=True, closes_with="endIf",
    icon="fa-font", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=20)
class IfTextContainsHandler:
    params = [
        Param("text", "源文本", "str-input", required=True, placeholder="支持 ${var} 变量"),
        Param("substring", "包含文本", "str-input", required=True),
    ]
