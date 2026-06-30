import json
from ._registry import _handler, _loc_call, _loc_str, _var_ref, _py_str, _emit_children, _emit_dispatch


@_handler("forEachElement")
def _emit_forEachElement(node, extra, depth, prefix, by_parent, lines, element_map=None):
    call = _loc_call(node, extra, element_map)
    item_var = _var_ref(extra.get("itemVar", "item"))
    idx_var = _var_ref(extra.get("indexVar", "index"))
    lines.append(f"{prefix}for {idx_var}, {item_var} in enumerate({call}):")
    _emit_children(node, depth, by_parent, lines, element_map)


@_handler("forRange")
def _emit_forRange(node, extra, depth, prefix, by_parent, lines, element_map=None):
    start = extra.get("start", 0)
    end = extra.get("end", 10)
    step = extra.get("step", 1)
    var = _var_ref(extra.get("varName", "i"))
    lines.append(f"{prefix}for {var} in range({start}, {end}, {step}):")
    _emit_children(node, depth, by_parent, lines, element_map)


@_handler("forList")
def _emit_forList(node, extra, depth, prefix, by_parent, lines, element_map=None):
    list_var = _var_ref(extra.get("listVar", "items"))
    item_var = _var_ref(extra.get("itemVar", "item"))
    idx_var = _var_ref(extra.get("indexVar", "index"))
    lines.append(f"{prefix}for {idx_var}, {item_var} in enumerate({list_var}):")
    _emit_children(node, depth, by_parent, lines, element_map)


@_handler("forEachTableRow")
def _emit_forEachTableRow(node, extra, depth, prefix, by_parent, lines, element_map=None):
    item_var = _var_ref(extra.get("itemVar", "row"))
    idx_var = _var_ref(extra.get("indexVar", "index"))
    lines.append(f"{prefix}for {idx_var}, {item_var} in enumerate(_table_data[\"rows\"]):")
    _emit_children(node, depth, by_parent, lines, element_map)


@_handler("whileCondition")
def _emit_whileCondition(node, extra, depth, prefix, by_parent, lines, element_map=None):
    cond_type = extra.get("conditionType", "elementExists")
    max_iter = extra.get("maxIterations", 100)
    execute_first = extra.get("executeFirst", False)

    lines.append(f"{prefix}_iter = 0")
    lines.append(f"{prefix}while _iter < {max_iter}:")

    ip = "    " * (depth + 1)

    def _condition_check():
        check_lines = []
        loc = _loc_str(node, element_map)
        if cond_type == "elementExists":
            check_lines.append(f"{ip}if not tab.ele({_py_str(loc)}):")
            check_lines.append(f"{ip}    break")
        elif cond_type == "elementNotExists":
            check_lines.append(f"{ip}if tab.ele({_py_str(loc)}):")
            check_lines.append(f"{ip}    break")
        elif cond_type == "urlContains":
            pattern = extra.get("urlPattern")
            check_lines.append(f"{ip}if {_py_str(pattern)} in tab.url:")
            check_lines.append(f"{ip}    break")
        elif cond_type == "varEquals":
            var = _var_ref(extra.get("varName", "x"))
            val = extra.get("varValue")
            check_lines.append(f"{ip}if {var} == {_py_str(val)}:")
            check_lines.append(f"{ip}    break")
        return check_lines

    if not execute_first:
        lines.extend(_condition_check())

    for child in by_parent.get(node.id, []):
        extra_c = json.loads(child.extra) if child.extra else {}
        _emit_dispatch(child, extra_c, depth + 1, by_parent, lines, element_map)

    lines.append(f"{ip}_iter += 1")

    if execute_first:
        lines.extend(_condition_check())


@_handler("break")
def _emit_break(node, extra, depth, prefix, by_parent, lines, element_map=None):
    lines.append(f"{prefix}break")


@_handler("continue")
def _emit_continue(node, extra, depth, prefix, by_parent, lines, element_map=None):
    lines.append(f"{prefix}continue")


@_handler("endFor")
def _emit_endFor(node, extra, depth, prefix, by_parent, lines, element_map=None):
    pass  # Structural marker
