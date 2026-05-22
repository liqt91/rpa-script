from ._registry import _handler, _loc_call, _py_str


@_handler("input")
def _emit_input(node, extra, depth, prefix, by_parent, lines):
    call = _loc_call(node, extra)
    text = extra.get("text")
    if extra.get("clearFirst", True):
        lines.append(f"{prefix}{call}.clear()")
    lines.append(f"{prefix}{call}.input({_py_str(text)})")


@_handler("inputAndPressEnter")
def _emit_inputAndPressEnter(node, extra, depth, prefix, by_parent, lines):
    call = _loc_call(node, extra)
    text = extra.get("text")
    if extra.get("clearFirst", True):
        lines.append(f"{prefix}{call}.clear()")
    lines.append(f"{prefix}{call}.input({_py_str(text)})")
    lines.append(f"{prefix}{call}.input(Keys.ENTER)")


@_handler("clearInput")
def _emit_clearInput(node, extra, depth, prefix, by_parent, lines):
    call = _loc_call(node, extra)
    lines.append(f"{prefix}{call}.clear()")


@_handler("pressKey")
def _emit_pressKey(node, extra, depth, prefix, by_parent, lines):
    key = extra.get("key", "Enter")
    lines.append(f"{prefix}tab.actions.key_down(Keys.{key}).key_up(Keys.{key})")


@_handler("selectOption")
def _emit_selectOption(node, extra, depth, prefix, by_parent, lines):
    call = _loc_call(node, extra)
    by = extra.get("by", "label")
    value = extra.get("value")
    if by == "label":
        lines.append(f"{prefix}{call}.select.by_text({_py_str(value)})")
    elif by == "value":
        lines.append(f"{prefix}{call}.select.by_value({_py_str(value)})")
    elif by == "index":
        lines.append(f"{prefix}{call}.select.by_index({value})")
