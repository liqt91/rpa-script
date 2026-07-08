"""
Generate handler .py and .js files from command definition JSON files.

Usage: python scripts/generate_commands.py

JSON format (commands/<type>.json):
{
  "type": "clickElement",
  "label": "点击元素",
  "runtime": "extension",        // extension | backend | emitter
  "params": [...],
  "handler": {
    "kind": "delegate",          // delegate | custom | backend
    "function": "doClick"        // for delegate
    "source": "path/to/impl"     // for custom/backend, relative to project root
  }
}

Output:
  extension:  handlers/extension/<type>.py  +  extension/handlers/<type>.js
  backend:    handlers/backend/<type>.py
  emitter:    handlers/flow/<type>.py
"""

import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMANDS_DIR = ROOT / "commands"
HANDLERS_DIR = ROOT / "src" / "runtime" / "workflow" / "handlers"
EXT_JS_DIR = ROOT / "extension" / "handlers"
CONTENT_BASE = ROOT / "extension" / "content_base.js"


def load_definitions() -> list[dict]:
    defs = []
    for fp in sorted(COMMANDS_DIR.glob("*.json")):
        with open(fp, encoding="utf-8") as f:
            d = json.load(f)
            d["_file"] = fp.stem
            defs.append(d)
    return defs


def param_to_py(p: dict) -> str:
    """Convert a param dict to a Param(...) constructor string."""
    parts = [f'"{p["name"]}"', f'"{p.get("label", "")}"', f'"{p.get("type", "text")}"']
    if p.get("required"):
        parts.append("required=True")
    if p.get("default") is not None:
        parts.append(f'default={json.dumps(p["default"])}')
    if p.get("options"):
        opts = json.dumps(p["options"])
        parts.append(f"options={opts}")
    if p.get("group"):
        parts.append(f'group="{p["group"]}"')
    if p.get("placeholder"):
        parts.append(f'placeholder="{p["placeholder"]}"')
    if p.get("description"):
        parts.append(f'description="{p["description"]}"')
    return f"Param({', '.join(parts)})"


def param_js_type(ptype: str) -> str:
    """Map Python param type to JS extra field usage hint."""
    # Just informational — JS reads extra directly
    return ptype


def generate_py(d: dict) -> str:
    """Generate the Python handler declaration file."""
    rtype = d["runtime"]
    params = d.get("params", [])
    handler = d.get("handler", {})

    # Build class name
    class_name = f"{d['type'][0].upper()}{d['type'][1:]}Handler"

    # Build params list
    param_lines = []
    for p in params:
        param_lines.append(f"    {param_to_py(p)},")

    # Category order mapping
    cat_map = {"extension": "extension", "backend": "backend", "emitter": "flow"}
    sub_dir = cat_map.get(rtype, rtype)

    lines = [
        f'"""Command: {d["label"]}"""',
        "from ..registry import register_handler, Param",
        "",
        f'@register_handler(type="{d["type"]}", label="{d["label"]}",',
        f'    category="{d["category"]}", runtime="{rtype}",',
        f'    icon="{d.get("icon", "fa-circle")}", icon_color="{d.get("iconColor", "text-gray-500")}",',
        f'    bg_color="{d.get("bgColor", "bg-gray-50")}",',
    ]
    if d.get("isContainer"):
        lines.append("    is_container=True,")
    if d.get("isBranch"):
        lines.append("    is_branch=True,")
    if d.get("isStructural"):
        lines.append("    is_structural=True,")
    if d.get("closesWith"):
        lines.append(f'    closes_with="{d["closesWith"]}",')
    lines.append(f'    description="{d.get("description", "")}",')
    lines.append(f'    category_order={d.get("categoryOrder", 0)},')
    lines.append(f'    command_order={d.get("commandOrder", 0)},')
    if not d.get("enabled", True):
        lines.append("    enabled=False,")
    lines.append(")")
    lines.append(f"class {class_name}:")
    if param_lines:
        lines.append("    params = [")
        lines.extend(param_lines)
        lines.append("    ]")

    # Backend handler: reference impl file
    if rtype == "backend" and handler.get("kind") == "backend":
        source = handler.get("source", "")
        lines.append("")
        lines.append(f"    # Implementation loaded from: {source}")

    return "\n".join(lines)


def generate_js(d: dict) -> str:
    """Generate the JS handler registration file."""
    handler = d.get("handler", {})
    kind = handler.get("kind")

    if kind == "delegate":
        func = handler.get("function", "doClick")
        return f"\nregisterHandler('{d['type']}', async (args) => {func}(args));\n"

    if kind == "custom":
        source = handler.get("source", "")
        if source:
            src_path = ROOT / source
            if src_path.exists():
                return src_path.read_text(encoding="utf-8")
        # Fallback: minimal stub
        return (
            f"\nregisterHandler('{d['type']}', async function handler(args) {{\n"
            f"  // TODO: implement {d['label']}\n"
            f"  return {{ ok: true }};\n"
            f"}});\n"
        )

    return ""


def write_outputs(defs: list[dict]):
    """Write generated .py and .js files."""
    for d in defs:
        rtype = d["runtime"]
        handler = d.get("handler", {})
        kind = handler.get("kind", "delegate")
        cat_map = {"extension": "extension", "backend": "backend", "emitter": "flow"}
        sub_dir = cat_map.get(rtype, rtype)

        # Python handler — only generate for delegate; custom/backend are hand-written
        py_code = generate_py(d)
        py_path = HANDLERS_DIR / sub_dir / f"{d['type']}.py"
        os.makedirs(py_path.parent, exist_ok=True)

        if kind == "delegate":
            if py_path.exists():
                print(f"  KEEP {py_path} (exists)")
            else:
                py_path.write_text(py_code, encoding="utf-8")
                print(f"  GEN  {py_path}")
        else:
            print(f"  SKIP {py_path} ({kind} — hand-written)")
        # ... JS part
        if rtype == "extension":
            js_code = generate_js(d)
            js_path = EXT_JS_DIR / f"{d['type']}.js"
            os.makedirs(js_path.parent, exist_ok=True)
            if kind == "delegate":
                if js_path.exists():
                    print(f"  KEEP {js_path} (exists)")
                else:
                    js_path.write_text(js_code, encoding="utf-8")
                    print(f"  GEN  {js_path}")
            else:
                print(f"  SKIP {js_path} ({kind} — hand-written)")


def main():
    defs = load_definitions()
    if not defs:
        print(f"No command definitions found in {COMMANDS_DIR}")
        return

    print(f"Processing {len(defs)} command definitions...")
    write_outputs(defs)
    print("\nDone. Next: python scripts/build_content_js.py")


if __name__ == "__main__":
    main()
