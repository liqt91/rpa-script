from ._registry import _handler, _loc_call_by_name


_FIND_SCROLLABLE_JS = """function isScrollable(el) {
  if (!el || el.nodeType !== 1) return false;
  const s = getComputedStyle(el);
  const oy = s.overflowY, o = s.overflow;
  const canOverflow = oy === 'auto' || oy === 'scroll' || o === 'auto' || o === 'scroll';
  return canOverflow && el.scrollHeight > el.clientHeight + 1;
}
function findLargestScrollable() {
  const all = document.querySelectorAll('*');
  let best = null, bestDiff = 0;
  for (const el of all) {
    if (isScrollable(el)) {
      const diff = el.scrollHeight - el.clientHeight;
      if (diff > bestDiff) { bestDiff = diff; best = el; }
    }
  }
  return best;
}
function findScrollable(el) {
  let cur = el;
  while (cur && cur !== document.body && cur !== document.documentElement) {
    if (isScrollable(cur)) return cur;
    cur = cur.parentElement;
  }
  if (isScrollable(document.documentElement)) return document.documentElement;
  if (isScrollable(document.body)) return document.body;
  return findLargestScrollable() || el;
}
var scrollEl = findScrollable(this);
"""


def _element_scroll_call(element_name, extra, element_map):
    """Build a Python expression that resolves the target element, or None for page scroll."""
    if not element_name:
        return None
    call = _loc_call_by_name(element_name, extra, element_map)
    return call if call and call != "tab" else None


def _scroll_target_expr(lookup_scrollable: bool) -> str:
    """Return JS prefix that resolves the scroll target element."""
    if lookup_scrollable:
        return _FIND_SCROLLABLE_JS + "\n"
    return "var scrollEl = this;\n"


@_handler("scrollToBottom")
def _emit_scrollToBottom(node, extra, depth, prefix, by_parent, lines, element_map=None):
    ele = _element_scroll_call(node.element_name, extra, element_map)
    if ele:
        lines.append(f"{prefix}_ele = {ele}")
        target_expr = _scroll_target_expr(extra.get("lookupScrollable", False))
        lines.append(f"{prefix}_ele.run_js({target_expr!r} + 'scrollEl.scrollTop = scrollEl.scrollHeight')")
    else:
        lines.append(f"{prefix}tab.scroll.to_bottom()")


@_handler("scrollToTop")
def _emit_scrollToTop(node, extra, depth, prefix, by_parent, lines, element_map=None):
    ele = _element_scroll_call(node.element_name, extra, element_map)
    if ele:
        lines.append(f"{prefix}_ele = {ele}")
        target_expr = _scroll_target_expr(extra.get("lookupScrollable", False))
        lines.append(f"{prefix}_ele.run_js({target_expr!r} + 'scrollEl.scrollTop = 0')")
    else:
        lines.append(f"{prefix}tab.scroll.to_top()")


@_handler("scrollOneScreen")
def _emit_scrollOneScreen(node, extra, depth, prefix, by_parent, lines, element_map=None):
    ele = _element_scroll_call(node.element_name, extra, element_map)
    if ele:
        lines.append(f"{prefix}_ele = {ele}")
        target_expr = _scroll_target_expr(extra.get("lookupScrollable", False))
        lines.append(f"{prefix}_ele.run_js({target_expr!r} + 'scrollEl.scrollTop += scrollEl.clientHeight')")
    else:
        lines.append(f"{prefix}tab.scroll.by(0, tab.rect.size[1])")


@_handler("scrollBy")
def _emit_scrollBy(node, extra, depth, prefix, by_parent, lines, element_map=None):
    x = extra.get("x", 0)
    y = extra.get("y", 500)
    ele = _element_scroll_call(node.element_name, extra, element_map)
    if ele:
        lines.append(f"{prefix}_ele = {ele}")
        target_expr = _scroll_target_expr(extra.get("lookupScrollable", False))
        lines.append(f"{prefix}_ele.run_js({target_expr!r} + 'scrollEl.scrollBy({x}, {y})')")
    else:
        lines.append(f"{prefix}tab.scroll.by({x}, {y})")
