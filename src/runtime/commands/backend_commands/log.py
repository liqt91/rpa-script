"""输出日志 — log (backend)"""
from src.runtime.workflow.handlers.registry import register_handler, Param


@register_handler(
    cmd="log", label="输出日志", category="数据", runtime="backend",
    icon="fa-terminal", icon_color="text-gray-500", bg_color="bg-gray-50",
    category_order=40, command_order=10,
    description="输出一条消息到运行日志",
    summary_tpl="{message}")
class LogHandler:
    params = [
        Param("message", "日志内容", "text", placeholder="支持 {{变量}} 引用"),
        Param("level", "日志级别", "select", default="info",
              options=[{"label": "信息", "value": "info"},
                       {"label": "警告", "value": "warning"},
                       {"label": "错误", "value": "error"}],
              group="advanced"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        from src.runtime.workflow.handlers.utils import convert_value
        message = convert_value(extra.get("message", ""), "string", runner.vars)
        level = extra.get("level", "info")
        result = {"log": str(message), "level": level}
        runner.completed += 1
        # P2: 与其他指令一致，结果带 stepId/nodeId/status 包装，便于结果面板定位到步骤
        runner.results.append({
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "status": "success",
            "result": result,
        })
        await runner._emit({
            "type": "stepComplete",
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "result": result,
        })
        return True
