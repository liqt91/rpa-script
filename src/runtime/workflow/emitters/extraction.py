from ._registry import _handler, _loc_call, _var_ref, _py_str


@_handler("getText")
def _emit_getText(node, extra, depth, prefix, by_parent, lines, element_map=None):
    call = _loc_call(node, extra, element_map)
    var = _var_ref(extra.get("varName", "text"))
    lines.append(f"{prefix}{var} = {call}.text")


@_handler("getAttr")
def _emit_getAttr(node, extra, depth, prefix, by_parent, lines, element_map=None):
    call = _loc_call(node, extra, element_map)
    attr = extra.get("attrName")
    var = _var_ref(extra.get("varName", "attrVal"))
    lines.append(f"{prefix}{var} = {call}.attr({_py_str(attr)})")


@_handler("getHtml")
def _emit_getHtml(node, extra, depth, prefix, by_parent, lines, element_map=None):
    call = _loc_call(node, extra, element_map)
    mode = extra.get("mode", "inner")
    var = _var_ref(extra.get("varName", "html"))
    if mode == "outer":
        lines.append(f"{prefix}{var} = {call}.html")
    else:
        lines.append(f"{prefix}{var} = {call}.inner_html")


@_handler("getValue")
def _emit_getValue(node, extra, depth, prefix, by_parent, lines, element_map=None):
    call = _loc_call(node, extra, element_map)
    var = _var_ref(extra.get("varName", "value"))
    lines.append(f"{prefix}{var} = {call}.value")
