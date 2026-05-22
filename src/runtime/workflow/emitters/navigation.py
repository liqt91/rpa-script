from ._registry import _handler, _loc_call, _var_ref


@_handler("navigate")
def _emit_navigate(node, extra, depth, prefix, by_parent, lines):
    url = (extra.get("url") or "").replace("'", "\\'")
    wait = extra.get("waitLoad", True)
    timeout = extra.get("timeout", 30)
    if wait:
        lines.append(f"{prefix}tab.get('{url}')")
    else:
        lines.append(f"{prefix}tab.get('{url}', go_timeout={timeout})")


@_handler("goBack")
def _emit_goBack(node, extra, depth, prefix, by_parent, lines):
    lines.append(f"{prefix}tab.back()")


@_handler("goForward")
def _emit_goForward(node, extra, depth, prefix, by_parent, lines):
    lines.append(f"{prefix}tab.forward()")


@_handler("refresh")
def _emit_refresh(node, extra, depth, prefix, by_parent, lines):
    if extra.get("hardReload"):
        lines.append(f"{prefix}tab.refresh(ignore_cache=True)")
    else:
        lines.append(f"{prefix}tab.refresh()")


@_handler("newTab")
def _emit_newTab(node, extra, depth, prefix, by_parent, lines):
    url = extra.get("url", "").replace("'", "\\'")
    if url:
        lines.append(f"{prefix}tab.new_tab('{url}')")
    else:
        lines.append(f"{prefix}tab.new_tab()")


@_handler("closeTab")
def _emit_closeTab(node, extra, depth, prefix, by_parent, lines):
    lines.append(f"{prefix}tab.close_tabs(tab)")


@_handler("switchTab")
def _emit_switchTab(node, extra, depth, prefix, by_parent, lines):
    by = extra.get("by", "index")
    value = extra.get("value", "")
    if by == "index":
        lines.append(f"{prefix}tab.to_tab({value})")
    elif by == "url":
        lines.append(f"{prefix}tab.to_tab(url='{value}')")
    elif by == "title":
        lines.append(f"{prefix}tab.to_tab(title='{value}')")


@_handler("switchToFrame")
def _emit_switchToFrame(node, extra, depth, prefix, by_parent, lines):
    loc = (node.locator or "").replace("'", "\\'")
    lines.append(f"{prefix}tab.to_frame('{loc}')")


@_handler("switchToMain")
def _emit_switchToMain(node, extra, depth, prefix, by_parent, lines):
    lines.append(f"{prefix}tab.to_main()")


@_handler("getCurrentUrl")
def _emit_getCurrentUrl(node, extra, depth, prefix, by_parent, lines):
    var = _var_ref(extra.get("varName", "currentUrl"))
    lines.append(f"{prefix}{var} = tab.url")


@_handler("getPageTitle")
def _emit_getPageTitle(node, extra, depth, prefix, by_parent, lines):
    var = _var_ref(extra.get("varName", "pageTitle"))
    lines.append(f"{prefix}{var} = tab.title")
