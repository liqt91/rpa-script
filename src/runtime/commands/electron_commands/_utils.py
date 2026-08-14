"""Electron 指令公共工具 — 选择器解析等。"""
import json

from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref


async def resolve_selector(runner, extra: dict) -> str:
    """解析目标选择器：elementName（元素库 electron 元素）优先，其次 selector 参数。"""
    element_name = convert_value(extra.get("elementName", ""), "string", runner.vars)
    selector = convert_value(extra.get("selector", ""), "string", runner.vars)
    if element_name:
        from src.repo import models
        db = models.SessionLocal()
        try:
            el = (db.query(models.WorkflowElement)
                  .filter_by(workflow_id=runner.workflow_id, name=element_name).first())
            if el:
                attrs = el.attributes
                if isinstance(attrs, str):
                    attrs = json.loads(attrs)
                if isinstance(attrs, dict) and attrs.get("selector"):
                    selector = attrs["selector"]
        finally:
            db.close()
    return selector


def page_fragment(extra: dict) -> str:
    """页面标题筛选（可选）。"""
    return convert_value(extra.get("titleFragment", ""), "string", {}) if extra.get("titleFragment") else ""


def emit_error(runner, step_id, instr, msg: str) -> bool:
    runner.completed += 1
    result = {"error": msg}
    runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                            "status": "error", "result": result})
    return False
