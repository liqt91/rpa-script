from ._registry import _handler, _var_ref


@_handler("callAiApp")
def _emit_callAiApp(node, extra, depth, prefix, by_parent, lines, element_map=None):
    app_type = extra.get("appType", "")
    inputs = extra.get("inputs", "{}")
    result_var = _var_ref(extra.get("resultVar", "aiResult"))
    lines.append(f"{prefix}# TODO: call AI app '{app_type}' with inputs={inputs}")
    lines.append(f"{prefix}{result_var} = None")
