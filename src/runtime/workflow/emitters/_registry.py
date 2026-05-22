"""Shared emit helpers and dispatch registry."""

import json
from typing import Any

from src.repo import runtime_models as models


def _indent(depth: int) -> str:
    return "    " * depth


def _py_str(val: Any) -> str:
    """将值安全转为 Python 字符串字面量（用 repr 处理引号、换行、反斜杠等）。"""
    if val is None:
        return "''"
    return repr(str(val))


def _loc_call(node: models.WorkflowNode, extra: dict) -> str:
    """Build tab.ele('...') style locator call."""
    loc = node.locator or ""
    method = node.method or "ele"
    if not loc:
        return "tab"
    return f"tab.{method}({_py_str(loc)})"


def _var_ref(name: str) -> str:
    """Sanitize variable name."""
    return name.strip() if name else "_tmp"


_EMIT_HANDLERS: dict[str, Any] = {}


def _handler(name: str):
    def decorator(fn):
        _EMIT_HANDLERS[name] = fn
        return fn
    return decorator


def _emit_children(node: models.WorkflowNode, depth: int,
                   by_parent: dict, lines: list[str]) -> None:
    """Emit child nodes of a container command."""
    for child in by_parent.get(node.id, []):
        extra = json.loads(child.extra) if child.extra else {}
        _emit_dispatch(child, extra, depth + 1, by_parent, lines)


def _emit_dispatch(node: models.WorkflowNode, extra: dict, depth: int,
                   by_parent: dict, lines: list[str]) -> None:
    prefix = _indent(depth)
    from src.runtime.workflow.commands import get_command
    cmd = get_command(node.type) or {}
    label = cmd.get("label", node.type)
    lines.append(f"{prefix}# WF_NODE id={node.id} type={node.type} label={label}")

    is_container = cmd.get("isContainer")
    is_structural = cmd.get("isStructural")
    handler = _EMIT_HANDLERS.get(node.type)

    if not handler:
        loc = _loc_call(node, extra)
        lines.append(f"{prefix}# TODO: {node.type} -> {loc}")
        return

    if is_container or is_structural:
        handler(node, extra, depth, prefix, by_parent, lines)
        return

    # 普通指令：包装 try/except/retry + 人工延迟
    on_error = extra.get("onError", "stop")
    retry_count = extra.get("retryCount", 3)

    handler_lines: list[str] = []
    handler(node, extra, depth, prefix, by_parent, handler_lines)
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
