"""Shared emit helpers and dispatch registry."""

import contextvars
import json
import re
from contextlib import contextmanager
from typing import Any

from src.repo import runtime_models as models


def _indent(depth: int) -> str:
    return "    " * depth


def _py_str(val: Any) -> str:
    """将值安全转为 Python 字符串字面量（用 repr 处理引号、换行、反斜杠等）。"""
    if val is None:
        return "''"
    return repr(str(val))


# ─── Loop-context stack for relative element resolution ─────────────
# A ContextVar isolates nested-loop state per export/coroutine so concurrent
# emissions do not interleave. _emit_forEachElement pushes the loop it emits.

_LOOP_STACK: contextvars.ContextVar[tuple[tuple[str, str], ...]] = contextvars.ContextVar(
    "_loop_stack", default=()
)


def _push_loop(element_name: str, item_var: str) -> contextvars.Token:
    """Push a forEachElement loop onto the stack."""
    current = _LOOP_STACK.get()
    return _LOOP_STACK.set(current + ((element_name, item_var),))


def _pop_loop(token: contextvars.Token) -> None:
    """Pop the innermost forEachElement loop from the stack."""
    _LOOP_STACK.reset(token)


@contextmanager
def _loop_context(element_name: str, item_var: str):
    """Context manager that pushes/pops a loop around a block."""
    token = _push_loop(element_name, item_var)
    try:
        yield
    finally:
        _pop_loop(token)


def _resolve_loop_anchor(extra: dict) -> str | None:
    """Return the loop item variable that should anchor this element call.

    - Empty loopAnchor -> innermost loop item.
    - Non-empty loopAnchor -> nearest loop whose element_name matches.
    - No loop stack -> None (global fallback).
    """
    stack = _LOOP_STACK.get()
    if not stack:
        return None
    anchor = (extra.get("loopAnchor") or "").strip()
    if not anchor:
        return stack[-1][1]
    for element_name, item_var in reversed(stack):
        if element_name == anchor:
            return item_var
    # Anchor not found: fall back to innermost loop and let caller log/warn.
    return stack[-1][1]


def _split_selector_prefix(text: str) -> tuple[str, str]:
    """Split a prefixed selector into (bare, family).

    Supports css:, xpath:, drission:. Falls back to css inference.
    """
    if not text:
        return "", "css"
    lowered = text.lower()
    for prefix, family in (("css:", "css"), ("xpath:", "xpath"), ("drission:", "drission")):
        if lowered.startswith(prefix):
            return text[len(prefix):].strip(), family
    # Heuristic: leading // or .// implies xpath, otherwise css.
    bare = text.strip()
    if bare.startswith("//") or bare.startswith(".//"):
        return bare, "xpath"
    return bare, "css"


def _build_relative_locator(el_relative_selector: str) -> str:
    """Build a DrissionPage-compatible locator string from a web relative selector."""
    bare, family = _split_selector_prefix(el_relative_selector)
    if family == "xpath":
        return f"xpath:{bare}"
    return bare


_LOCATOR_KEYS = {"locator", "selectorFamily", "type", "selector", "syntax"}


