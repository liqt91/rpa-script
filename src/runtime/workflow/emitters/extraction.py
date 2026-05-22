from ._registry import _handler, _loc_call, _var_ref, _py_str


@_handler("getText")
def _emit_getText(node, extra, depth, prefix, by_parent, lines):
    call = _loc_call(node, extra)
    var = _var_ref(extra.get("varName", "text"))
    lines.append(f"{prefix}{var} = {call}.text")


@_handler("getAttr")
def _emit_getAttr(node, extra, depth, prefix, by_parent, lines):
    call = _loc_call(node, extra)
    attr = extra.get("attrName")
    var = _var_ref(extra.get("varName", "attrVal"))
    lines.append(f"{prefix}{var} = {call}.attr({_py_str(attr)})")


@_handler("getHtml")
def _emit_getHtml(node, extra, depth, prefix, by_parent, lines):
    call = _loc_call(node, extra)
    mode = extra.get("mode", "inner")
    var = _var_ref(extra.get("varName", "html"))
    if mode == "outer":
        lines.append(f"{prefix}{var} = {call}.html")
    else:
        lines.append(f"{prefix}{var} = {call}.inner_html")


@_handler("getValue")
def _emit_getValue(node, extra, depth, prefix, by_parent, lines):
    call = _loc_call(node, extra)
    var = _var_ref(extra.get("varName", "value"))
    lines.append(f"{prefix}{var} = {call}.value")


@_handler("getElementCount")
def _emit_getElementCount(node, extra, depth, prefix, by_parent, lines):
    call = _loc_call(node, extra)
    var = _var_ref(extra.get("varName", "count"))
    lines.append(f"{prefix}{var} = len({call})")


@_handler("getElementList")
def _emit_getElementList(node, extra, depth, prefix, by_parent, lines):
    loc = node.locator or ""
    var = _var_ref(extra.get("varName", "elements"))
    lines.append(f"{prefix}{var} = tab.eles({_py_str(loc)})")
