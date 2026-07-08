"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(type="ifElementVisible", label="如果元素可见", category="条件判断", runtime="emitter",
    is_container=True, closes_with="endIf",
    icon="fa-eye", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=10,
    description="根据元素是否可见决定执行分支")
class IfElementVisibleHandler:
    params = [
        Param("element_name", "元素", "str-element", required=True, group="主属性"),
        Param("operator", "判断条件", "str-dropdown",
              options=[{"label": "可见", "value": "visible"}, {"label": "不可见", "value": "notVisible"}],
              default="visible"),
        Param("scope", "匹配范围", "str-dropdown",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]
