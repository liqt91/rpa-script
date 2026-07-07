"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(type="ifDictContains", label="如果字典包含键", category="条件判断", runtime="emitter",
    is_container=True, closes_with="endIf",
    icon="fa-book", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=70)
class IfDictContainsHandler:
    params = [
        Param("dictVar", "字典变量", "varName", required=True),
        Param("key", "键名", "text", required=True),
    ]


# ─── 异常处理 ────────────────────────────────────────────────
