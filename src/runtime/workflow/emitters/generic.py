"""Generic fallback emitters for new-system JSON-defined commands.

Commands defined in commands/*.json can declare a `pythonAction` field. When no
specific emitter is registered for their type, _emit_dispatch falls back to the
generic emitter here, which produces DrissionPage Python code from the action
and parameter schema.
"""
import json
from pathlib import Path

from ._registry import _handler, _loc_call, _py_str


_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_COMMANDS_DIR = _ROOT / "commands"


def _load_definition(type_name: str) -> dict | None:
    fp = _COMMANDS_DIR / f"{type_name}.json"
    if not fp.exists():
        return None
    with open(fp, encoding="utf-8") as f:
        return json.load(f)


@_handler("__generic__")
def _emit_generic(node, extra, depth, prefix, by_parent, lines, element_map=None):
    """Fallback emitter driven by commands/*.json metadata."""
    d = _load_definition(node.cmd)
    if not d:
        # No JSON definition either — leave a TODO marker
        loc = _loc_call(node, extra, element_map)
        lines.append(f"{prefix}# TODO: {node.cmd} -> {loc}")
        return

    python_action = d.get("pythonAction")
    params = {p["name"]: p for p in d.get("params", [])}

    # Element-based generic actions
    if python_action in ("click", "hover", "focus", "submit"):
        call = _loc_call(node, extra, element_map)
        lines.append(f"{prefix}{call}.{python_action}()")
        return

    if python_action == "input":
        call = _loc_call(node, extra, element_map)
        text = extra.get("text", "")
        if extra.get("clearFirst", True):
            lines.append(f"{prefix}{call}.clear()")
        rendered = str(text) + ("\n" if extra.get("pressEnter") else "")
        lines.append(f"{prefix}{call}.input({_py_str(rendered)})")
        return

    if python_action == "wait":
        call = _loc_call(node, extra, element_map)
        timeout = extra.get("timeout", 10)
        lines.append(
            f"{prefix}# wait for element: {call} (timeout={timeout}) — "
            f"new-system generic emitter does not yet implement polling"
        )
        return

    # Backend-style variable / data actions are intentionally not handled here;
    # they should use dedicated emitters (variables.py, output.py, etc.).

    # Unknown / unsupported action
    loc = _loc_call(node, extra, element_map)
    lines.append(
        f"{prefix}# TODO: {node.cmd} pythonAction={python_action!r} is not supported by generic emitter -> {loc}"
    )
