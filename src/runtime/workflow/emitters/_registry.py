"""Shared emit helpers and dispatch registry."""

import json
import re
from typing import Any

from src.repo import runtime_models as models


def _indent(depth: int) -> str:
    return "    " * depth


def _py_str(val: Any) -> str:
    """将值安全转为 Python 字符串字面量（用 repr 处理引号、换行、反斜杠等）。"""
    if val is None:
        return "''"
    return repr(str(val))


_LOCATOR_KEYS = {"locator", "selectorFamily", "type", "selector", "syntax"}


def _normalize_locator(node: models.WorkflowNode) -> str | list:
    """Parse JSON-encoded array locators back to Python objects."""
    loc = node.locator
    if isinstance(loc, str):
        text = loc.strip()
        if text.startswith("[") or text.startswith("{"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [
                        {k: v for k, v in item.items() if k in _LOCATOR_KEYS}
                        if isinstance(item, dict) else item
                        for item in parsed
                    ]
                return parsed
            except Exception:
                return text
        return text
    if isinstance(loc, list):
        return [
            {k: v for k, v in item.items() if k in _LOCATOR_KEYS}
            if isinstance(item, dict) else item
            for item in loc
        ]
    return loc or ""


def _loc_str(node: models.WorkflowNode, element_map: dict | None = None) -> str:
    """Return just the resolved locator string (for use in wait/scroll/etc)."""
    if element_map and node.element_name:
        el = element_map.get(node.element_name)
        if el and el.drission_selector:
            return el.drission_selector
    # fallback: legacy direct locator storage
    loc = _normalize_locator(node)
    if isinstance(loc, list):
        return loc[0] if loc else ""
    return loc or ""


def _loc_str_by_name(element_name: str | None, element_map: dict | None = None) -> str:
    """Return just the resolved locator string for a named element."""
    if element_map and element_name:
        el = element_map.get(element_name)
        if el and el.drission_selector:
            return el.drission_selector
    return ""


def _loc_call(node: models.WorkflowNode, extra: dict, element_map: dict | None = None) -> str:
    """Build tab.ele('...') style locator call."""
    return _loc_call_by_name(node.element_name, extra, element_map)


def _loc_call_by_name(element_name: str | None, extra: dict, element_map: dict | None = None) -> str:
    """Build tab.ele('...') style locator call for a named element."""
    # Resolve from element_map first (per-workflow element library)
    if element_map and element_name:
        el = element_map.get(element_name)
        if el and el.drission_selector:
            loc = el.drission_selector
            target_mode = el.target_mode or "single"
            method = "eles" if target_mode == "list" else "ele"
            visibility_mode = extra.get("visibilityMode")
            visible_only = visibility_mode != "any" if visibility_mode else extra.get("visibleOnly", True)
            if visible_only and method == "ele":
                return f"_ele_visible(tab, {_py_str(loc)})"
            return f"tab.{method}({_py_str(loc)})"

    # Fallback: legacy direct locator storage (should not happen after migration)
    loc = ""
    target_mode = "single"
    method = "eles" if target_mode == "list" else "ele"
    visibility_mode = extra.get("visibilityMode")
    visible_only = visibility_mode != "any" if visibility_mode else extra.get("visibleOnly", True)
    if not loc:
        return "tab"
    if isinstance(loc, list):
        if visible_only and method == "ele":
            return f"_try_locators(tab, {repr(loc)}, method={repr(method)}, visible_only=True)"
        return f"_try_locators(tab, {repr(loc)}, method={repr(method)})"
    if visible_only and method == "ele":
        return f"_ele_visible(tab, {_py_str(loc)})"
    return f"tab.{method}({_py_str(loc)})"


def _loc_calls(node: models.WorkflowNode, extra: dict, element_map: dict | None = None) -> list[str]:
    """Build locator calls for the primary element plus any additional element_names."""
    calls = [_loc_call(node, extra, element_map)]
    for name in extra.get("element_names") or []:
        if name:
            calls.append(_loc_call_by_name(name, extra, element_map))
    return calls


_VAR_REF_RE = re.compile(r'^\$\{(\w+)\}$|^\{\{(\w+)\}}$')


def _clean_var_ref(val: str) -> str:
    """Strip ${var} or {{var}} wrapper from a variable name field."""
    if not isinstance(val, str):
        return val
    m = _VAR_REF_RE.match(val.strip())
    if m:
        return m.group(1) or m.group(2)
    return val.strip()


def _var_ref(name: str) -> str:
    """Sanitize variable name."""
    return _clean_var_ref(name) if name else "_tmp"


_EMIT_HANDLERS: dict[str, Any] = {}


def _handler(name: str):
    def decorator(fn):
        _EMIT_HANDLERS[name] = fn
        return fn
    return decorator


def _emit_children(node: models.WorkflowNode, depth: int,
                   by_parent: dict, lines: list[str], element_map: dict | None = None) -> None:
    """Emit child nodes of a container command."""
    for child in by_parent.get(node.id, []):
        if getattr(child, "enabled", 1) == 0:
            continue
        extra = json.loads(child.extra) if child.extra else {}
        _emit_dispatch(child, extra, depth + 1, by_parent, lines, element_map)


def _emit_dispatch(node: models.WorkflowNode, extra: dict, depth: int,
                   by_parent: dict, lines: list[str], element_map: dict | None = None) -> None:
    if getattr(node, "enabled", 1) == 0:
        return
    prefix = _indent(depth)
    from src.runtime.workflow.commands import get_command
    cmd = get_command(node.type) or {}
    label = cmd.get("label", node.type)
    lines.append(f"{prefix}# WF_NODE id={node.id} type={node.type} label={label}")

    is_container = cmd.get("isContainer")
    is_structural = cmd.get("isStructural")
    handler = _EMIT_HANDLERS.get(node.type)

    if not handler:
        loc = _loc_call(node, extra, element_map)
        lines.append(f"{prefix}# TODO: {node.type} -> {loc}")
        return

    if is_container or is_structural:
        handler(node, extra, depth, prefix, by_parent, lines, element_map)
        return

    # 普通指令：包装 try/except/retry + 人工延迟
    on_error = extra.get("onError", "stop")
    retry_count = extra.get("retryCount", 3)

    handler_lines: list[str] = []
    handler(node, extra, depth, prefix, by_parent, handler_lines, element_map)
    handler_lines.append(f"{prefix}_human_delay()")

    if on_error == "retry":
        lines.append(f"{prefix}for _retry_idx in range({retry_count}):")
        lines.append(f"{prefix}    try:")
        for hl in handler_lines:
            content = hl[len(prefix):] if hl.startswith(prefix) else hl
            lines.append(f"{prefix}        {content}")
        lines.append(f"{prefix}        break")
        lines.append(f"{prefix}    except Exception as _e:")
        lines.append(
            f'{prefix}        print(f"[WF_ERROR] '
            f'指令 #{node.id} ({node.type}) {label} "'
            f'f"(retry {{_retry_idx + 1}}/{retry_count}): {{_e}}", file=sys.stderr)'
        )
        lines.append(f"{prefix}        if _retry_idx < {retry_count - 1}:")
        lines.append(f"{prefix}            time.sleep(0.5)")
        lines.append(f"{prefix}else:")
        lines.append(
            f'{prefix}    raise RuntimeError('
            f'f"指令 #{node.id} ({node.type}) {label} '
            f'重试 {retry_count} 次后仍然失败")'
        )
    else:
        lines.append(f"{prefix}try:")
        for hl in handler_lines:
            content = hl[len(prefix):] if hl.startswith(prefix) else hl
            lines.append(f"{prefix}    {content}")
        lines.append(f"{prefix}except Exception as _e:")
        lines.append(
            f'{prefix}    print(f"[WF_ERROR] '
            f'指令 #{node.id} ({node.type}) {label}: {{_e}}", file=sys.stderr)'
        )
        if on_error == "continue":
            lines.append(f"{prefix}    pass  # continue on error")
        else:
            lines.append(f"{prefix}    raise")
