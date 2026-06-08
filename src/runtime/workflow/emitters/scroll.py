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


@_handler("scrollIntoView")
def _emit_scrollIntoView(node, extra, depth, prefix, by_parent, lines, element_map=None):
    call = _loc_call(node, extra, element_map)
    block = extra.get("block", "center")
    lines.append(f"{prefix}{call}.scroll.into_view(align={_py_str(block)})")


@_handler("scrollBy")
def _emit_scrollBy(node, extra, depth, prefix, by_parent, lines, element_map=None):
    x = extra.get("x", 0)
    y = extra.get("y", 500)
    lines.append(f"{prefix}tab.scroll.by({x}, {y})")


@_handler("infiniteScroll")
def _emit_infiniteScroll(node, extra, depth, prefix, by_parent, lines, element_map=None):
    end_marker = extra.get("endMarker")
    max_scrolls = extra.get("maxScrolls", 50)
    interval = extra.get("interval", 2.0)
    click_more = extra.get("clickMoreSelector")

    lines.append(f"{prefix}# Infinite scroll")
    lines.append(f"{prefix}_scroll_count = 0")
    lines.append(f"{prefix}while _scroll_count < {max_scrolls}:")
    lines.append(f"{prefix}    _body_text = tab.ele('body').text")
    if end_marker:
        lines.append(f"{prefix}    if {_py_str(end_marker)} in _body_text:")
        lines.append(f"{prefix}        break")
    if click_more:
        lines.append(f"{prefix}    for _more in tab.eles({_py_str(click_more)}):")
        lines.append(f"{prefix}        try: _more.click()")
        lines.append(f"{prefix}        except: pass")
    lines.append(f"{prefix}    tab.scroll.by(0, 800)")
    lines.append(f"{prefix}    tab.wait({interval})")
    lines.append(f"{prefix}    _scroll_count += 1")
