"""日志 — log"""
from ..registry import register_handler, Param
from ..utils import resolve_vars
import logging

logger = logging.getLogger(__name__)


@register_handler(type="log", label="打印日志", category="高级", runtime="backend",
    icon="fa-terminal", icon_color="text-gray-700", bg_color="bg-gray-100",
    category_order=90, command_order=20)
class LogHandler:
    params = [
        Param("message", "日志内容", "text", required=True, placeholder="支持 ${var} 变量插值"),
        Param("level", "日志级别", "select",
              options=[{"label":"信息","value":"info"},{"label":"警告","value":"warn"},{"label":"错误","value":"error"}],
              default="info", group="advanced"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        msg = extra.get("message", "")
        level = extra.get("level", "info")
        resolved = resolve_vars(msg, runner.vars)
        getattr(logger, level, logger.info)(f"[Log] {resolved}")
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
            "status": "success", "result": {"log": resolved}})
        runner.completed += 1
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"),
            "result": {"log": resolved}})
        return True
