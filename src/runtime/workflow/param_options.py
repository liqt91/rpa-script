"""共享参数模板 — $ref 展开。

指令 JSON 的 params 支持 {"$ref": "<模板名>"} 引用 src/runtime/commands/types/value_types.json
中 paramTemplates 段的共享参数模板（引用处的其他字段覆盖合并），避免 searchMode/
clickType/method 等参数在多个指令间重复维护。new_catalog（面板）、definitions API
（编辑器）、generate_commands（生成桩）统一经此展开。
"""
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_VALUE_TYPES_PATH = _ROOT / "src" / "runtime" / "commands" / "types" / "value_types.json"

_CACHE: dict | None = None


def load_param_options() -> dict:
    """读取 value_types.json paramTemplates 段的模板表（进程内缓存）。"""
    global _CACHE
    if _CACHE is None:
        _CACHE = {}
        try:
            if _VALUE_TYPES_PATH.exists():
                with open(_VALUE_TYPES_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                _CACHE = data.get("paramTemplates", {}) or {}
        except Exception:
            _CACHE = {}
    return _CACHE


def reload_param_options() -> None:
    """清缓存（/api/commands/param-options、value-types 保存与热重载时调用）。"""
    global _CACHE
    _CACHE = None


def resolve_params(params: list) -> list:
    """展开 params 中的 $ref 引用：{"$ref": name, ...overrides} → 模板定义 + 覆盖字段。"""
    options = load_param_options()
    out = []
    for p in params or []:
        if not isinstance(p, dict):
            out.append(p)
            continue
        ref = p.pop("$ref", None) if "$ref" in p else None
        if ref is None:
            out.append(p)
            continue
        base = options.get(ref)
        if not isinstance(base, dict):
            # 未知引用：保留 $ref 原样，避免静默吞掉（校验可发现）
            out.append({**p, "$ref": ref})
            continue
        merged = {**base, **p}
        merged.pop("$ref", None)
        out.append(merged)
    return out
