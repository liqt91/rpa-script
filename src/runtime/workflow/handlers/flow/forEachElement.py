"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(type="forEachElement", label="循环元素列表", category="循环", runtime="control",
    is_container=True, closes_with="endFor",
    icon="fa-crosshairs", icon_color="text-indigo-500", bg_color="bg-indigo-50", category_order=80, command_order=30,
    description="遍历匹配到的所有元素")
class ForEachElementHandler:
    params = [
        Param("element_name", "元素", "str-element", required=True, group="主属性"),
        Param("itemVar", "当前项变量", "str-input", required=True, default="item", group="output"),
        Param("indexVar", "索引变量", "str-input", default="index", group="output"),
        Param("scope", "匹配范围", "str-dropdown",
              options=[{"label": "全局", "value": "global"}], default="global", group="advanced"),
        Param("visibilityMode", "元素可见性", "str-dropdown",
              options=[{"label": "仅可见", "value": "visible"}, {"label": "所有", "value": "any"}],
              default="visible", group="advanced"),
    ]
