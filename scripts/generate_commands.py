"""
Generate handler .py and .js files from command definition JSON files.

Usage: python scripts/generate_commands.py

JSON format (commands/<type>.json):
{
  "type": "clickElement",
  "label": "点击元素",
  "runtime": "extension",        // extension | backend | control
  "params": [...],
  "handler": {
    "kind": "extension",         // extension | backend | control
    "function": "doClick"        // extension: JS function name to delegate to
    "source": "path/to/impl"     // extension/backend: path to hand-written impl
  }
}

Three command types (matching src/runtime/commands/ subdirectories):
  extension:  Python stub + JS handler. function=delegate, source=custom JS.
  backend:    Python handler with execute(). AI/hand-written, skipped here.
  control:    Python flow-control handler. AI/hand-written, skipped here.

Output:
  extension:  src/runtime/commands/extension_commands/<type>.py
              extension/handlers/<type>.js
  backend:    src/runtime/commands/backend_commands/<type>.py
  control:    src/runtime/commands/control_commands/<type>.py
"""

import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMANDS_DIR = ROOT / "commands"
HANDLERS_DIR = ROOT / "src" / "runtime" / "workflow" / "handlers"
EXT_DOM_DIR = ROOT / "extension" / "dom_handlers"
EXT_DOM_NEW_DIR = ROOT / "extension" / "dom_handlers_new"


def load_definitions() -> list[dict]:
    defs = []
    for fp in sorted(COMMANDS_DIR.glob("*.json")):
        with open(fp, encoding="utf-8") as f:
            d = json.load(f)
            d["_file"] = fp.stem
            defs.append(d)
    return defs


def _py_literal(value) -> str:
    """Render a JSON-like value as valid Python literal."""
    if isinstance(value, bool):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def param_to_py(p: dict) -> str:
    """Convert a param dict to a Param(...) constructor string."""
    parts = [f'"{p["name"]}"', f'"{p.get("label", "")}"', f'"{p.get("type", "text")}"']
    if p.get("required"):
        parts.append("required=True")
    if p.get("default") is not None:
        parts.append(f"default={_py_literal(p['default'])}")
    if p.get("options"):
        opts = json.dumps(p["options"], ensure_ascii=False)
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


def _category(d: dict) -> str:
    """Resolve category from either 'category' (string) or 'categories' (list)."""
    cat = d.get("category", "")
    if not cat:
        cats = d.get("categories", [])
        if cats:
            cat = cats[0]
    return cat


def generate_py(d: dict) -> str:
    """Generate the Python handler declaration file."""
    rtype = d["runtime"]
    params = d.get("params", [])
    handler = d.get("handler", {})
    category = _category(d)

    # Build class name
    class_name = f"{d['cmd'][0].upper()}{d['cmd'][1:]}Handler"

    # Build params list (8-space indent for class body)
    param_lines = []
    for p in params:
        param_lines.append(f"        {param_to_py(p)},")

    lines = [
        f'"""Command: {d["label"]}"""',
        "from src.runtime.workflow.handlers.registry import register_handler, Param",
        "",
        f'@register_handler(cmd="{d["cmd"]}", label="{d["label"]}",',
        f'    category="{category}", runtime="{rtype}",',
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

    # Backend/control handlers are hand-written or AI-generated — nothing extra to generate
    if handler.get("kind") in ("backend", "control"):
        source = handler.get("source", "")
        if source:
            lines.append("")
            lines.append(f"    # Implementation: {source}")

    return "\n".join(lines)


def generate_js(d: dict) -> str:
    """Generate the JS handler for extension commands.

    - function given → delegate: one-liner forwarding to a named JS function.
    - source given    → custom: read JS from the referenced source file.
    - neither         → TODO stub.
    """
    handler = d.get("handler", {})
    kind = handler.get("kind", "")

    if kind != "extension":
        return ""

    func = handler.get("function", "")
    source = handler.get("source", "")

    if func:
        return f"\nregisterHandler('{d['cmd']}', async (args) => {func}(args));\n"

    if source:
        src_path = ROOT / source
        if src_path.exists():
            return src_path.read_text(encoding="utf-8")
        # Source file not found — generate a stub
        return (
            f"\nregisterHandler('{d['cmd']}', async function handler(args) {{\n"
            f"  // Source file not found: {source}\n"
            f"  return {{ ok: true }};\n"
            f"}});\n"
        )

    # Neither function nor source — generate TODO stub
    return (
        f"\nregisterHandler('{d['cmd']}', async function handler(args) {{\n"
        f"  // TODO: implement {d['label']}\n"
        f"  return {{ ok: true }};\n"
        f"}});\n"
    )


def _choose_output_dirs(d: dict) -> tuple[Path, Path]:
    """Return (python_dir, js_dir) for a definition.
    Always outputs to new-system paths.
    """
    rtype = d["runtime"]
    py_dir = ROOT / "src" / "runtime" / "commands" / f"{rtype}_commands"
    js_dir = EXT_DOM_NEW_DIR
    return py_dir, js_dir


def write_outputs(defs: list[dict]):
    """Write generated .py and .js files."""
    for d in defs:
        handler = d.get("handler", {})
        kind = handler.get("kind", "")
        py_dir, js_dir = _choose_output_dirs(d)

        # Python handler — extension generates stub; backend/control are hand-written
        py_code = generate_py(d)
        py_path = py_dir / f"{d['cmd']}.py"
        os.makedirs(py_path.parent, exist_ok=True)

        if kind in ("", "extension") and d["runtime"] != "control":
            # Always regenerate extension stubs; control commands are hand-written
            py_path.write_text(py_code, encoding="utf-8")
            print(f"  GEN  {py_path}")
        else:
            print(f"  SKIP {py_path} ({kind or d['runtime']} — hand-written)")

        # JS part — only for extension commands
        # Background handlers (source in background_handlers/) are compiled
        # by build_background_js.py — skip DOM handler generation.
        if d["runtime"] == "extension":
            source = handler.get("source", "")
            if "background_handlers" in source:
                print(f"  SKIP JS (background handler: {source})")
            else:
                js_code = generate_js(d)
                js_path = js_dir / f"{d['cmd']}.js"
                os.makedirs(js_path.parent, exist_ok=True)
                if js_path.exists():
                    print(f"  KEEP {js_path} (exists)")
                else:
                    js_path.write_text(js_code, encoding="utf-8")
                    print(f"  GEN  {js_path}")


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
