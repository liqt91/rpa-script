from ._registry import _handler, _var_ref


@_handler("custom")
def _emit_custom(node, extra, depth, prefix, by_parent, lines):
    code = extra.get("code", "")
    desc = extra.get("description", "")
    if desc:
        lines.append(f"{prefix}# {desc}")
    for line in code.splitlines():
        lines.append(f"{prefix}{line}")


@_handler("executeJs")
def _emit_executeJs(node, extra, depth, prefix, by_parent, lines):
    script = extra.get("script", "")
    result_var = _var_ref(extra.get("resultVar", "jsResult"))
    lines.append(f"{prefix}{result_var} = tab.run_js('''{script}''')")
