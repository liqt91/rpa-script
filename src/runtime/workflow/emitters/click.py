from ._registry import _handler, _loc_call, _var_ref


@_handler("click")
def _emit_click(node, extra, depth, prefix, by_parent, lines, element_map=None):
    call = _loc_call(node, extra, element_map)
    if extra.get("forceJs"):
        lines.append(f"{prefix}{call}.click(by_js=True)")
    else:
        lines.append(f"{prefix}{call}.click()")


@_handler("clickCurrentLoopItem")
def _emit_clickCurrentLoopItem(node, extra, depth, prefix, by_parent, lines, element_map=None):
    item_var = _var_ref(extra.get("itemVar", "item"))
    if extra.get("forceJs"):
        lines.append(f"{prefix}{item_var}.click(by_js=True)")
    else:
        lines.append(f"{prefix}{item_var}.click()")


@_handler("hover")
def _emit_hover(node, extra, depth, prefix, by_parent, lines, element_map=None):
    call = _loc_call(node, extra, element_map)
    lines.append(f"{prefix}{call}.hover()")


@_handler("unhover")
def _emit_unhover(node, extra, depth, prefix, by_parent, lines, element_map=None):
    call = _loc_call(node, extra, element_map)
    lines.append(f"{prefix}{call}.hover.off()")
