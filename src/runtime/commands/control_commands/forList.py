"""Command: 遍历列表"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="forList", label="遍历列表",
    category="", runtime="control",
    icon="fa-list-ol", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    is_container=True,
    closes_with="endLoop",
    description="遍历一个列表变量，对每个值执行循环体",
    category_order=50,
    command_order=20,
)
class ForListHandler:
    params = [
        Param("listName", "列表变量", "string", required=True, group="主属性"),
        Param("itemVar", "当前项变量", "string", default="item"),
        Param("indexVar", "索引变量", "string", default="index"),
    ]