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
    out = {
        "name": field["name"],
        "label": field.get("label", field["name"]),
        "type": field.get("type", "string"),
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
    if field.get("isPrimaryElement"):
        out["isPrimaryElement"] = True
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


# Generic params injected into every non-structural command.
# Loaded from commands/types/generic_params.json at runtime (shared with registry.py).

def _load_generic_params() -> dict:
    import json as _json
    json_path = ROOT / "src" / "runtime" / "commands" / "types" / "generic_params.json"
    try:
        if json_path.exists():
            with open(json_path, encoding="utf-8") as f:
                return _json.load(f)
    except Exception:
        pass
    # hardcoded fallback
    return {
        "common": [
            {"name": "onError", "label": "执行失败时", "type": "select",
             "options": [{"label": "停止", "value": "stop"}, {"label": "继续", "value": "continue"}, {"label": "重试", "value": "retry"}],
             "default": "stop", "group": "advanced"},
            {"name": "retryCount", "label": "重试次数", "type": "number", "default": 3, "group": "advanced"},
            {"name": "timeout", "label": "超时(秒)", "type": "number", "default": 10, "group": "advanced"},
            {"name": "description", "label": "步骤说明", "type": "text", "default": "", "group": "advanced"},
        ],
        "extensionOnly": [
            {"name": "humanLike", "label": "模拟人工操作", "type": "boolean", "default": True, "group": "advanced"},
        ],
    }


def _merge_fields(specific, generic):
    """Merge generic params into specific, dedup by name (specific wins)."""
    seen = {f["name"] for f in specific if f.get("name")}
    merged = list(specific)
    for f in generic:
        if f.get("name") and f["name"] not in seen:
            seen.add(f["name"])
            merged.append(f)
    return merged


def _generic_extra_params(runtime: str) -> list:
    """Return generic params that apply to a given runtime tier."""
    params = _load_generic_params()
    if runtime in ("extension",):
        return params.get("common", []) + params.get("extensionOnly", [])
    if runtime in ("backend",):
        return params.get("common", [])
    return []


_CATEGORY_NAMES = {}  # slug -> Chinese name, loaded on first call


def _load_category_names() -> dict:
    """Load category slug→name mapping from categories.json."""
    global _CATEGORY_NAMES
    if not _CATEGORY_NAMES:
        path = ROOT / "src" / "runtime" / "commands" / "types" / "categories.json"
        try:
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                _CATEGORY_NAMES = {c["slug"]: c["name"] for c in data.get("categories", [])}
        except Exception:
            pass
    return _CATEGORY_NAMES


def _category_name(slug: str) -> str:
    """Map a category slug to its Chinese display name."""
    return _load_category_names().get(slug, slug)


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
            name = _category_name(cat)
            if name not in commands_by_cat:
                commands_by_cat[name] = []
                categories.append(name)

        rt_info = _runtime_info(d)
        is_structural = d.get("isContainer") or d.get("isBranch") or d.get("isStructural")
        cmd = {
            "cmd": d["cmd"],
            "label": d.get("label", d["cmd"]),
            "category": _category_name(cats[0]) if cats else "其他",
            "icon": d.get("icon", "fa-circle"),
            "iconColor": d.get("iconColor", "text-gray-500"),
            "bgColor": d.get("bgColor", "bg-gray-50"),
            "description": d.get("description", ""),
            "fields": _merge_fields(
                [_normalize_field(p) for p in d.get("params", [])],
                [] if is_structural else _generic_extra_params(d.get("runtime", "extension")),
            ),
            "isContainer": bool(d.get("isContainer")),
            "isBranch": bool(d.get("isBranch")),
            "isStructural": bool(d.get("isStructural")),
            "closesWith": d.get("closesWith"),
            "categoryOrder": d.get("categoryOrder", 0),
            "commandOrder": d.get("commandOrder", 0),
            "isBuiltin": False,
            "enabled": True,
            "isNew": True,
            **rt_info,
        }
        for cat in cats:
            commands_by_cat[_category_name(cat)].append(cmd)

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
