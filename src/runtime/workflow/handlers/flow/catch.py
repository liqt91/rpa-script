"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(type="catch", label="捕获异常", category="异常处理", runtime="control",
    is_container=True, is_branch=True,
    icon="fa-exclamation-triangle", icon_color="text-red-500", bg_color="bg-red-50", category_order=87, command_order=20)
class CatchHandler:
    params = [
        Param("errorVar", "错误信息保存到", "str-var", default="error", group="output"),
    ]


# ─── 分支 ─────────────────────────────────────────────────────
