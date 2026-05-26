"""
Extension Emitter — schema-driven instruction sequence generator.

Driven by COMMAND_REGISTRY["runtimes"].extension declarations.
Only emits commands that declare extension runtime support.
Container nodes are flattened (children emitted directly).
"""

import json
from src.repo import runtime_models as models
from src.runtime.workflow.commands import COMMAND_REGISTRY


# Extra transforms applied per command type for extension compatibility.
# Key: workflow command type  →  Value: lambda(extra) -> adjusted_extra
_EXTRA_TRANSFORMS = {
    "sleep": lambda e: {**e, "seconds": e.get("seconds", 1)},
    "scrollToBottom": lambda e: {**e, "direction": "bottom"},
    "scrollToTop": lambda e: {**e, "direction": "top"},
    "scrollBy": lambda e: {**e, "direction": "down" if (e.get("y") or 500) > 0 else "up", "amount": abs(e.get("y", 500))},
    "getText": lambda e: {**e, "attribute": None},
    "getAttr": lambda e: {**e, "attribute": e.get("attrName")},
    "getHtml": lambda e: {**e, "attribute": "innerHTML"},
    "getValue": lambda e: {**e, "attribute": "value"},
    "inputAndPressEnter": lambda e: {**e, "pressEnter": True},
}


def _build_by_parent(nodes: list[models.WorkflowNode]) -> dict:
    """Group nodes by parent_id."""
    by_parent: dict = {}
    for n in nodes:
        by_parent.setdefault(n.parent_id, []).append(n)
    for pid in by_parent:
        by_parent[pid].sort(key=lambda x: x.order)
    return by_parent


def _parse_extra(node: models.WorkflowNode) -> dict:
    if node.extra and isinstance(node.extra, str):
        try:
            return json.loads(node.extra)
        except Exception:
            return {}
    return node.extra or {}


def _emit_instruction(node: models.WorkflowNode, step_index: int, handler: str) -> dict:
    """Convert a single node to an instruction dict."""
    extra = _parse_extra(node)
    # Apply extension-specific extra transforms
    transform = _EXTRA_TRANSFORMS.get(node.type)
    if transform:
        extra = transform(extra)
    return {
        "stepId": f"step_{step_index}",
        "nodeId": node.id,
        "cmdType": node.type,          # original workflow command type
        "type": handler,               # content-script handler name
        "locator": node.locator,
        "locatorType": node.locator_type or "css",
        "action": node.action,
        "extra": extra,
    }


def _get_extension_runtime(cmd_type: str) -> dict | None:
    """Return the extension runtime declaration for a command, or None."""
    cmd = COMMAND_REGISTRY.get(cmd_type)
    if not cmd:
        return None
    return cmd.get("runtimes", {}).get("extension")


def build_instructions(nodes: list[models.WorkflowNode]) -> list[dict]:
    """
    Flatten a node tree into a linear instruction sequence.
    Only emits instructions for commands that declare extension runtime support.
    Container nodes are flattened (children are emitted directly).
    """
    by_parent = _build_by_parent(nodes)
    instructions: list[dict] = []
    step_counter = [0]

    def _walk(parent_id, depth=0):
        children = by_parent.get(parent_id, [])
        for child in children:
            extra = _parse_extra(child)
            cmd = COMMAND_REGISTRY.get(child.type) or {}
            is_container = cmd.get("isContainer", False)

            if not is_container and child.type in ("if", "for", "loop", "try", "while"):
                is_container = True

            if is_container:
                # Flatten: just recurse children
                _walk(child.id, depth + 1)
                continue

            runtime = _get_extension_runtime(child.type)
            if not runtime:
                # Skip commands without extension runtime declaration
                continue

            step_counter[0] += 1
            instr = _emit_instruction(child, step_counter[0], runtime["handler"])
            instructions.append(instr)

    _walk(None)
    return instructions
