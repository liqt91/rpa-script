"""
Extension Emitter — translates WorkflowNode list into JSON instruction sequence.

Output format (one instruction per step):
    {
        "stepId": str,       # unique within run
        "type": str,         # command type (navigate, click, input, ...)
        "locator": str,      # optional element locator
        "locatorType": str,  # css | xpath | id | class | text | data-attr
        "action": str,       # optional action sub-type
        "extra": dict,       # command-specific parameters
    }

Container nodes (if/for/loop) are flattened into a linear sequence with
enterBlock/exitBlock markers so the extension runner can handle them
without tree traversal.
"""

import json
from src.repo import runtime_models as models


def _build_by_parent(nodes: list[models.WorkflowNode]) -> dict:
    """Group nodes by parent_id."""
    by_parent: dict = {}
    for n in nodes:
        by_parent.setdefault(n.parent_id, []).append(n)
    # Sort each group by order
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


def _emit_instruction(node: models.WorkflowNode, step_index: int) -> dict:
    """Convert a single node to an instruction dict."""
    extra = _parse_extra(node)
    return {
        "stepId": f"step_{step_index}",
        "type": node.type,
        "locator": node.locator,
        "locatorType": node.locator_type or "css",
        "action": node.action,
        "extra": extra,
    }


def build_instructions(nodes: list[models.WorkflowNode]) -> list[dict]:
    """
    Flatten a node tree into a linear instruction sequence.

n    Container nodes (if/for/loop/try) are emitted as:
        { type: "enterBlock", blockType: "if", condition: ... }
        ...children...
        { type: "exitBlock", blockType: "if" }

n    The extension runner is responsible for interpreting enterBlock/exitBlock.
    """
    by_parent = _build_by_parent(nodes)
    instructions: list[dict] = []
    step_counter = [0]

    def _walk(parent_id, depth=0):
        children = by_parent.get(parent_id, [])
        for child in children:
            extra = _parse_extra(child)
            cmd_info = getattr(child, "_command_info", None)
            is_container = cmd_info.get("isContainer", False) if cmd_info else False

            if not is_container and child.type in ("if", "for", "loop", "try", "while"):
                # Fallback: check type name for container detection
                is_container = True

            if is_container:
                # enterBlock marker
                step_counter[0] += 1
                instructions.append({
                    "stepId": f"step_{step_counter[0]}",
                    "type": "enterBlock",
                    "blockType": child.type,
                    "locator": child.locator,
                    "locatorType": child.locator_type or "css",
                    "extra": extra,
                })
                # Recurse children
                _walk(child.id, depth + 1)
                # exitBlock marker
                step_counter[0] += 1
                instructions.append({
                    "stepId": f"step_{step_counter[0]}",
                    "type": "exitBlock",
                    "blockType": child.type,
                    "extra": {},
                })
            else:
                step_counter[0] += 1
                instructions.append(_emit_instruction(child, step_counter[0]))

    _walk(None)
    return instructions
