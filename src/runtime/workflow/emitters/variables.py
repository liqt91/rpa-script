from ._registry import _handler, _var_ref, _py_str


@_handler("setVar")
def _emit_setVar(node, extra, depth, prefix, by_parent, lines):
    var = _var_ref(extra.get("name", "x"))
    value = extra.get("value", "")
    vtype = extra.get("valueType", "string")
    if vtype == "number":
        lines.append(f"{prefix}{var} = {value}")
    elif vtype == "bool":
        val = "True" if str(value).lower() in ("true", "1", "yes") else "False"
        lines.append(f"{prefix}{var} = {val}")
    elif vtype == "list":
        lines.append(f"{prefix}{var} = []")
    else:
        lines.append(f"{prefix}{var} = {_py_str(value)}")


@_handler("appendToList")
def _emit_appendToList(node, extra, depth, prefix, by_parent, lines):
    list_var = _var_ref(extra.get("listName", "items"))
    value = extra.get("value", "")
    lines.append(f"{prefix}{list_var}.append({_py_str(value)})")


@_handler("stringConcat")
def _emit_stringConcat(node, extra, depth, prefix, by_parent, lines):
    target = _var_ref(extra.get("targetVar", "result"))
    parts = [extra.get("part1", ""), extra.get("part2", ""), extra.get("part3", "")]
    parts = [p for p in parts if p]
    if parts:
        joined = " + ".join(_py_str(p) for p in parts)
        lines.append(f"{prefix}{target} = {joined}")
    else:
        lines.append(f"{prefix}{target} = ''")


@_handler("increment")
def _emit_increment(node, extra, depth, prefix, by_parent, lines):
    var = _var_ref(extra.get("varName", "count"))
    step = extra.get("step", 1)
    lines.append(f"{prefix}{var} += {step}")
