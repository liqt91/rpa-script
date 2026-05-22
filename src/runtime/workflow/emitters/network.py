import json
from ._registry import _handler, _var_ref, _py_str


@_handler("httpRequest")
def _emit_httpRequest(node, extra, depth, prefix, by_parent, lines):
    method = extra.get("method", "GET")
    url = extra.get("url")
    headers_str = extra.get("headers", "")
    body = extra.get("body", "")
    timeout = extra.get("timeout", 30)
    result_var = _var_ref(extra.get("resultVar", "response"))

    lines.append(f"{prefix}import requests")
    lines.append(f"{prefix}{result_var} = requests.{method.lower()}({_py_str(url)}")

    if headers_str:
        try:
            headers = json.loads(headers_str)
            lines.append(f"{prefix}    , headers={json.dumps(headers)}")
        except Exception:
            pass

    if body and method in ("POST", "PUT"):
        try:
            json_body = json.loads(body)
            lines.append(f"{prefix}    , json={json_body}")
        except Exception:
            lines.append(f"{prefix}    , data={_py_str(body)}")

    lines.append(f"{prefix}    , timeout={timeout})")
