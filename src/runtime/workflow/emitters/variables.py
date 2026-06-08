from ._registry import _handler, _var_ref, _py_str


@_handler("setVar")
def _emit_setVar(node, extra, depth, prefix, by_parent, lines, element_map=None):
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
def _emit_appendToList(node, extra, depth, prefix, by_parent, lines, element_map=None):
    list_var = _var_ref(extra.get("listName", "items"))
    value = extra.get("value", "")
    lines.append(f"{prefix}{list_var}.append({_py_str(value)})")


@_handler("stringConcat")
def _emit_stringConcat(node, extra, depth, prefix, by_parent, lines, element_map=None):
    target = _var_ref(extra.get("targetVar", "result"))
    parts = [extra.get("part1", ""), extra.get("part2", ""), extra.get("part3", "")]
    parts = [p for p in parts if p]
    if parts:
        joined = " + ".join(_py_str(p) for p in parts)
        lines.append(f"{prefix}{target} = {joined}")
    else:
        lines.append(f"{prefix}{target} = ''")


@_handler("increment")
def _emit_increment(node, extra, depth, prefix, by_parent, lines, element_map=None):
    var = _var_ref(extra.get("varName", "count"))
    step = extra.get("step", 1)
    lines.append(f"{prefix}{var} += {step}")


@_handler("readTableCell")
def _emit_readTableCell(node, extra, depth, prefix, by_parent, lines, element_map=None):
    row = extra.get("rowIndex", 0)
    col = _py_str(extra.get("columnName", ""))
    var = _var_ref(extra.get("varName", "cellValue"))
    lines.append(f"{prefix}{var} = _table_data[\"rows\"][{row}].get({col}, \"\")")


@_handler("writeTableCell")
def _emit_writeTableCell(node, extra, depth, prefix, by_parent, lines, element_map=None):
    row = extra.get("rowIndex", 0)
    col = _py_str(extra.get("columnName", ""))
    value = _py_str(extra.get("value", ""))
    lines.append(f"{prefix}_table_data[\"rows\"][{row}][{col}] = {value}")


@_handler("getTableRowCount")
def _emit_getTableRowCount(node, extra, depth, prefix, by_parent, lines, element_map=None):
    var = _var_ref(extra.get("varName", "rowCount"))
    lines.append(f"{prefix}{var} = len(_table_data[\"rows\"])")


@_handler("writeTableRow")
def _emit_writeTableRow(node, extra, depth, prefix, by_parent, lines, element_map=None):
    mode = extra.get("writeMode", "append")
    row = extra.get("rowIndex", 0)
    data = extra.get("rowData", "{}")
    ip = "    " * depth
    lines.append(f"{ip}_row_raw = {data}")
    _cols = "_table_data.get('columns', [])"
    _expr = f"{{({_cols}[i]['name'] if i < len({_cols}) else chr(65 + i)): v for i, v in enumerate(_row_raw)}}"
    lines.append(
        f"{ip}_row_data = _row_raw if isinstance(_row_raw, dict) else {_expr} "
        f"if isinstance(_row_raw, list) else {{}}"
    )
    if mode == "append":
        lines.append(f"{ip}_table_data['rows'].append(_row_data)")
    elif mode == "insert":
        lines.append(f"{ip}_table_data['rows'].insert({row}, _row_data)")
    else:
        lines.append(f"{ip}_table_data['rows'][{row}] = _row_data")
