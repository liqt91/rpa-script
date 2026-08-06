"""Handler 工具函数 — 变量插值、值转换等公共逻辑。"""
import json as _json
import re

_VAR_RE = re.compile(r"\{\{([^}]+)\}\}|\$\{([^}]+)\}")

# 旧类型名兼容映射 (str-input→string, int-number→number, etc.)
_LEGACY_TYPE_MAP = {
    "str-input": "string", "str-textarea": "text", "str-var": "string",
    "str-dropdown": "select", "str-element": "element",
    "int-number": "number", "bool-check": "boolean",
    "any-expr": "code", "list-input": "code", "dict-input": "code",
}


def resolve_vars(text: str, runner_vars: dict) -> str:
    """将字符串中的 {{varName}} 或 ${varName} 替换为 runner.vars 中的值。"""
    def _replacer(m):
        name = m.group(1) or m.group(2)
        return str(runner_vars.get(name, m.group(0)))
    return _VAR_RE.sub(_replacer, str(text))


def resolve_vars_json(text: str, runner_vars: dict) -> str:
    """同 resolve_vars，但字符串值用 json.dumps 包裹以保持 JSON 合法。

    [{{a}}, {{b}}] -> ["值A", "值B"]  <- 合法 JSON，json.loads 可用
    """
    def _replacer(m):
        name = m.group(1) or m.group(2)
        if name not in runner_vars:
            return m.group(0)
        val = runner_vars[name]
        if isinstance(val, (str, list, dict)):
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
    value_type = _LEGACY_TYPE_MAP.get(value_type, value_type)

    # any-input 保持自动推断：先尝试 JSON，再退回字符串
    if value_type == "any-input":
        s = str(value)
        resolved = resolve_vars_json(s, vars or {})
        try:
            return _json.loads(resolved)
        except Exception:
            return resolve_vars(s, vars or {})

    if value_type == "number":
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return 0
    elif value_type == "boolean":
        return str(value).lower() in ("true", "1", "yes")
    elif value_type == "code":
        s = str(value)
        # 显式表达式：=expr 前缀，跳过 JSON 推断，直接求值
        if s.startswith("="):
            resolved = resolve_vars(s[1:], vars or {})
            return _eval_expression(resolved, vars or {})
        # 否则：{{}} 替换 → JSON 推断 → 兜底表达式求值
        resolved = resolve_vars_json(s, vars or {})
        try:
            return _json.loads(resolved)
        except Exception:
            return _eval_expression(s, vars or {})
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
        "range": range, "list": list, "dict": dict,
        "isinstance": isinstance,
    }
    safe_vars = {**safe_builtins, **vars}
    return eval(expr, {"__builtins__": {}}, safe_vars)
