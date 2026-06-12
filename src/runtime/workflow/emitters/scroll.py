from ._registry import _handler, _loc_call, _py_str


@_handler("scrollToBottom")
def _emit_scrollToBottom(node, extra, depth, prefix, by_parent, lines, element_map=None):
    lines.append(f"{prefix}tab.scroll.to_bottom()")


@_handler("scrollToTop")
def _emit_scrollToTop(node, extra, depth, prefix, by_parent, lines, element_map=None):
    lines.append(f"{prefix}tab.scroll.to_top()")


@_handler("scrollOneScreen")
def _emit_scrollOneScreen(node, extra, depth, prefix, by_parent, lines, element_map=None):
    lines.append(f"{prefix}tab.scroll.by(0, tab.rect.size[1])")


@_handler("scrollBy")
def _emit_scrollBy(node, extra, depth, prefix, by_parent, lines, element_map=None):
    x = extra.get("x", 0)
    y = extra.get("y", 500)
    lines.append(f"{prefix}tab.scroll.by({x}, {y})")


