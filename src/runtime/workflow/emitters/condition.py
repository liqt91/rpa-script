from ._registry import _handler, _loc_calls, _loc_str_by_name, _var_ref, _py_str, _emit_children


@_handler("ifElementVisible")
def _emit_ifElementVisible(node, extra, depth, prefix, by_parent, lines, element_map=None):
    op = extra.get("operator", "visible")
    mode = extra.get("visibilityMode", "visible")
    if mode == "any":
        locs = [_loc_str_by_name(node.element_name, element_map)]
        for name in extra.get("element_names") or []:
            if name:
                locs.append(_loc_str_by_name(name, element_map))
        checks = [f"_ele_exists(tab, {_py_str(loc)})" for loc in locs if loc]
        if not checks:
            checks = ["False"]
        if op == "visible":
            cond = " or ".join(checks) if len(checks) > 1 else checks[0]
        else:
            cond = " and ".join(f"not {c}" for c in checks) if len(checks) > 1 else f"not {checks[0]}"
    else:
        calls = _loc_calls(node, extra, element_map)
        if op == "visible":
            cond = (
                " or ".join(f"{c}.states.is_displayed" for c in calls)
                if len(calls) > 1
                else f"{calls[0]}.states.is_displayed"
            )
        else:
            if len(calls) > 1:
                cond = " and ".join(f"not {c}.states.is_displayed" for c in calls)
            else:
                cond = f"not {calls[0]}.states.is_displayed"
    lines.append(f"{prefix}if {cond}:")
    _emit_children(node, depth, by_parent, lines, element_map)


@_handler("ifTextContains")
def _emit_ifTextContains(node, extra, depth, prefix, by_parent, lines, element_map=None):
    calls = _loc_calls(node, extra, element_map)
    call = calls[0]
    text = extra.get("text")
    lines.append(f"{prefix}if {_py_str(text)} in ({call}.text or ''):")
    _emit_children(node, depth, by_parent, lines, element_map)


@_handler("ifTextEquals")
def _emit_ifTextEquals(node, extra, depth, prefix, by_parent, lines, element_map=None):
    calls = _loc_calls(node, extra, element_map)
    call = calls[0]
    text = extra.get("text")
    lines.append(f"{prefix}if ({call}.text or '') == {_py_str(text)}:")
    _emit_children(node, depth, by_parent, lines, element_map)


@_handler("ifVarEquals")
def _emit_ifVarEquals(node, extra, depth, prefix, by_parent, lines, element_map=None):
    var = _var_ref(extra.get("varName", "x"))
    value = extra.get("value")
    vtype = extra.get("valueType", "string")
    if vtype == "number":
        lines.append(f"{prefix}if {var} == {value}:")
    elif vtype == "bool":
        val = "True" if str(value).lower() in ("true", "1", "yes") else "False"
        lines.append(f"{prefix}if {var} == {val}:")
    else:
        lines.append(f"{prefix}if {var} == {_py_str(value)}:")
    _emit_children(node, depth, by_parent, lines, element_map)


@_handler("else")
def _emit_else(node, extra, depth, prefix, by_parent, lines, element_map=None):
    lines.append(f"{prefix}else:")
    _emit_children(node, depth, by_parent, lines, element_map)


@_handler("endIf")
def _emit_endIf(node, extra, depth, prefix, by_parent, lines, element_map=None):
    pass  # Structural marker, no code
