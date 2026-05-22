from ._registry import _handler


@_handler("sleep")
def _emit_sleep(node, extra, depth, prefix, by_parent, lines):
    sec = extra.get("seconds", 1.0)
    lines.append(f"{prefix}tab.wait({sec})")


@_handler("waitForElement")
def _emit_waitForElement(node, extra, depth, prefix, by_parent, lines):
    loc = (node.locator or "").replace("'", "\\'")
    timeout = extra.get("timeout", 10)
    lines.append(f"{prefix}tab.wait.ele_displayed('{loc}', timeout={timeout})")


@_handler("waitForElementHide")
def _emit_waitForElementHide(node, extra, depth, prefix, by_parent, lines):
    loc = (node.locator or "").replace("'", "\\'")
    timeout = extra.get("timeout", 10)
    lines.append(f"{prefix}tab.wait.ele_hidden('{loc}', timeout={timeout})")


@_handler("waitForText")
def _emit_waitForText(node, extra, depth, prefix, by_parent, lines):
    loc = (node.locator or "").replace("'", "\\'")
    text = (extra.get("text") or "").replace("'", "\\'")
    timeout = extra.get("timeout", 10)
    lines.append(f"{prefix}tab.wait.ele_text('{loc}', '{text}', timeout={timeout})")


@_handler("waitForUrl")
def _emit_waitForUrl(node, extra, depth, prefix, by_parent, lines):
    pattern = (extra.get("urlPattern") or "").replace("'", "\\'")
    timeout = extra.get("timeout", 10)
    lines.append(f"{prefix}tab.wait.url_change('{pattern}', timeout={timeout})")


@_handler("waitForLoad")
def _emit_waitForLoad(node, extra, depth, prefix, by_parent, lines):
    timeout = extra.get("timeout", 30)
    lines.append(f"{prefix}tab.wait.load_start(timeout={timeout})")
