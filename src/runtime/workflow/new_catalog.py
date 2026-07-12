"""Catalog loader for new-system commands defined in commands/*.json.

This keeps JSON-driven commands isolated from the legacy DB-based command
catalog during development. The workflow editor can fetch this catalog
separately and visually mark the commands as "new".
"""
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent
COMMANDS_DIR = ROOT / "commands"


def _normalize_field(field: dict) -> dict:
    """Convert JSON param definition to workflow-editor field schema."""
    # Map new type names to NodeForm-compatible old names
    _TYPE_MAP = {
        "string": "str-input", "text": "str-textarea",
        "number": "int-number", "boolean": "bool-check",
        "select": "str-dropdown", "code": "any-expr",
        "element": "str-element", "hidden": "hidden",
    }
    field_type = field.get("type", "str-input")
    out = {
        "name": field["name"],
        "label": field.get("label", field["name"]),
        "type": _TYPE_MAP.get(field_type, field_type),
        "group": field.get("group", "主属性"),
    }
    if field.get("required"):
        out["required"] = True
    if "default" in field and field["default"] is not None:
        out["default"] = field["default"]
    if field.get("options"):
        out["options"] = field["options"]
    if field.get("placeholder"):
        out["placeholder"] = field["placeholder"]
    if field.get("description"):
        out["description"] = field["description"]
    return out


def _runtime_info(d: dict) -> dict:
    """Derive runtime metadata for the editor palette."""
    rtype = d.get("runtime", "extension")
    handler = d.get("handler", {})

    if rtype == "control":
        return {"hasRuntime": False, "local": False, "handler": None}

    # backend / extension both carry a runtime handler
    kind = handler.get("kind", "delegate")
    local = rtype == "backend"
    # The actual handler name used at runtime equals the command type for
    # generated delegate handlers; custom/backend reference their impl source.
    handler_name = d["cmd"] if kind == "delegate" else handler.get("source") or d["cmd"]
    return {"hasRuntime": True, "local": local, "handler": handler_name}


def load_new_catalog() -> dict[str, Any]:
    """Return a command catalog shaped like /api/workflows/commands."""
    commands_by_cat: dict[str, list] = {}
    categories: list[str] = []
    container_types: list[str] = []
    branch_types: list[str] = []

    for fp in sorted(COMMANDS_DIR.glob("*.json")):
        with open(fp, encoding="utf-8") as f:
            d = json.load(f)

        if not d.get("enabled", True):
            continue

        # Support new `categories` array (slugs) with fallback to old `category` string
        cats = d.get("categories") or []
        if not cats and d.get("category"):
            cats = [d["category"]]
        if not cats:
            cats = ["其他"]
        for cat in cats:
            if cat not in commands_by_cat:
                commands_by_cat[cat] = []
                categories.append(cat)

        runtime = _runtime_info(d)
        cmd = {
            "cmd": d["cmd"],
            "label": d.get("label", d["cmd"]),
            "category": cats[0] if cats else "其他",
            "icon": d.get("icon", "fa-circle"),
            "iconColor": d.get("iconColor", "text-gray-500"),
            "bgColor": d.get("bgColor", "bg-gray-50"),
            "description": d.get("description", ""),
            "fields": [_normalize_field(p) for p in d.get("params", [])],
            "isContainer": bool(d.get("isContainer")),
            "isBranch": bool(d.get("isBranch")),
            "isStructural": bool(d.get("isStructural")),
            "closesWith": d.get("closesWith"),
            "categoryOrder": d.get("categoryOrder", 0),
            "commandOrder": d.get("commandOrder", 0),
            "isBuiltin": False,
            "enabled": True,
            "isNew": True,
            **runtime,
        }
        for cat in cats:
            commands_by_cat[cat].append(cmd)

        if cmd["isContainer"]:
            container_types.append(cmd["cmd"])
        if cmd["isBranch"]:
            branch_types.append(cmd["cmd"])

    # Sort commands inside each category
    for cat in commands_by_cat:
        commands_by_cat[cat].sort(key=lambda c: (c["categoryOrder"], c["commandOrder"]))

    return {
        "categories": categories,
        "commands": commands_by_cat,
        "containerTypes": container_types,
        "branchTypes": branch_types,
    }
