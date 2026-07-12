"""
Extension Emitter — schema-driven instruction sequence generator.

Driven by COMMAND_REGISTRY["runtimes"].extension declarations.
Only emits commands that declare extension runtime support.
Container nodes are emitted as compound instructions with body/elseBody.
"""

import contextvars
import json
from contextlib import contextmanager
from src.repo import runtime_models as models
from src.runtime.workflow.handlers.registry import build_command_registry


# Extra transforms applied per command type for extension compatibility.
_EXTRA_TRANSFORMS = {
    "sleep": lambda e: {**e, "seconds": e.get("seconds", 1)},
    "scrollToBottom": lambda e: {**e, "scrollType": "toBottom"},
    "scrollToTop": lambda e: {**e, "scrollType": "toTop"},
    "scrollOneScreen": lambda e: {**e, "scrollType": "oneScreen"},
    "scrollBy": lambda e: {**e, "scrollType": "by"},
    "getText": lambda e: {**e, "attribute": None},
    "getAttr": lambda e: {**e, "attribute": e.get("attrName")},
    "getHtml": lambda e: {**e, "attribute": "innerHTML"},
    "getValue": lambda e: {**e, "attribute": "value"},
    "inputAndPressEnter": lambda e: {**e, "pressEnter": True},
}


# ─── Loop-context stack for relative element resolution ─────────────
# Tracks the element_names of active forEachElement loops so child
# instructions can automatically resolve relative to their anchor.
_LOOP_STACK: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar(
    "_loop_stack_ext", default=()
)


def _push_loop(element_name: str) -> contextvars.Token:
    current = _LOOP_STACK.get()
    return _LOOP_STACK.set(current + (element_name,))


def _pop_loop(token: contextvars.Token) -> None:
    _LOOP_STACK.reset(token)


@contextmanager
def _loop_context(element_name: str):
    token = _push_loop(element_name)
    try:
        yield
    finally:
        _pop_loop(token)


def _build_by_parent(nodes: list[models.WorkflowNode]) -> dict:
    """Group nodes by parent_id."""
    by_parent: dict = {}
    for n in nodes:
        by_parent.setdefault(n.parent_id, []).append(n)
    for pid in by_parent:
        by_parent[pid].sort(key=lambda x: x.order)
    return by_parent


def _parse_extra(node: models.WorkflowNode) -> dict:
    if node.extra and isinstance(node.extra, str):
        try:
            extra = json.loads(node.extra)
        except Exception:
            extra = {}
    else:
        extra = node.extra or {}
    return _apply_defaults(node.cmd, extra)


def _apply_defaults(cmd_type: str, extra: dict) -> dict:
    """Fill missing extra fields with schema defaults so old workflows pick up new fields."""
    cmd = build_command_registry().get(cmd_type)
    if not cmd:
        return extra
    defaults = {}
    for field in cmd.get("fields", []):
        name = field.get("name")
        default = field.get("default")
        if name is not None and default is not None and name not in extra:
            defaults[name] = default
    return {**defaults, **extra} if defaults else extra


def _node_meta(node: models.WorkflowNode) -> tuple[bool, bool, bool]:
    """Return (is_container, is_branch, is_structural) for a node."""
    cmd = build_command_registry().get(node.cmd) or {}
    is_container = cmd.get("isContainer", False)
    is_branch = cmd.get("isBranch", False)
    is_structural = cmd.get("isStructural", False)
    # Legacy fallback for types that should be containers
    if not is_container and node.cmd in ("if", "for", "loop", "try", "while"):
        is_container = True
    return is_container, is_branch, is_structural


def _match_brackets(nodes: list[models.WorkflowNode]) -> tuple[dict, dict]:
    """
    Bracket matching: map container -> structural end node, and container -> branch node.
    Returns (container_close, container_branch).
    """
    sorted_nodes = sorted(nodes, key=lambda n: n.order)
    stack = []
    container_close: dict = {}
    container_branch: dict = {}

    for node in sorted_nodes:
        is_container, is_branch, is_structural = _node_meta(node)
        if is_branch:
            # Branch nodes (else/catch) belong to the nearest open container and
            # share its closing marker; do not push them as a new container scope.
            if stack:
                container_id = stack[-1]
                container_branch[container_id] = node.id
        elif is_container:
            stack.append(node.id)
        elif is_structural:
            if stack:
                closed = stack.pop()
                container_close[closed] = node.id

    return container_close, container_branch


def _infer_selector_family(locator: str) -> str:
    """Infer selector family from locator string prefix/pattern."""
    if not locator:
        return "css"
    text = locator.strip()
    if text.startswith("xpath:") or text.startswith("//"):
        return "xpath"
    drission_prefixes = ("@", "tag:", "verse:", "text=", "@@")
    if any(text.startswith(p) for p in drission_prefixes):
        return "drission"
    return "css"


