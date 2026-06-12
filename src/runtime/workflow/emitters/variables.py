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


@_handler("setDictValue")
def _emit_setDictValue(node, extra, depth, prefix, by_parent, lines, element_map=None):
    dict_name = _var_ref(extra.get("dictName", "data"))
    key = _py_str(extra.get("key", ""))
    value = _py_str(extra.get("value", ""))
    lines.append(f"{prefix}{dict_name}[{key}] = {value}")


@_handler("getDictValue")
def _emit_getDictValue(node, extra, depth, prefix, by_parent, lines, element_map=None):
    dict_name = _var_ref(extra.get("dictName", "data"))
    key = _py_str(extra.get("key", ""))
    var = _var_ref(extra.get("varName", "dictValue"))
    lines.append(f"{prefix}{var} = {dict_name}.get({key})")


@_handler("removeDictKey")
def _emit_removeDictKey(node, extra, depth, prefix, by_parent, lines, element_map=None):
    dict_name = _var_ref(extra.get("dictName", "data"))
    key = _py_str(extra.get("key", ""))
    lines.append(f"{prefix}{dict_name}.pop({key}, None)")


@_handler("readTableCell")
def _emit_readTableCell(node, extra, depth, prefix, by_parent, lines, element_map=None):
    row = _py_str(extra.get("rowIndex", 0))
    col = _py_str(extra.get("columnName", ""))
    var = _var_ref(extra.get("varName", "cellValue"))
    lines.append(f"{prefix}_row_idx = int(_resolve_vars(str({row})))")
    lines.append(f"{prefix}{var} = _table_data[\"rows\"][_row_idx].get({_py_str(col)}, \"\")")


@_handler("writeTableCell")
def _emit_writeTableCell(node, extra, depth, prefix, by_parent, lines, element_map=None):
    row = _py_str(extra.get("rowIndex", 0))
    col = _py_str(extra.get("columnName", ""))
    value = _py_str(extra.get("value", ""))
    lines.append(f"{prefix}_row_idx = int(_resolve_vars(str({row})))")
    lines.append(f"{prefix}_col_name = _resolve_vars({col})")
    lines.append(f"{prefix}_ensure_table_rows(_table_data, _row_idx)")
    lines.append(f"{prefix}_table_data[\"rows\"][_row_idx][_col_name] = _resolve_vars({value})")


@_handler("getTableRowCount")
def _emit_getTableRowCount(node, extra, depth, prefix, by_parent, lines, element_map=None):
    var = _var_ref(extra.get("varName", "rowCount"))
    lines.append(f"{prefix}{var} = len(_table_data[\"rows\"])")


@_handler("writeTableRow")
def _emit_writeTableRow(node, extra, depth, prefix, by_parent, lines, element_map=None):
    mode = extra.get("writeMode", "append")
    row = _py_str(extra.get("rowIndex", 0))
    data = _py_str(extra.get("rowData", "{}"))
    lines.append(f"{prefix}_row_raw = _resolve_vars({data})")
    lines.append(f"{prefix}_row_data = _coerce_row_data(_row_raw)")
    if mode == "append":
        lines.append(f"{prefix}_table_data['rows'].append(_row_data)")
    elif mode == "insert":
        lines.append(f"{prefix}_table_data['rows'].insert({row}, _row_data)")
    else:
        lines.append(f"{prefix}_ensure_table_rows(_table_data, int(_resolve_vars(str({row}))))")
        lines.append(f"{prefix}_table_data['rows'][int(_resolve_vars(str({row})))] = _row_data")
