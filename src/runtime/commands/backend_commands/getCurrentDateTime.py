"""读取当前日期时间 — getCurrentDateTime (backend)"""
import datetime as _dt

from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import clean_var_ref


@register_handler(cmd="getCurrentDateTime", label="读取当前日期时间",
    category="变量及日志", runtime="backend",
    icon="fa-clock", icon_color="text-blue-500",
    bg_color="bg-blue-50",
    description="读取当前系统日期时间，按指定格式输出到变量。",
    category_order=30,
    command_order=15,
    summary_tpl="{format}")
class GetCurrentDateTimeHandler:
    params = [
        Param("format", "格式", "string", default="%Y-%m-%d %H:%M:%S", group="主属性", description="strftime 格式，如 %Y-%m-%d 日期、%H:%M:%S 时间、%Y-%m-%d %H:%M:%S 日期时间"),
        Param("useUtc", "使用 UTC 时间", "boolean", default=False, group="advanced"),
        Param("resultVar", "保存到变量", "str-var", default="currentDateTime", group="output"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra", {})

        fmt = extra.get("format") or "%Y-%m-%d %H:%M:%S"
        use_utc = extra.get("useUtc", False)
        if isinstance(use_utc, str):
            use_utc = use_utc.lower() in ("true", "1", "yes")
        use_utc = bool(use_utc)
        result_var = clean_var_ref(extra.get("resultVar", "currentDateTime"))

        now = _dt.datetime.now(_dt.timezone.utc) if use_utc else _dt.datetime.now()
        value = now.strftime(fmt)

        if result_var:
            runner.vars[result_var] = value

        result = {"dateTime": value, "format": fmt, "useUtc": use_utc}
        runner.completed += 1
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
