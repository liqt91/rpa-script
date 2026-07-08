"""Handler 工具函数 — 变量插值、值转换等公共逻辑。"""
import re

_VAR_RE = re.compile(r"\$\{(\w+)\}|\{\{(\w+)\}\}")


def resolve_vars(text: str, runner_vars: dict) -> str:
    """将字符串中的 ${varName} 替换为 runner.vars 中的值。"""
    def _replacer(m):
        name = m.group(1) or m.group(2)
        return str(runner_vars.get(name, m.group(0)))
    return _VAR_RE.sub(_replacer, str(text))


def resolve_vars_json(text: str, runner_vars: dict) -> str:
    """同 resolve_vars，但字符串值用 json.dumps 包裹以保持 JSON 合法。
    
    [${a}, ${b}] → ["值A", "值B"]  ← 合法 JSON，json.loads 可用
    """
    import json as _json

    def _replacer(m):
        name = m.group(1) or m.group(2)
        if name not in runner_vars:
            return m.group(0)  # 未定义，保留原样
        val = runner_vars[name]
        if isinstance(val, str):
            return _json.dumps(val, ensure_ascii=False)
        if isinstance(val, (list, dict)):
            return _json.dumps(val, ensure_ascii=False)
        return str(val)
    return _VAR_RE.sub(_replacer, str(text))


_VAR_REF_RE = re.compile(r'^\$\{([^}]+)\}$|^{{([^}]+)}}$')


def clean_var_ref(val: str) -> str:
    """剥 ${statistic} → statistic，只返回裸变量名。非 ${} 格式原样返回。"""
    v = val.strip() if isinstance(val, str) else str(val)
    m = _VAR_REF_RE.match(v)
    return (m.group(1) or m.group(2)) if m else v


def convert_value(value, value_type: str, vars: dict | None = None):
    """将字符串值按类型转换。

    value_type: 回传类型-前端控件, 如 str-input / int-number / list-input / any-expr
    """
    # 兼容旧类型名 → 新类型名
    _LEGACY = {
        "string": "str-input", "text": "str-input",
        "number": "int-number",
        "bool": "bool-check",
        "list": "list-input",
        "dict": "dict-input",
        "expression": "any-expr",
    }
    value_type = _LEGACY.get(value_type, value_type)

    if value_type == "int-number":
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return 0
    elif value_type == "bool-check":
        return str(value).lower() in ("true", "1", "yes")
    elif value_type == "list-input":
        # JSON 安全的 ${} 替换，再反序列化：自动加引号，文本里逗号不分裂
        import json as _json
        resolved = resolve_vars_json(str(value), vars or {})
        try:
            return _json.loads(resolved)
        except Exception:
            return [resolved]
    elif value_type == "dict-input":
        import json as _json
        resolved = resolve_vars_json(str(value), vars or {})
        try:
            return _json.loads(resolved)
        except Exception:
            return {}
    elif value_type == "any-expr":
        return _eval_expression(str(value), vars or {})
    elif value_type == "any-input":
        # ${} 替换 → JSON 推断 → 兜底字符串
        import json as _json2
        resolved = resolve_vars(str(value), vars or {})
        try:
            return _json2.loads(resolved)
        except Exception:
            return resolved
    else:
        # str-input / str-textarea / str-var / str-dropdown / str-element
        return resolve_vars(str(value), vars or {})


def _eval_expression(expr: str, vars: dict):
    """求值 Python 表达式，可访问 vars 中的变量。失败抛出异常，不兜底。"""
    safe_builtins = {
        "True": True, "False": False, "None": None,
        "int": int, "float": float, "str": str, "bool": bool,
        "len": len, "abs": abs, "round": round, "min": min, "max": max,
        "isinstance": isinstance,
    }
    safe_vars = {**safe_builtins, **vars}
    return eval(expr, {"__builtins__": {}}, safe_vars)
