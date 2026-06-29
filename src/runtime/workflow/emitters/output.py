from ._registry import _handler, _py_str


@_handler("log")
def _emit_log(node, extra, depth, prefix, by_parent, lines, element_map=None):
    msg = extra.get("message", "")
    level = extra.get("level", "info")
    lines.append(f'{prefix}print("[{level.upper()}]", {_py_str(msg)})')
