"""Handler 工具函数 — 变量插值、值转换等公共逻辑。"""
import re

_VAR_RE = re.compile(r"\{\{([^}]+)\}\}")


def resolve_vars(text: str, runner_vars: dict) -> str:
    """将字符串中的 {{varName}} 替换为 runner.vars 中的值。"""
    def _replacer(m):
        name = m.group(1)
        return str(runner_vars.get(name, m.group(0)))
    return _VAR_RE.sub(_replacer, str(text))


def resolve_vars_json(text: str, runner_vars: dict) -> str:
    """同 resolve_vars，但字符串值用 json.dumps 包裹以保持 JSON 合法。

    [{{a}}, {{b}}] -> ["值A", "值B"]  <- 合法 JSON，json.loads 可用
    """
    import json as _json

    def _replacer(m):
        name = m.group(1)
        if name not in runner_vars:
            return m.group(0)
        val = runner_vars[name]
        if isinstance(val, str):
            return _json.dumps(val, ensure_ascii=False)
        if isinstance(val, (list, dict)):
            return _json.dumps(val, ensure_ascii=False)
        return str(val)
    return _VAR_RE.sub(_replacer, str(text))


_VAR_REF_RE = re.compile(r'^\{\{([^}]+)\}\}$')


def clean_var_ref(val: str) -> str:
    """剥 {{statistic}} -> statistic，只返回裸变量名。非 {{}} 格式原样返回。"""
    v = val.strip() if isinstance(val, str) else str(val)
    m = _VAR_REF_RE.match(v)
    return m.group(1) if m else v


def convert_value(value, value_type: str, vars: dict | None = None):
    """将字符串值按类型转换。

    value_type: 参数类型名，见 commands/value_types.json
    """
    # 旧类型名兼容映射 (str-input→string, int-number→number, etc.)
    _LEGACY = {
        "str-input": "string", "str-textarea": "text", "str-var": "string",
        "str-dropdown": "select", "str-element": "element",
        "int-number": "number", "bool-check": "boolean",
        "any-expr": "code", "any-input": "string",
        "list-input": "code", "dict-input": "code",
    }
    value_type = _LEGACY.get(value_type, value_type)

    if value_type == "number":
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return 0
    elif value_type == "boolean":
        return str(value).lower() in ("true", "1", "yes")
    elif value_type == "code":
        import json as _json
        resolved = resolve_vars_json(str(value), vars or {})
        try:
            return _json.loads(resolved)
        except Exception:
            return _eval_expression(str(value), vars or {})
    elif value_type == "element":
        return value
    else:
        # string / text / select
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
