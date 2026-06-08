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


@_handler("waitForElementHide")
def _emit_waitForElementHide(node, extra, depth, prefix, by_parent, lines, element_map=None):
    loc = _loc_str(node, element_map)
    timeout = extra.get("timeout", 10)
    lines.append(f"{prefix}tab.wait.ele_hidden({_py_str(loc)}, timeout={timeout})")


@_handler("waitForText")
def _emit_waitForText(node, extra, depth, prefix, by_parent, lines, element_map=None):
    loc = _loc_str(node, element_map)
    text = extra.get("text")
    timeout = extra.get("timeout", 10)
    lines.append(f"{prefix}tab.wait.ele_text({_py_str(loc)}, {_py_str(text)}, timeout={timeout})")


@_handler("waitForUrl")
def _emit_waitForUrl(node, extra, depth, prefix, by_parent, lines, element_map=None):
    pattern = extra.get("urlPattern")
    timeout = extra.get("timeout", 10)
    lines.append(f"{prefix}tab.wait.url_change({_py_str(pattern)}, timeout={timeout})")


@_handler("waitForLoad")
def _emit_waitForLoad(node, extra, depth, prefix, by_parent, lines, element_map=None):
    timeout = extra.get("timeout", 30)
    lines.append(f"{prefix}tab.wait.load_start(timeout={timeout})")
