import json
from ._registry import _handler, _emit_dispatch, _loc_call, _var_ref


@_handler("ifElementExists")
def _emit_ifElementExists(node, extra, depth, prefix, by_parent, lines):
    call = _loc_call(node, extra)
    lines.append(f"{prefix}if {call}:")
    for child in by_parent.get(node.id, []):
        _emit_dispatch(child, json.loads(child.extra) if child.extra else {}, depth + 1, by_parent, lines)


@_handler("ifElementNotExists")
def _emit_ifElementNotExists(node, extra, depth, prefix, by_parent, lines):
    call = _loc_call(node, extra)
    lines.append(f"{prefix}if not {call}:")
    for child in by_parent.get(node.id, []):
        _emit_dispatch(child, json.loads(child.extra) if child.extra else {}, depth + 1, by_parent, lines)


@_handler("ifElementVisible")
def _emit_ifElementVisible(node, extra, depth, prefix, by_parent, lines):
    call = _loc_call(node, extra)
    lines.append(f"{prefix}if {call}.states.is_displayed:")
    for child in by_parent.get(node.id, []):
        _emit_dispatch(child, json.loads(child.extra) if child.extra else {}, depth + 1, by_parent, lines)


@_handler("ifTextContains")
def _emit_ifTextContains(node, extra, depth, prefix, by_parent, lines):
    call = _loc_call(node, extra)
    text = (extra.get("text") or "").replace("'", "\\'")
    lines.append(f"{prefix}if '{text}' in ({call}.text or ''):")
    for child in by_parent.get(node.id, []):
        _emit_dispatch(child, json.loads(child.extra) if child.extra else {}, depth + 1, by_parent, lines)


@_handler("ifTextEquals")
def _emit_ifTextEquals(node, extra, depth, prefix, by_parent, lines):
    call = _loc_call(node, extra)
    text = (extra.get("text") or "").replace("'", "\\'")
    lines.append(f"{prefix}if ({call}.text or '') == '{text}':")
    for child in by_parent.get(node.id, []):
        _emit_dispatch(child, json.loads(child.extra) if child.extra else {}, depth + 1, by_parent, lines)


@_handler("ifUrlContains")
def _emit_ifUrlContains(node, extra, depth, prefix, by_parent, lines):
    pattern = (extra.get("urlPattern") or "").replace("'", "\\'")
    lines.append(f"{prefix}if '{pattern}' in tab.url:")
    for child in by_parent.get(node.id, []):
        _emit_dispatch(child, json.loads(child.extra) if child.extra else {}, depth + 1, by_parent, lines)


@_handler("ifVarEquals")
def _emit_ifVarEquals(node, extra, depth, prefix, by_parent, lines):
    var = _var_ref(extra.get("varName", "x"))
    value = (extra.get("value") or "").replace("'", "\\'")
    vtype = extra.get("valueType", "string")
    if vtype == "number":
        lines.append(f"{prefix}if {var} == {value}:")
    elif vtype == "bool":
        val = "True" if value.lower() in ("true", "1", "yes") else "False"
        lines.append(f"{prefix}if {var} == {val}:")
    else:
        lines.append(f"{prefix}if {var} == '{value}':")
    for child in by_parent.get(node.id, []):
        _emit_dispatch(child, json.loads(child.extra) if child.extra else {}, depth + 1, by_parent, lines)


@_handler("ifVarGreaterThan")
def _emit_ifVarGreaterThan(node, extra, depth, prefix, by_parent, lines):
    var = _var_ref(extra.get("varName", "x"))
    value = extra.get("value", 0)
    lines.append(f"{prefix}if {var} > {value}:")
    for child in by_parent.get(node.id, []):
        _emit_dispatch(child, json.loads(child.extra) if child.extra else {}, depth + 1, by_parent, lines)


@_handler("else")
def _emit_else(node, extra, depth, prefix, by_parent, lines):
    lines.append(f"{prefix}else:")
    for child in by_parent.get(node.id, []):
        _emit_dispatch(child, json.loads(child.extra) if child.extra else {}, depth + 1, by_parent, lines)


@_handler("endIf")
def _emit_endIf(node, extra, depth, prefix, by_parent, lines):
    pass  # Structural marker, no code
