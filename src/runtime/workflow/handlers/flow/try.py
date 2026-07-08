"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(type="try", label="尝试执行", category="异常处理", runtime="emitter",
    is_container=True, closes_with="endTry",
    icon="fa-shield-alt", icon_color="text-red-500", bg_color="bg-red-50", category_order=87, command_order=10,
    description="尝试执行内部指令，出错时跳到 catch 分支")
class TryHandler:
    params = []