def _normalize_locator(val):
    if isinstance(val, str):
        text = val.strip()
        if text.startswith("[") or text.startswith("{"):
            try:
                return json.loads(text)
            except Exception:
                return text
        return text
    return val


def _split_prefixed_selector(value: str) -> tuple[str, str]:
    """Split a `family:selector` string into (selector, family).

    relative_selector is stored with an explicit `css:`/`xpath:`/`drission:`
    prefix. If no recognized prefix is present, the family is inferred from the
    bare selector pattern.
    """
    text = (value or "").strip()
    if not text:
        return "", "css"
    for prefix in ("css:", "xpath:", "drission:"):
        if text.startswith(prefix):
            bare = text[len(prefix):].strip()
            return bare, prefix[:-1]
    return text, _infer_selector_family(text)


def _ancestor_chain(el, element_map: dict | None) -> list:
    """Return the ancestor chain from root down to `el`."""
    chain = []
    visited = set()
    current = el
    while current:
        chain.append(current)
        parent_name = (getattr(current, "anchor_element_name", "") or "").strip()
        if not parent_name or parent_name in visited:
            break
        visited.add(parent_name)
        current = element_map.get(parent_name) if element_map else None
    return list(reversed(chain))


def _find_matching_loop(anchor_name: str, element_map: dict | None, stack: tuple) -> str | None:
    """Find the nearest active loop that appears in `anchor_name`'s ancestor chain.

    If `anchor_name` itself is an active loop, it wins immediately. Otherwise
    walk up through `anchor_element_name` until a loop in `stack` is found.
    """
    if not anchor_name or not stack:
        return None
    if anchor_name in stack:
        return anchor_name
    current = element_map.get(anchor_name) if element_map else None
    visited = {anchor_name}
    while current:
        if current.name in stack:
            return current.name
        parent_name = (getattr(current, "anchor_element_name", "") or "").strip()
        if not parent_name or parent_name in visited:
            break
        visited.add(parent_name)
        current = element_map.get(parent_name)
    return None


def _build_chain_from_loop(el, loop_name: str, element_map: dict | None) -> list | None:
    """Return the chain [loop_element, ..., el] if `loop_name` is an ancestor of `el`."""
    chain = []
    visited = set()
    current = el
    while current:
        chain.insert(0, current)
        if current.name == loop_name:
            break
        parent_name = (getattr(current, "anchor_element_name", "") or "").strip()
        if not parent_name or parent_name in visited:
            return None
        visited.add(parent_name)
        current = element_map.get(parent_name)
    if not chain or chain[0].name != loop_name:
        return None
    return chain


def _combine_relative_chain(chain: list) -> tuple[str | None, str | None]:
    """Combine relative selectors from a chain into one locator relative to the first element.

    Returns (combined_selector, family). Mixed CSS/XPath families are not supported
    and return (None, None) so the caller can fall back to the immediate anchor.
    """
    css_parts = []
    xpath_parts = []
    for node in chain[1:]:
        sel = (getattr(node, "relative_selector", "") or "").strip()
        if not sel:
            sel = (getattr(node, "web_selector", "") or "").strip()
        if not sel:
            continue
        bare, family = _split_prefixed_selector(sel)
        if not bare:
            continue
        if family == "xpath":
            xpath_parts.append(bare)
        else:
            css_parts.append(bare)
    if css_parts and xpath_parts:
        return None, None
    if xpath_parts:
        combined = xpath_parts[0]
        for part in xpath_parts[1:]:
            if part.startswith(".//"):
                combined += "//" + part[3:]
            elif part.startswith("./"):
                combined += "/" + part[2:]
            elif part.startswith("//"):
                combined += part
            else:
                combined += "//" + part
        return combined, "xpath"
    if css_parts:
        return " ".join(css_parts), "css"
    return None, None


