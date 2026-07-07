"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(type="forEachTableRow", label="循环表格行", category="循环", runtime="emitter",
    is_container=True, closes_with="endFor",
    icon="fa-table", icon_color="text-indigo-500", bg_color="bg-indigo-50", category_order=80, command_order=40,
    description="遍历数据表格的每一行")
class ForEachTableRowHandler:
    params = [
        Param("itemVar", "当前行变量", "text", required=True, default="row", group="output"),
        Param("indexVar", "索引变量", "text", default="index", group="output"),
    ]
