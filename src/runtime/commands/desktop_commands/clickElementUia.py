"""Command: 点击控件 (UIA) — clickElementUia

使用 UIA InvokePattern 点击控件。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref


@register_handler(
    cmd="clickElementUia", label="点击控件 (UIA)",
    category="桌面操作(UIA)", runtime="backend",
    icon="fa-hand-pointer", icon_color="text-green-500",
    bg_color="bg-green-50",
    description="使用 UI Automation 点击控件",
    category_order=65, command_order=20,
    summary_tpl="{targetElement}",
)
class ClickElementUiaHandler:
    params = [
        Param("targetElement", "目标控件 (UIA变量)", "str-var", required=True,
              placeholder="控件UIA对象变量，如 {{btnElement}}"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._uia import is_uia_available, click_element, get_text, get_control_type

        extra = instr.get("extra", {})
        target_var = clean_var_ref(extra.get("targetElement", ""))

        if not is_uia_available():
            result = {"error": "UIAutomation 不可用"}
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        elem = runner.vars.get(target_var)
        if not elem:
            result = {"error": f"UIA 控件变量无效: {target_var} = {elem}"}
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        ok = click_element(elem)
        result = {
            "found": True, "clicked": ok,
            "name": get_text(elem), "control_type": get_control_type(elem),
            "log": f"{get_control_type(elem)} \"{get_text(elem)}\"",
        }
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