def _inject_relative_fields(extra: dict, el, element_map: dict | None = None) -> dict:
    """Inject capture-time relative-anchor fields into an instruction's extra.

    Child elements with a relative_selector always resolve relatively.
    For anchor/plain elements, relative resolution only happens when the user
    has not explicitly disabled it (useRelative=False) and scope is not global.

    If the element's immediate anchor is not the current loop, this function
    walks up the anchor chain and finds the nearest active forEachElement loop
    that is an ancestor of the element. It then emits a combined relative
    selector from that loop down to the target element, so nested anchor chains
    (e.g. loop -> parent anchor -> child -> grandchild) work without flattening
    the captured tree.
    """
    if not el:
        return extra
    element_kind = getattr(el, "element_kind", "plain")
    if element_kind == "plain":
        return extra
    if extra.get("scope", "local") == "global":
        return extra

    rel = (getattr(el, "relative_selector", "") or "").strip()
    if not rel:
        return extra
    rel_selector, rel_family = _split_prefixed_selector(rel)
    if not rel_selector:
        return extra

    # Child elements always use their verified relative selector.
    if element_kind != "child" and extra.get("useRelative") is False:
        return extra

    anchor_name = (getattr(el, "anchor_element_name", "") or "").strip()
    stack = _LOOP_STACK.get()
    if anchor_name:
        loop_name = _find_matching_loop(anchor_name, element_map, stack)
        if not loop_name:
            if element_kind == "child":
                raise ValueError(
                    f"Element '{getattr(el, 'name', '')}' is a child element and must be used "
                    f"inside a forEachElement loop for anchor '{anchor_name}'"
                )
            return extra
    else:
        # Legacy fallback: only allowed for non-child elements.
        if element_kind == "child":
            raise ValueError(
                f"Child element '{getattr(el, 'name', '')}' must have anchor_element_name"
            )
        return extra

    enriched = dict(extra)
    enriched["useRelative"] = True
    enriched["loopAnchor"] = loop_name

    # Try to build a combined selector from the matching loop down to this
    # element. If that fails (mixed families or broken chain), fall back to
    # the immediate relative selector and the matching loop context.
    chain = _build_chain_from_loop(el, loop_name, element_map)
    if chain and len(chain) > 1:
        combined, family = _combine_relative_chain(chain)
        if combined:
            enriched["relativeLocator"] = combined
            enriched["relativeSelectorFamily"] = family
            return enriched

    enriched["relativeLocator"] = rel_selector
    enriched["relativeSelectorFamily"] = rel_family
    return enriched


def _emit_instruction(
    node: models.WorkflowNode, step_index: int, handler: str,
    element_map: dict | None = None,
) -> dict:
    """Convert a single node to an instruction dict."""
    extra = _parse_extra(node)
    transform = _EXTRA_TRANSFORMS.get(node.cmd)
    if transform:
        extra = transform(extra)

    # Resolve element_name -> selector from element_map
    el = element_map.get(node.element_name) if element_map and node.element_name else None
    locator = _normalize_locator(el.web_selector) if el else ""
    selector_family = _infer_selector_family(el.web_selector) if el else "css"

    # Inject capture-time relative-anchor fields (no-op for unanchored elements).
    extra = _inject_relative_fields(extra, el, element_map)

    return {
        "stepId": f"step_{step_index}",
        "nodeId": node.id,
        "order": node.order,
        "cmdType": node.cmd,
        "cmdLabel": (build_command_registry().get(node.cmd) or {}).get("label", node.cmd),
        "type": handler,
        "locator": locator,
        "selectorFamily": selector_family,
        "action": node.action,
        "extra": extra,
    }


def _get_extension_runtime(cmd_type: str) -> dict | None:
    """Return the extension runtime declaration for a command, or None."""
    # Old type name → handler mapping for backward compatibility
    LEGACY_MAP = {
        "click": "elementAction", "input": "elementAction",
        "clearInput": "elementAction", "doubleClick": "elementAction",
        "rightClick": "elementAction", "hover": "elementAction",
        "unhover": "elementAction", "selectOption": "elementAction",
        "getAttr": "elementAction", "getHtml": "elementAction",
        "scrollToBottom": "elementAction", "scrollToTop": "elementAction",
        "scrollBy": "elementAction", "scrollOneScreen": "elementAction",
        "inputAndPressEnter": "elementAction", "clickCurrentLoopItem": "elementAction",
        "pressKey": "pressKey", "keyCombo": "keyCombo",
        "getPageTitle": "getPageTitle", "getElementCount": "getElementCount",
        "takeScreenshot": "takeScreenshot", "executeJs": "executeJs",
        "waitForElement": "wait", "waitForText": "wait",
        "waitForUrl": "wait", "waitForLoad": "wait",
        "waitForElementHide": "wait",
    }
    cmd = build_command_registry().get(cmd_type)
    if cmd:
        return cmd.get("runtimes", {}).get("extension")
    # Fallback: old type name
    handler = LEGACY_MAP.get(cmd_type)
    if handler:
        return {"handler": handler, "local": False}
    return None


def _is_container_node(node: models.WorkflowNode) -> bool:
    """Check if a node is a container (can have children that form a body)."""
    is_container, _, _ = _node_meta(node)
    return is_container


def _is_skip_node(node: models.WorkflowNode) -> bool:
    """Check if a node should be skipped during flat walking (branch/structural markers)."""
    _, is_branch, is_structural = _node_meta(node)
    return is_branch or is_structural


