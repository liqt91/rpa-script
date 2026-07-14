"""Command: 控件输入 (UIA) — inputElementUia

使用 UIA ValuePattern / SendKeys 向控件输入文本。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref


@register_handler(
    cmd="inputElementUia", label="控件输入 (UIA)",
    category="桌面操作(UIA)", runtime="backend",
    icon="fa-keyboard", icon_color="text-green-500",
    bg_color="bg-green-50",
    description="使用 UI Automation 向控件输入文本",
    category_order=65, command_order=30,
    summary_tpl="{text}",
)
class InputElementUiaHandler:
    params = [
        Param("targetElement", "目标控件 (UIA变量)", "str-var", required=True,
              placeholder="控件UIA对象变量，如 {{editElement}}"),
        Param("text", "输入内容", "string", required=True,
              placeholder="要输入的文本，支持 {{变量}} 引用"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._uia import is_uia_available, set_text, get_text, get_control_type

        extra = instr.get("extra", {})
        target_var = clean_var_ref(extra.get("targetElement", ""))
        text = convert_value(extra.get("text", ""), "string", runner.vars)

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

        ok = set_text(elem, text)
        result = {
            "found": True, "input_ok": ok,
            "name": get_text(elem), "control_type": get_control_type(elem),
            "log": f"输入: {text}",
        }
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success" if ok else "error", "result": result})
        if ok:
            await runner._emit({"type": "stepComplete", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "result": result})
            return True
        result["error"] = f"输入失败: {text}"
        await runner._emit({"type": "stepError", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "error": result["error"]})
        return False
