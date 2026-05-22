from ._registry import _handler


@_handler("keyCombo")
def _emit_keyCombo(node, extra, depth, prefix, by_parent, lines):
    keys = extra.get("keys", "")
    parts = [k.strip() for k in keys.split("+") if k.strip()]
    if parts:
        combo = ", ".join(f"Keys.{p}" for p in parts)
        lines.append(f"{prefix}tab.actions.key_down({combo}).key_up({combo})")
    else:
        lines.append(f"{prefix}# keyCombo: {keys}")
