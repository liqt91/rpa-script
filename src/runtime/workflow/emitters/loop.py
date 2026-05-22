import json
from ._registry import _handler, _emit_dispatch, _loc_call, _var_ref


@_handler("forEachElement")
def _emit_forEachElement(node, extra, depth, prefix, by_parent, lines):
    call = _loc_call(node, extra)
    item_var = _var_ref(extra.get("itemVar", "item"))
    idx_var = _var_ref(extra.get("indexVar", "index"))
    lines.append(f"{prefix}for {idx_var}, {item_var} in enumerate({call}):")
    for child in by_parent.get(node.id, []):
        _emit_dispatch(child, json.loads(child.extra) if child.extra else {}, depth + 1, by_parent, lines)


@_handler("forRange")
def _emit_forRange(node, extra, depth, prefix, by_parent, lines):
    start = extra.get("start", 0)
    end = extra.get("end", 10)
    step = extra.get("step", 1)
    var = _var_ref(extra.get("varName", "i"))
    lines.append(f"{prefix}for {var} in range({start}, {end}, {step}):")
    for child in by_parent.get(node.id, []):
        _emit_dispatch(child, json.loads(child.extra) if child.extra else {}, depth + 1, by_parent, lines)


@_handler("forList")
def _emit_forList(node, extra, depth, prefix, by_parent, lines):
    list_var = _var_ref(extra.get("listVar", "items"))
    item_var = _var_ref(extra.get("itemVar", "item"))
    idx_var = _var_ref(extra.get("indexVar", "index"))
    lines.append(f"{prefix}for {idx_var}, {item_var} in enumerate({list_var}):")
    for child in by_parent.get(node.id, []):
        _emit_dispatch(child, json.loads(child.extra) if child.extra else {}, depth + 1, by_parent, lines)


@_handler("whileCondition")
def _emit_whileCondition(node, extra, depth, prefix, by_parent, lines):
    cond_type = extra.get("conditionType", "elementExists")
    max_iter = extra.get("maxIterations", 100)

    lines.append(f"{prefix}_iter = 0")
    lines.append(f"{prefix}while _iter < {max_iter}:")

    ip = "    " * (depth + 1)
    if cond_type == "elementExists":
        loc = (extra.get("locator") or "").replace("'", "\\'")
        lines.append(f"{ip}if not tab.ele('{loc}'):")
        lines.append(f"{ip}    break")
    elif cond_type == "elementNotExists":
        loc = (extra.get("locator") or "").replace("'", "\\'")
        lines.append(f"{ip}if tab.ele('{loc}'):")
        lines.append(f"{ip}    break")
    elif cond_type == "urlContains":
        pattern = (extra.get("urlPattern") or "").replace("'", "\\'")
        lines.append(f"{ip}if '{pattern}' in tab.url:")
        lines.append(f"{ip}    break")
    elif cond_type == "varEquals":
        var = _var_ref(extra.get("varName", "x"))
        val = (extra.get("varValue") or "").replace("'", "\\'")
        lines.append(f"{ip}if {var} == '{val}':")
        lines.append(f"{ip}    break")

    for child in by_parent.get(node.id, []):
        _emit_dispatch(child, json.loads(child.extra) if child.extra else {}, depth + 1, by_parent, lines)

    lines.append(f"{ip}_iter += 1")


@_handler("break")
def _emit_break(node, extra, depth, prefix, by_parent, lines):
    lines.append(f"{prefix}break")


@_handler("continue")
def _emit_continue(node, extra, depth, prefix, by_parent, lines):
    lines.append(f"{prefix}continue")


@_handler("endFor")
def _emit_endFor(node, extra, depth, prefix, by_parent, lines):
    pass  # Structural marker
