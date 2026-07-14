"""Command: 按元素库取控件 (UIA) — pickElementUia

从元素库中已捕获的桌面元素（uia）内选取层级，返回该层级的 UIA 控件。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref
import json


@register_handler(
    cmd="pickElementUia", label="按元素库取控件 (UIA)",
    category="桌面操作(UIA)", runtime="backend",
    icon="fa-sitemap", icon_color="text-green-500",
    bg_color="bg-green-50",
    description="从元素库UIA元素中按层级取控件",
    category_order=65, command_order=15,
    summary_tpl="{elementName} L{levelIndex}",
)
class PickElementUiaHandler:
    params = [
        Param("elementName", "桌面元素", "string", required=True,
              placeholder="元素库中 element_kind=uia 的元素名称",
              group="主属性"),
        Param("levelIndex", "层级序号", "number", default="-1",
              placeholder="0=顶层窗口，-1=最后一层(目标控件)"),
        Param("resultVar", "结果存入变量(UIA)", "str-var", default="",
              placeholder="找到的UIA控件对象存入此变量"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._uia import (
            is_uia_available, pick_from_path, get_text, get_control_type,
        )
        from src.repo import runtime_models as models
        from src.repo.models import SessionLocal

        extra = instr.get("extra", {})
        element_name = convert_value(extra.get("elementName", ""), "string", runner.vars)
        level_index = int(extra.get("levelIndex", -1) or -1)
        result_var = clean_var_ref(extra.get("resultVar", ""))

        if not is_uia_available():
            result = {"error": "UIAutomation 不可用"}
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        wf_id = runner.workflow_id
        if not wf_id:
            result = {"error": "无法获取工作流 ID"}
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        db = SessionLocal()
        try:
            el = db.query(models.WorkflowElement).filter(
                models.WorkflowElement.workflow_id == wf_id,
                models.WorkflowElement.name == element_name,
            ).first()
            if not el:
                result = {"error": f"未找到元素: {element_name}"}
                runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                        "status": "error", "result": result})
                await runner._emit({"type": "stepError", "stepId": step_id,
                                    "nodeId": instr.get("nodeId"), "error": result["error"]})
                return False

            attrs = el.attributes
            if isinstance(attrs, str):
                attrs = json.loads(attrs)
            path = attrs.get("path", []) if isinstance(attrs, dict) else []
        finally:
            db.close()

        if not path:
            result = {"error": f"元素 {element_name} 没有控件层级数据"}
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        target = pick_from_path(path, level_index)
        if not target:
            result = {"error": f"层级 {level_index} 未找到", "level": level_index}
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        if result_var:
            runner.vars[result_var] = target

        result = {
            "found": True, "level": level_index,
            "name": target.get("name", ""),
            "class_name": target.get("class_name", ""),
            "control_type": target.get("control_type", ""),
            "log": f"层级[{level_index}]: {target.get('control_type','')} \"{target.get('name','')}\"",
        }
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
