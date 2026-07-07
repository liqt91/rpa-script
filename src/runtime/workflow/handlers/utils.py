"""Handler 工具函数 — 变量插值、值转换等公共逻辑。"""
import re

_VAR_RE = re.compile(r"\$\{(\w+)\}|\{\{(\w+)\}\}")


def resolve_vars(text: str, runner_vars: dict) -> str:
    """将字符串中的 ${varName} 替换为 runner.vars 中的值。"""
    def _replacer(m):
        name = m.group(1) or m.group(2)
        return str(runner_vars.get(name, m.group(0)))
    return _VAR_RE.sub(_replacer, str(text))


def convert_value(value, value_type: str, vars: dict | None = None):
    """将字符串值按类型转换。

    value_type:
      - string: 原样返回字符串（支持 ${var} 变量插值）
      - number: 转为 int/float
      - bool: 转为 True/False
      - list: JSON 解析为列表
      - dict: JSON 解析为字典
      - expression: Python 表达式求值，可访问 vars 中的变量
    """
    if value_type == "number":
        try:
            return float(value) if "." in str(value) else int(value)
        except (ValueError, TypeError):
            return 0
    elif value_type == "bool":
        return str(value).lower() in ("true", "1", "yes")
    elif value_type == "list":
        import json
        try:
            return json.loads(str(value))
        except Exception:
            return [value]
    elif value_type == "dict":
        import json
        try:
            return json.loads(str(value))
        except Exception:
            return {}
    elif value_type == "expression":
        return _eval_expression(str(value), vars or {})
    else:
        # string — resolve ${var} placeholders
        return resolve_vars(str(value), vars or {})


def _eval_expression(expr: str, vars: dict):
    """安全求值 Python 表达式，可访问 vars 中的变量。"""
    safe_builtins = {
        "True": True, "False": False, "None": None,
        "int": int, "float": float, "str": str, "bool": bool,
        "len": len, "abs": abs, "round": round, "min": min, "max": max,
        "isinstance": isinstance,
    }
    safe_vars = {**safe_builtins, **vars}
    try:
        return eval(expr, {"__builtins__": {}}, safe_vars)
    except Exception:
        # Fallback: return original expression string
        return expr
