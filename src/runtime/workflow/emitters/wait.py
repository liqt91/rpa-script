from ._registry import _handler, _loc_str, _py_str


@_handler("sleep")
def _emit_sleep(node, extra, depth, prefix, by_parent, lines, element_map=None):
    sec = extra.get("seconds", 1.0)
    lines.append(f"{prefix}tab.wait({sec})")


@_handler("waitForElement")
def _emit_waitForElement(node, extra, depth, prefix, by_parent, lines, element_map=None):
    loc = _loc_str(node, element_map)
    timeout = extra.get("timeout", 10)
    lines.append(f"{prefix}tab.wait.ele_displayed({_py_str(loc)}, timeout={timeout})")
