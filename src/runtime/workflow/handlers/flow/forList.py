"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(type="forList", label="循环列表", category="循环", runtime="control",
    is_container=True, closes_with="endFor",
    icon="fa-list-ol", icon_color="text-indigo-500", bg_color="bg-indigo-50", category_order=80, command_order=10,
    description="遍历列表变量中的每个元素")
class ForListHandler:
    params = [
        Param("listVar", "列表变量", "str-var", required=True, group="主属性"),
        Param("itemVar", "当前项变量", "str-input", required=True, default="item", group="output"),
        Param("indexVar", "索引变量", "str-input", default="index", group="output"),
    ]
