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

# Commands that the content script can execute directly.
# Others (setVar, log, pushItem, return, custom, takeScreenshot, closeTab)
# are skipped because they need backend interpretation or browser APIs
# unavailable to content scripts.
_SUPPORTED_TYPES = {
    "navigate", "click", "input", "inputAndPressEnter",
    "getText", "getAttr", "getHtml", "getValue",
    "waitForElement", "sleep",
    "scrollToBottom", "scrollToTop", "scrollBy",
    "goBack", "goForward", "refresh",
    "pressKey", "hover", "clearInput", "selectOption",
    "newTab", "executeJs", "setVar",
}

# Mapping from workflow command type -> content-script instruction type
_TYPE_MAP = {
    "inputAndPressEnter": "input",
    "getText": "extract",
    "getAttr": "extract",
    "getHtml": "extract",
    "getValue": "extract",
    "waitForElement": "wait",
    "sleep": "wait",
    "scrollToBottom": "scroll",
    "scrollToTop": "scroll",
    "scrollBy": "scroll",
}


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
    Only emits instructions for types supported by the content script.
    Container nodes are flattened (children are emitted directly).
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
                is_container = True

            if is_container:
                # Flatten: just recurse children (no enterBlock/exitBlock markers)
                _walk(child.id, depth + 1)
            elif child.type not in _SUPPORTED_TYPES:
                # Skip unsupported commands (setVar, log, pushItem, etc.)
                continue
            else:
                step_counter[0] += 1
                instr = _emit_instruction(child, step_counter[0])
                # Remap type for content script compatibility
                instr["type"] = _TYPE_MAP.get(child.type, child.type)
                # Adjust extra for remapped types
                if child.type == "sleep":
                    instr["extra"] = {**extra, "seconds": extra.get("seconds", 1)}
                elif child.type in ("scrollToBottom", "scrollToTop"):
                    instr["extra"] = {**extra, "direction": "bottom" if child.type == "scrollToBottom" else "top"}
                elif child.type == "scrollBy":
                    instr["extra"] = {**extra, "direction": "down" if (extra.get("y") or 500) > 0 else "up", "amount": abs(extra.get("y", 500))}
                elif child.type == "getText":
                    instr["extra"] = {**extra, "attribute": None}
                elif child.type == "getAttr":
                    instr["extra"] = {**extra, "attribute": extra.get("attrName")}
                elif child.type == "getHtml":
                    instr["extra"] = {**extra, "attribute": "innerHTML"}
                elif child.type == "getValue":
                    instr["extra"] = {**extra, "attribute": "value"}
                instructions.append(instr)

    _walk(None)
    return instructions
