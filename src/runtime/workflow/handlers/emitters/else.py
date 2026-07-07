"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(type="else", label="否则", category="条件判断", runtime="emitter",
    is_container=True, is_branch=True,
    icon="fa-code-branch", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=15)
class ElseHandler:
    params = []


# ─── 结构标记（闭合标签）────────────────────────────────────
