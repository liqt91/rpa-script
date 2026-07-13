"""条件循环 — 循环指令"""
from ...workflow.handlers.registry import register_handler, Param
from ...workflow.extension_runner import LoopBreak, LoopContinue, logger

@register_handler(cmd="whileCondition", label="条件循环", category="循环", runtime="control",
    is_container=True, closes_with="endLoop",
    icon="fa-arrows-spin", icon_color="text-purple-500", bg_color="bg-purple-50",
    category_order=50, command_order=40,
    description="当条件满足时重复执行循环体")
class WhileConditionHandler:
    params = [
        Param("conditionType", "条件类型", "str-dropdown", required=True, group="主属性",
              options=[
                  {"label": "元素存在", "value": "elementExists"},
                  {"label": "元素不存在", "value": "elementNotExists"},
                  {"label": "URL 包含", "value": "urlContains"},
                  {"label": "变量等于", "value": "varEquals"},
                  {"label": "变量包含", "value": "varContains"},
                  {"label": "表达式", "value": "expression"},
              ]),
        Param("elementName", "元素", "str-element", group="condition"),
        Param("urlPattern", "URL 包含", "string", default="", group="condition"),
        Param("varName", "变量名", "string", default="", group="condition"),
        Param("varValue", "预期值", "string", default="", group="condition"),
        Param("condition", "表达式", "string", default="False", group="condition",
              placeholder="如: ${a} > 10"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, instr, extra):
        max_iter = int(extra.get("maxIterations", 100))
        body = instr.get("body", [])
        execute_first = extra.get("executeFirst", False)
        first_iter = True
        for _iter in range(max_iter):
            if runner._stopped:
                break
            if not (execute_first and first_iter):
                condition_met = (await runner._evaluate_condition(instr))["met"]
                logger.info(f"whileCondition iter={_iter} met={condition_met}")
                if not condition_met:
                    break
            first_iter = False
            try:
                if not await runner._run_body(body):
                    return False
            except LoopBreak:
                logger.info("whileCondition break")
                break
            except LoopContinue:
                continue
        runner.completed += 1
        await runner._emit({"type":"stepComplete","stepId":instr.get("stepId"),"nodeId":instr.get("nodeId"),"result":{"whileCondition":"done"}})
        return True
