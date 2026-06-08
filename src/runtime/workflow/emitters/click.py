from ._registry import _handler, _loc_call, _loc_str, _py_str


@_handler("click")
def _emit_click(node, extra, depth, prefix, by_parent, lines, element_map=None):
    call = _loc_call(node, extra, element_map)
    if extra.get("forceJs"):
        lines.append(f"{prefix}{call}.click(by_js=True)")
    else:
        lines.append(f"{prefix}{call}.click()")


@_handler("doubleClick")
def _emit_doubleClick(node, extra, depth, prefix, by_parent, lines, element_map=None):
    call = _loc_call(node, extra, element_map)
    lines.append(f"{prefix}{call}.click(times=2)")


@_handler("rightClick")
def _emit_rightClick(node, extra, depth, prefix, by_parent, lines, element_map=None):
    call = _loc_call(node, extra, element_map)
    lines.append(f"{prefix}{call}.click(button='right')")


@_handler("clickByIndex")
def _emit_clickByIndex(node, extra, depth, prefix, by_parent, lines, element_map=None):
    loc = _loc_str(node, element_map)
    idx = extra.get("index", 0)
    lines.append(f"{prefix}tab.eles({_py_str(loc)})[{idx}].click()")


@_handler("clickIfExists")
def _emit_clickIfExists(node, extra, depth, prefix, by_parent, lines, element_map=None):
    call = _loc_call(node, extra, element_map)
    lines.append(f"{prefix}_el = {call}")
    lines.append(f"{prefix}if _el:")
    lines.append(f"{prefix}    _el.click()")


@_handler("hover")
def _emit_hover(node, extra, depth, prefix, by_parent, lines, element_map=None):
    call = _loc_call(node, extra, element_map)
    lines.append(f"{prefix}{call}.hover()")
