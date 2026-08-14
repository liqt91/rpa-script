"""设置变量"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref


@register_handler(
    cmd="setVar", label="设置变量", category="变量操作", runtime="backend",
    icon="fa-equals", icon_color="text-green-500", bg_color="bg-green-50",
    category_order=30, command_order=10,
    summary_tpl="{name} = {value}")
class SetVarHandler:
    params = [
        Param("name", "变量名", "str-var", required=True),
        Param("value", "值", "any-input"),
        Param("valueType", "值类型", "select",
              options=[
                  {"label": "自动", "value": "any-input"},
                  {"label": "文本", "value": "string"},
                  {"label": "数字", "value": "number"},
                  {"label": "布尔", "value": "boolean"},
                  {"label": "代码/表达式", "value": "code",
                   "description": "JSON 数组/对象、=表达式、Python 表达式"},
              ], default="any-input"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra", {})
        name = clean_var_ref(extra.get("name", ""))
        value = extra.get("value", "")
        value_type = extra.get("valueType", "string")
        if name:
            resolved_value = convert_value(value, value_type, runner.vars)
            runner.vars[name] = resolved_value
        else:
            resolved_value = None
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
            "status": "success", "result": {"setVar": name, "value": resolved_value}})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
            "nodeId": instr.get("nodeId"), "result": {"setVar": name, "value": resolved_value}})
        return True
