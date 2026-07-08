"""自定义代码 — custom"""
from ..registry import register_handler, Param
import logging

logger = logging.getLogger(__name__)


@register_handler(type="custom", label="自定义代码", category="高级", runtime="backend",
    icon="fa-code", icon_color="text-gray-700", bg_color="bg-gray-100", category_order=90, command_order=10,
    description="执行自定义 Python 代码，可访问 runner.vars / _table / _table_data / logger 等上下文")
class CustomHandler:
    params = [
        Param("code", "Python 代码", "any-expr", required=True),
        Param("resultVar", "保存结果到", "str-var", group="output"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        code = extra.get("code", "")
        result_var = extra.get("resultVar") or extra.get("varName") or extra.get("saveToVar")
        # str-var 填的是 ${变量名}，剥壳取裸名
        if result_var:
            from ..utils import clean_var_ref
            result_var = clean_var_ref(result_var)

        # 用 _TableAccessor 包装，支持 _table[0][0] / _table[0]["A"] 索引
        from src.runtime.workflow.extension_runner import _TableAccessor
        safe_globals = {
            "__builtins__": {
                "print": print, "len": len, "range": range, "int": int, "float": float,
                "str": str, "bool": bool, "list": list, "dict": dict, "set": set,
                "tuple": tuple, "zip": zip, "enumerate": enumerate, "map": map, "filter": filter,
                "sum": sum, "min": min, "max": max, "abs": abs, "round": round,
                "isinstance": isinstance, "type": type, "getattr": getattr, "hasattr": hasattr,
                "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
                "json": __import__("json"), "re": __import__("re"), "time": __import__("time"),
            },
            "_vars": runner.vars,
            "_table": _TableAccessor(getattr(runner, '_table_data', {})),
            "_log": logger.info,
        }
        safe_locals = {}
        try:
            exec(code, safe_globals, safe_locals)
        except Exception as e:
            logger.error(f"[custom] 代码执行失败: {e}")
            raise

        result = safe_locals.get(result_var) if result_var else safe_locals.get('result')
        if result is None and result_var:
            # 也尝试取 'result' 做兜底
            result = safe_locals.get('result')
        if result_var and result is not None:
            runner.vars[result_var] = result

        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "success",
            "result": {"custom": str(result)[:200] if result else "executed"}})
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"),
            "result": {"custom": str(result)[:200] if result else "executed"}})
        return True
