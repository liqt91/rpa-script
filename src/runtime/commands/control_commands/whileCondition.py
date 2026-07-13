"""Command: 条件循环"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="whileCondition", label="条件循环",
    category="", runtime="control",
    icon="fa-arrows-spin", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    is_container=True,
    closes_with="endLoop",
    description="当条件满足时重复执行循环体",
    category_order=50,
    command_order=40,
)
class WhileConditionHandler:
    params = [
        Param("conditionType", "条件类型", "select", required=True, options=[{"label": "元素存在", "value": "elementExists"}, {"label": "元素不存在", "value": "elementNotExists"}, {"label": "URL 包含", "value": "urlContains"}, {"label": "变量等于", "value": "varEquals"}, {"label": "变量包含", "value": "varContains"}, {"label": "表达式", "value": "expression"}], group="主属性"),
        Param("elementName", "元素", "element", group="condition"),
        Param("urlPattern", "URL 包含", "string", default="", group="condition"),
        Param("varName", "变量名", "string", default="", group="condition"),
        Param("varValue", "预期值", "string", default="", group="condition"),
        Param("condition", "表达式", "string", default="False", group="condition", placeholder="如: ${a} > 10"),
    ]