def build_instructions(nodes: list[models.WorkflowNode], element_map: dict | None = None) -> list[dict]:
    """
    Build an instruction sequence from a node tree.
    Container nodes become compound instructions with 'body' sub-instructions.
    If/try containers may also have 'elseBody' from branch nodes (else/catch).
    Branch and structural nodes are consumed as markers, not emitted.
    element_map: {element_name: WorkflowElement} for resolving selectors.
    """
    by_parent = _build_by_parent(nodes)
    container_close, container_branch = _match_brackets(nodes)
    node_map = {n.id: n for n in nodes}
    instructions: list[dict] = []
    step_counter = [0]

    def _next_step_id() -> str:
        step_counter[0] += 1
        return f"step_{step_counter[0]}"

    def _resolve_locator(element_name: str | None) -> tuple[str, str]:
        """Resolve an element_name to (locator, selector_family)."""
        el = element_map.get(element_name) if element_map and element_name else None
        if el:
            return (
                _normalize_locator(el.web_selector),
                _infer_selector_family(el.web_selector),
            )
        return "", "css"

    def _build_body(parent_id) -> list[dict]:
        """Recursively build instructions for all children of a parent."""
        body: list[dict] = []
        children = by_parent.get(parent_id, [])
        for child in children:
            if getattr(child, "enabled", 1) == 0:
                continue
            if _is_skip_node(child):
                continue
            child_instructions = _build_node(child)
            if isinstance(child_instructions, list):
                body.extend(child_instructions)
            elif child_instructions:
                body.append(child_instructions)
        return body

    def _build_node(node: models.WorkflowNode) -> dict | list | None:
        """Build instruction(s) for a single node. Returns dict, list, or None."""
        if getattr(node, "enabled", 1) == 0:
            return None

        is_container, _, _ = _node_meta(node)
        extra = _parse_extra(node)
        locator, selector_family = _resolve_locator(node.element_name)

        if is_container:
            # Build compound instruction. forEachElement pushes its element_name
            # onto the loop stack so descendants can auto-resolve relatives.
            # If the loop element itself is a child, resolve it relative to its
            # parent loop so nested forEachElement loops work without a global chain.
            if node.cmd == "forEachElement" and node.element_name:
                el = element_map.get(node.element_name) if element_map else None
                if el and getattr(el, "element_kind", "plain") == "child":
                    rel_extra = _inject_relative_fields(extra, el, element_map)
                    if rel_extra.get("relativeLocator"):
                        extra = rel_extra
                        locator = rel_extra["relativeLocator"]
                        selector_family = rel_extra.get("relativeSelectorFamily", "css")
                with _loop_context(node.element_name):
                    body = _build_body(node.id)
                    branch_id = container_branch.get(node.id)
                    else_body = _build_body(branch_id) if branch_id else []
            else:
                body = _build_body(node.id)
                branch_id = container_branch.get(node.id)
                else_body = _build_body(branch_id) if branch_id else []

            compound = {
                "stepId": _next_step_id(),
                "nodeId": node.id,
                "order": node.order,
                "cmdType": node.cmd,
                "cmdLabel": (build_command_registry().get(node.cmd) or {}).get("label", node.cmd),
                "type": node.cmd,
                "compound": True,
                "elementName": node.element_name,
                "locator": locator,
                "selectorFamily": selector_family,
                "action": node.action,
                "extra": extra,
                "body": body,
            }
            close_id = container_close.get(node.id)
            if close_id:
                close_node = node_map.get(close_id)
                if close_node:
                    compound["endOrder"] = close_node.order
                    compound["endNodeId"] = close_node.id
            # Support additional elements for multi-element condition commands
            alt_names = extra.get("element_names") or []
            if alt_names:
                compound["altLocators"] = [
                    {"locator": _resolve_locator(name)[0],
                     "selectorFamily": _resolve_locator(name)[1]}
                    for name in alt_names if name
                ]
            if else_body:
                compound["elseBody"] = else_body
            return compound

        # Leaf node: check for extension runtime support
        runtime = _get_extension_runtime(node.cmd)
        if not runtime:
            # Special case: break/continue have no runtime but are handled by runner
            if node.cmd in ("break", "continue"):
                return {
                    "stepId": _next_step_id(),
                    "nodeId": node.id,
                    "order": node.order,
                    "cmdType": node.cmd,
                    "cmdLabel": (build_command_registry().get(node.cmd) or {}).get("label", node.cmd),
                    "type": node.cmd,
                    "compound": True,
                    "extra": extra,
                }
            # Skip commands without extension runtime declaration
            return None

        step_counter[0] += 1
        return _emit_instruction(node, step_counter[0], runtime["handler"], element_map)

    # Walk top-level (parent_id=None)
    root_children = by_parent.get(None, [])
    for node in root_children:
        if getattr(node, "enabled", 1) == 0:
            continue
        if _is_skip_node(node):
            continue
        result = _build_node(node)
        if isinstance(result, list):
            instructions.extend(result)
        elif result:
            instructions.append(result)

    return instructions
