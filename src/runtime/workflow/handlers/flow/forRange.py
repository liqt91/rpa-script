"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(type="forRange", label="循环次数", category="循环", runtime="control",
    is_container=True, closes_with="endFor",
    icon="fa-redo", icon_color="text-indigo-500", bg_color="bg-indigo-50", category_order=80, command_order=20,
    description="按指定次数循环执行")
class ForRangeHandler:
    params = [
        Param("start", "起始值", "int-number", default=0),
        Param("end", "结束值", "int-number", default=10),
        Param("step", "步长", "int-number", default=1),
        Param("varName", "循环变量", "str-input", default="i", group="output"),
    ]
