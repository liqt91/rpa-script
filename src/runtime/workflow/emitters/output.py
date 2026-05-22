import json
from ._registry import _handler, _var_ref


@_handler("log")
def _emit_log(node, extra, depth, prefix, by_parent, lines):
    msg = (extra.get("message") or "").replace("'", "\\'")
    level = extra.get("level", "info")
    lines.append(f"{prefix}print('[{level.upper()}] {msg}')")


@_handler("pushItem")
def _emit_pushItem(node, extra, depth, prefix, by_parent, lines):
    expr = extra.get("dataExpr", "{}")
    try:
        parsed = json.loads(expr)
        expr_str = json.dumps(parsed, ensure_ascii=False, indent=None).replace("'", "\\'")
    except Exception:
        expr_str = expr.replace("'", "\\'")
    lines.append(f"{prefix}_results.append({expr_str})")


@_handler("takeScreenshot")
def _emit_takeScreenshot(node, extra, depth, prefix, by_parent, lines):
    path = (extra.get("savePath") or "screenshot.png").replace("'", "\\'")
    full = extra.get("fullPage", False)
    loc = extra.get("locator", "").replace("'", "\\'")
    if loc:
        lines.append(f"{prefix}tab.ele('{loc}').get_screenshot(path='{path}')")
    elif full:
        lines.append(f"{prefix}tab.get_screenshot(path='{path}', full_page=True)")
    else:
        lines.append(f"{prefix}tab.get_screenshot(path='{path}')")


@_handler("saveToFile")
def _emit_saveToFile(node, extra, depth, prefix, by_parent, lines):
    data_var = _var_ref(extra.get("dataVar", "data"))
    path = (extra.get("filePath") or "data.json").replace("'", "\\'")
    fmt = extra.get("format", "json")
    if fmt == "json":
        lines.append(f"{prefix}import json")
        lines.append(f"{prefix}with open('{path}', 'w', encoding='utf-8') as f:")
        lines.append(f"{prefix}    json.dump({data_var}, f, ensure_ascii=False, indent=2)")
    else:
        lines.append(f"{prefix}import csv")
        lines.append(f"{prefix}with open('{path}', 'w', newline='', encoding='utf-8') as f:")
        lines.append(f"{prefix}    writer = csv.DictWriter(f, fieldnames={data_var}[0].keys())")
        lines.append(f"{prefix}    writer.writeheader()")
        lines.append(f"{prefix}    writer.writerows({data_var})")
