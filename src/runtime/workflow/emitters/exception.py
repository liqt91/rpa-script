from ._registry import _handler, _var_ref, _emit_children


@_handler("try")
def _emit_try(node, extra, depth, prefix, by_parent, lines):
    lines.append(f"{prefix}try:")
    _emit_children(node, depth, by_parent, lines)


@_handler("catch")
def _emit_catch(node, extra, depth, prefix, by_parent, lines):
    err_var = _var_ref(extra.get("errorVar", "error"))
    lines.append(f"{prefix}except Exception as {err_var}:")
    _emit_children(node, depth, by_parent, lines)


@_handler("endTry")
def _emit_endTry(node, extra, depth, prefix, by_parent, lines):
    pass  # Structural marker
