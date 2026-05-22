import json
from ._registry import _handler, _emit_dispatch, _var_ref


@_handler("try")
def _emit_try(node, extra, depth, prefix, by_parent, lines):
    lines.append(f"{prefix}try:")
    for child in by_parent.get(node.id, []):
        _emit_dispatch(child, json.loads(child.extra) if child.extra else {}, depth + 1, by_parent, lines)


@_handler("catch")
def _emit_catch(node, extra, depth, prefix, by_parent, lines):
    err_var = _var_ref(extra.get("errorVar", "error"))
    lines.append(f"{prefix}except Exception as {err_var}:")
    for child in by_parent.get(node.id, []):
        _emit_dispatch(child, json.loads(child.extra) if child.extra else {}, depth + 1, by_parent, lines)


@_handler("endTry")
def _emit_endTry(node, extra, depth, prefix, by_parent, lines):
    pass  # Structural marker
