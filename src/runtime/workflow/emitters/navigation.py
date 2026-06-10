from ._registry import _handler, _loc_str, _var_ref, _py_str


@_handler("openBrowser")
def _emit_openBrowser(node, extra, depth, prefix, by_parent, lines, element_map=None):
    browser = extra.get("browserType", "chrome")
    url = extra.get("url")
    state = extra.get("windowState", "normal")
    lines.append(f"{prefix}tab = page.new_tab({{'browser': {browser!r}, 'url': {_py_str(url or 'about:blank')}, 'state': {state!r}}})  # openBrowser")


@_handler("navigate")
def _emit_navigate(node, extra, depth, prefix, by_parent, lines, element_map=None):
    url = extra.get("url")
    wait = extra.get("waitLoad", True)
    timeout = extra.get("timeout", 30)
    if wait:
        lines.append(f"{prefix}tab.get({_py_str(url)})")
    else:
        lines.append(f"{prefix}tab.get({_py_str(url)}, go_timeout={timeout})")


@_handler("goBack")
def _emit_goBack(node, extra, depth, prefix, by_parent, lines, element_map=None):
    lines.append(f"{prefix}tab.back()")


@_handler("goForward")
def _emit_goForward(node, extra, depth, prefix, by_parent, lines, element_map=None):
    lines.append(f"{prefix}tab.forward()")


@_handler("refresh")
def _emit_refresh(node, extra, depth, prefix, by_parent, lines, element_map=None):
    if extra.get("hardReload"):
        lines.append(f"{prefix}tab.refresh(ignore_cache=True)")
    else:
        lines.append(f"{prefix}tab.refresh()")


@_handler("newTab")
def _emit_newTab(node, extra, depth, prefix, by_parent, lines, element_map=None):
    url = extra.get("url")
    if url:
        lines.append(f"{prefix}tab.new_tab({_py_str(url)})")
    else:
        lines.append(f"{prefix}tab.new_tab()")


@_handler("closeTab")
def _emit_closeTab(node, extra, depth, prefix, by_parent, lines, element_map=None):
    lines.append(f"{prefix}tab.close_tabs(tab)")


@_handler("closeBrowser")
def _emit_closeBrowser(node, extra, depth, prefix, by_parent, lines, element_map=None):
    window_id = extra.get("windowId")
    if window_id:
        lines.append(f"{prefix}tab.browser.close_window({window_id})")
    else:
        lines.append(f"{prefix}tab.browser.close_window()")


@_handler("switchTab")
def _emit_switchTab(node, extra, depth, prefix, by_parent, lines, element_map=None):
    by = extra.get("by", "index")
    value = extra.get("value", "")
    if by == "index":
        lines.append(f"{prefix}tab.to_tab({value})")
    elif by == "url":
        lines.append(f"{prefix}tab.to_tab(url={_py_str(value)})")
    elif by == "title":
        lines.append(f"{prefix}tab.to_tab(title={_py_str(value)})")


@_handler("switchToFrame")
def _emit_switchToFrame(node, extra, depth, prefix, by_parent, lines, element_map=None):
    loc = _loc_str(node, element_map)
    lines.append(f"{prefix}tab.to_frame({_py_str(loc)})")


@_handler("switchToMain")
def _emit_switchToMain(node, extra, depth, prefix, by_parent, lines, element_map=None):
    lines.append(f"{prefix}tab.to_main()")


@_handler("getCurrentUrl")
def _emit_getCurrentUrl(node, extra, depth, prefix, by_parent, lines, element_map=None):
    var = _var_ref(extra.get("varName", "currentUrl"))
    lines.append(f"{prefix}{var} = tab.url")


@_handler("getPageTitle")
def _emit_getPageTitle(node, extra, depth, prefix, by_parent, lines, element_map=None):
    var = _var_ref(extra.get("varName", "pageTitle"))
    lines.append(f"{prefix}{var} = tab.title")
