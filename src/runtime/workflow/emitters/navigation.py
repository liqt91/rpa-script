from ._registry import _handler, _py_str, _var_ref


@_handler("openBrowser")
def _emit_openBrowser(node, extra, depth, prefix, by_parent, lines, element_map=None):
    url = extra.get("url") or "about:blank"
    # The Python runner already connects to an existing Chrome via connect_chrome().
    # openBrowser here just means "open a fresh tab"; we cannot switch browsers.
    lines.append(
        f"{prefix}tab = tab.new_tab({_py_str(url)})  # openBrowser"
    )


@_handler("navigate")
def _emit_navigate(node, extra, depth, prefix, by_parent, lines, element_map=None):
    url = extra.get("url")
    wait = extra.get("waitLoad", True)
    timeout = extra.get("timeout", 30)
    if wait:
        lines.append(f"{prefix}tab.get({_py_str(url)})")
    else:
        lines.append(f"{prefix}tab.get({_py_str(url)}, go_timeout={timeout})")


@_handler("newTab")
def _emit_newTab(node, extra, depth, prefix, by_parent, lines, element_map=None):
    url = extra.get("url")
    if url:
        lines.append(f"{prefix}tab.new_tab({_py_str(url)})")
    else:
        lines.append(f"{prefix}tab.new_tab()")


@_handler("closeBrowser")
def _emit_closeBrowser(node, extra, depth, prefix, by_parent, lines, element_map=None):
    window_id = extra.get("windowId")
    if window_id:
        lines.append(f"{prefix}tab.browser.close_window({window_id})")
    else:
        lines.append(f"{prefix}tab.browser.close_window()")


@_handler("getCurrentUrl")
def _emit_getCurrentUrl(node, extra, depth, prefix, by_parent, lines, element_map=None):
    var = _var_ref(extra.get("varName", "currentUrl"))
    lines.append(f"{prefix}{var} = tab.url")
