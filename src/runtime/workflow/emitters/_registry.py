"""Shared emit helpers and dispatch registry."""

import json
from typing import Any

from src.repo import runtime_models as models


def _indent(depth: int) -> str:
    return "    " * depth


def _loc_call(node: models.WorkflowNode, extra: dict) -> str:
    """Build tab.ele('...') style locator call."""
    loc = (node.locator or "").replace("'", "\\'")
    method = node.method or "ele"
    if not loc:
        return "tab"
    return f"tab.{method}('{loc}')"


def _var_ref(name: str) -> str:
    """Sanitize variable name."""
    return name.strip() if name else "_tmp"


_EMIT_HANDLERS: dict[str, Any] = {}


def _handler(name: str):
    def decorator(fn):
        _EMIT_HANDLERS[name] = fn
        return fn
    return decorator


def _emit_dispatch(node: models.WorkflowNode, extra: dict, depth: int,
                   by_parent: dict, lines: list[str]) -> None:
    prefix = _indent(depth)
    from src.runtime.workflow.commands import COMMAND_REGISTRY
    cmd = COMMAND_REGISTRY.get(node.type, {})
    label = cmd.get("label", node.type)
    lines.append(f"{prefix}# WF_NODE id={node.id} type={node.type} label={label}")
    handler = _EMIT_HANDLERS.get(node.type)

    if handler:
        handler(node, extra, depth, prefix, by_parent, lines)
    else:
        loc = _loc_call(node, extra)
        lines.append(f"{prefix}# TODO: {node.type} -> {loc}")
