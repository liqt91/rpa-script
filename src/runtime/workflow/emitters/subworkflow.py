import json
from ._registry import _handler, _var_ref


@_handler("callWorkflow")
def _emit_callWorkflow(node, extra, depth, prefix, by_parent, lines):
    wf_id = extra.get("workflowId", 0)
    inputs = extra.get("inputs", "")
    lines.append(f"{prefix}# TODO: call workflow {wf_id}")


@_handler("return")
def _emit_return(node, extra, depth, prefix, by_parent, lines):
    expr = extra.get("resultExpr", "")
    if expr:
        try:
            parsed = json.loads(expr)
            expr_str = json.dumps(parsed, ensure_ascii=False)
            lines.append(f"{prefix}return {expr_str}")
        except Exception:
            lines.append(f"{prefix}return {expr}")
    else:
        lines.append(f"{prefix}return {{'total': len(_results), 'items': _results}}")