def _normalize_locator(node: models.WorkflowNode) -> str | list:
    """Parse JSON-encoded array locators back to Python objects."""
    loc = node.locator
    if isinstance(loc, str):
        text = loc.strip()
        if text.startswith("[") or text.startswith("{"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [
                        {k: v for k, v in item.items() if k in _LOCATOR_KEYS}
                        if isinstance(item, dict) else item
                        for item in parsed
                    ]
                return parsed
            except Exception:
                return text
        return text
    if isinstance(loc, list):
        return [
            {k: v for k, v in item.items() if k in _LOCATOR_KEYS}
            if isinstance(item, dict) else item
            for item in loc
        ]
    return loc or ""


def _loc_str(node: models.WorkflowNode, element_map: dict | None = None) -> str:
    """Return just the resolved locator string (for use in wait/scroll/etc)."""
    if element_map and node.element_name:
        el = element_map.get(node.element_name)
        if el and el.web_selector:
            bare, family = _split_selector_prefix(el.web_selector)
            return f"xpath:{bare}" if family == "xpath" else bare
    # fallback: legacy direct locator storage
    loc = _normalize_locator(node)
    if isinstance(loc, list):
        return loc[0] if loc else ""
    return loc or ""


def _loc_str_by_name(element_name: str | None, element_map: dict | None = None) -> str:
    """Return just the resolved locator string for a named element."""
    if element_map and element_name:
        el = element_map.get(element_name)
        if el and el.web_selector:
            bare, family = _split_selector_prefix(el.web_selector)
            return f"xpath:{bare}" if family == "xpath" else bare
    return ""


def _loc_call(
    node: models.WorkflowNode,
    extra: dict,
    element_map: dict | None = None,
    method: str | None = None,
) -> str:
    """Build tab.ele('...') style locator call."""
    return _loc_call_by_name(node.element_name, extra, element_map, method=method)


def _loc_call_by_name(
    element_name: str | None,
    extra: dict,
    element_map: dict | None = None,
    method: str | None = None,
) -> str:
    """Build tab.ele('...') style locator call for a named element.

    When the call is inside a forEachElement loop and the element or extra
    asks for relative resolution, emits item.ele('...') or just the loop item.
    An element with anchor_element_name automatically resolves relative to the
    matching loop in the current loop stack.
    Pass method='eles' to force list resolution (used by forEachElement itself).
    """
    # Scope=global forces legacy global resolution regardless of loop context.
    if extra.get("scope", "local") == "global":
        item_var = None
    else:
        item_var = _resolve_loop_anchor(extra)

    el = element_map.get(element_name) if element_map and element_name else None
    element_kind = getattr(el, "element_kind", "plain") if el else "plain"

    # Reference the loop item itself (e.g. item.click(), item.text).
    if item_var and extra.get("referenceItemItself"):
        return item_var

    rel = (getattr(el, "relative_selector", "") or "").strip()
    anchor_name = (getattr(el, "anchor_element_name", "") or "").strip()
    stack = _LOOP_STACK.get()
    explicit_loop_anchor = (extra.get("loopAnchor") or "").strip()

    matched_anchor = False
    if anchor_name and stack and (not explicit_loop_anchor or explicit_loop_anchor == anchor_name):
        for loop_name, var in reversed(stack):
            if loop_name == anchor_name:
                item_var = var
                matched_anchor = True
                break
    elif item_var and rel and not anchor_name:
        # Legacy: element has a relative selector but no named anchor; use the
        # innermost loop for backward compatibility.
        matched_anchor = True

    # Enforce element_kind semantics: child elements must resolve relative to
    # their named anchor loop. Otherwise the workflow is invalid.
    if element_kind == "child" and (not anchor_name or not matched_anchor):
        raise ValueError(
            f"Element '{element_name}' is a child element and must be used inside "
            f"a forEachElement loop for anchor '{anchor_name or '?'}'"
        )

    use_relative = bool(
        item_var
        and extra.get("useRelative", True) is not False
        and el
        and rel
        and matched_anchor
    )

    # Resolve from element_map first (per-workflow element library).
    # Prefer the validated CSS/XPath web_selector; only fall back to the legacy
    # drission_selector if no web selector exists.
    if el and (el.web_selector or el.drission_selector):
        if method is None:
            method = "ele"
        visibility_mode = extra.get("visibilityMode")
        visible_only = visibility_mode != "any" if visibility_mode else extra.get("visibleOnly", True)

        if use_relative and rel:
            loc = _build_relative_locator(rel)
        else:
            primary = el.web_selector or el.drission_selector or ""
            bare, family = _split_selector_prefix(primary)
            loc = f"xpath:{bare}" if family == "xpath" else bare
        base_var = item_var if use_relative else "tab"
        if visible_only and method == "ele":
            return f"_ele_visible({base_var}, {_py_str(loc)})"
        return f"{base_var}.{method}({_py_str(loc)})"

    # Fallback: legacy direct locator storage (should not happen after migration).
    loc = ""
    if method is None:
        method = "ele"
    visibility_mode = extra.get("visibilityMode")
    visible_only = visibility_mode != "any" if visibility_mode else extra.get("visibleOnly", True)
    base_var = item_var if use_relative else "tab"
    if not loc:
        return base_var
    if isinstance(loc, list):
        if visible_only and method == "ele":
            return f"_try_locators({base_var}, {repr(loc)}, method={repr(method)}, visible_only=True)"
        return f"_try_locators({base_var}, {repr(loc)}, method={repr(method)})"
    if visible_only and method == "ele":
        return f"_ele_visible({base_var}, {_py_str(loc)})"
    return f"{base_var}.{method}({_py_str(loc)})"


def _loc_calls(node: models.WorkflowNode, extra: dict, element_map: dict | None = None) -> list[str]:
    """Build locator calls for the primary element plus any additional element_names."""
    calls = [_loc_call(node, extra, element_map)]
    for name in extra.get("element_names") or []:
        if name:
            calls.append(_loc_call_by_name(name, extra, element_map))
    return calls


_VAR_REF_RE = re.compile(r'^\$\{(\w+)\}$|^\{\{(\w+)\}}$')


def _clean_var_ref(val: str) -> str:
    """Strip ${var} or {{var}} wrapper from a variable name field."""
    if not isinstance(val, str):
        return val
    m = _VAR_REF_RE.match(val.strip())
    if m:
        return m.group(1) or m.group(2)
    return val.strip()


def _var_ref(name: str) -> str:
    """Sanitize variable name."""
    return _clean_var_ref(name) if name else "_tmp"


_EMIT_HANDLERS: dict[str, Any] = {}


def _handler(name: str):
    def decorator(fn):
        _EMIT_HANDLERS[name] = fn
        return fn
    return decorator


def _emit_children(node: models.WorkflowNode, depth: int,
                   by_parent: dict, lines: list[str], element_map: dict | None = None) -> None:
    """Emit child nodes of a container command."""
    for child in by_parent.get(node.id, []):
        if getattr(child, "enabled", 1) == 0:
            continue
        extra = json.loads(child.extra) if child.extra else {}
        _emit_dispatch(child, extra, depth + 1, by_parent, lines, element_map)


def _emit_dispatch(node: models.WorkflowNode, extra: dict, depth: int,
                   by_parent: dict, lines: list[str], element_map: dict | None = None) -> None:
    if getattr(node, "enabled", 1) == 0:
        return
    prefix = _indent(depth)
    from src.runtime.workflow.commands import get_command
    cmd = get_command(node.type) or {}
    label = cmd.get("label", node.type)
    lines.append(f"{prefix}# WF_NODE id={node.id} type={node.type} label={label}")

    is_container = cmd.get("isContainer")
    is_structural = cmd.get("isStructural")
    handler = _EMIT_HANDLERS.get(node.type)

    if not handler:
        loc = _loc_call(node, extra, element_map)
        lines.append(f"{prefix}# TODO: {node.type} -> {loc}")
        return

    if is_container or is_structural:
        handler(node, extra, depth, prefix, by_parent, lines, element_map)
        return

    # 普通指令：包装 try/except/retry + 人工延迟
    on_error = extra.get("onError", "stop")
    retry_count = extra.get("retryCount", 3)

    handler_lines: list[str] = []
    handler(node, extra, depth, prefix, by_parent, handler_lines, element_map)
    handler_lines.append(f"{prefix}_human_delay()")

    if on_error == "retry":
        lines.append(f"{prefix}for _retry_idx in range({retry_count}):")
        lines.append(f"{prefix}    try:")
        for hl in handler_lines:
            content = hl[len(prefix):] if hl.startswith(prefix) else hl
            lines.append(f"{prefix}        {content}")
        lines.append(f"{prefix}        break")
        lines.append(f"{prefix}    except Exception as _e:")
        lines.append(
            f'{prefix}        print(f"[WF_ERROR] '
            f'指令 #{node.id} ({node.type}) {label} "'
            f'f"(retry {{_retry_idx + 1}}/{retry_count}): {{_e}}", file=sys.stderr)'
        )
        lines.append(f"{prefix}        if _retry_idx < {retry_count - 1}:")
        lines.append(f"{prefix}            time.sleep(0.5)")
        lines.append(f"{prefix}else:")
        lines.append(
            f'{prefix}    raise RuntimeError('
            f'f"指令 #{node.id} ({node.type}) {label} '
            f'重试 {retry_count} 次后仍然失败")'
        )
    else:
        lines.append(f"{prefix}try:")
        for hl in handler_lines:
            content = hl[len(prefix):] if hl.startswith(prefix) else hl
            lines.append(f"{prefix}    {content}")
        lines.append(f"{prefix}except Exception as _e:")
        lines.append(
            f'{prefix}    print(f"[WF_ERROR] '
            f'指令 #{node.id} ({node.type}) {label}: {{_e}}", file=sys.stderr)'
        )
        if on_error == "continue":
            lines.append(f"{prefix}    pass  # continue on error")
        else:
            lines.append(f"{prefix}    raise")
