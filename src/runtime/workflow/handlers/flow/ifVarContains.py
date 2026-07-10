"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(type="ifVarContains", label="如果变量包含", category="条件判断", runtime="control",
    is_container=True, closes_with="endIf",
    icon="fa-search", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=50)
class IfVarContainsHandler:
    params = [
        Param("varName", "变量名", "str-var", required=True),
        Param("substring", "包含文本", "str-input", required=True),
    ]
