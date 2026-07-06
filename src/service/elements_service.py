"""
Element capture service — business logic for saving captured DOM elements
into per-workflow element libraries.

Runtime routers delegate here; this layer orchestrates repo calls.
"""

import json

from src.repo import runtime_models as models
from src.repo.models import SessionLocal


def _partition_candidates(candidates: list) -> tuple[list, list, list]:
    """Split candidates by family into css/xpath/drission lists."""
    css, xpath, drission = [], [], []
    for c in candidates:
        family = c.get("family") or c.get("type") or "css"
        if family == "css":
            css.append(c)
        elif family == "xpath":
            xpath.append(c)
        elif family == "drission":
            drission.append(c)
        else:
            # fallback: treat unknown as css
            css.append(c)
    return css, xpath, drission


def _strip_selector_prefix(value: str) -> str:
    """Remove css:/xpath:/drission: prefix if present."""
    if not value:
        return ""
    lowered = value.lower()
    if lowered.startswith("css:"):
        return value[4:].strip()
    if lowered.startswith("xpath:"):
        return value[6:].strip()
    if lowered.startswith("drission:"):
        return value[9:].strip()
    return value.strip()


def _selector_family(value: str) -> str:
    """Infer selector family from prefix or leading characters."""
    if not value:
        return "css"
    lowered = value.lower()
    if lowered.startswith("xpath:") or lowered.startswith("//"):
        return "xpath"
    if lowered.startswith("drission:"):
        return "drission"
    return "css"


def build_element_index(elements: list[models.WorkflowElement]) -> dict[str, models.WorkflowElement]:
    """Return a name -> element lookup for a workflow's element library."""
    return {el.name: el for el in elements}


def build_element_tree(
    elements: list[models.WorkflowElement],
) -> tuple[list[dict], list[str]]:
    """
    Build a nested element tree from flat WorkflowElement rows.

    Returns (tree_roots, orphan_names).
    Roots are elements with no parent (anchor_element_name empty/missing or
    points to a non-existent element). Orphans are roots whose declared parent
    does not exist.
    """
    index = build_element_index(elements)
    roots: list[models.WorkflowElement] = []
    orphans: list[str] = []

    for el in elements:
        parent = el.anchor_element_name
        if not parent or parent not in index:
            roots.append(el)
            if parent:
                orphans.append(el.name)

    def to_node(el: models.WorkflowElement, visited: set[str]) -> dict | None:
        if el.name in visited:
            # Cycle detected; treat this branch as an orphan leaf.
            return {
                "name": el.name,
                "element_kind": el.element_kind,
                "web_selector": el.web_selector or "",
                "relative_selector": el.relative_selector or "",
                "anchor_element_name": el.anchor_element_name,
                "children": [],
                "cycle": True,
            }
        visited.add(el.name)
        children = [c for c in elements if c.anchor_element_name == el.name]
        return {
            "name": el.name,
            "element_kind": el.element_kind,
            "web_selector": el.web_selector or "",
            "relative_selector": el.relative_selector or "",
            "anchor_element_name": el.anchor_element_name,
            "children": [to_node(c, set(visited)) for c in children],
        }

    tree = [to_node(r, set()) for r in roots]
    return tree, orphans


def _combine_css_chain(chain: list[dict]) -> str:
    """Combine a selector chain into a single CSS descendant selector."""
    parts: list[str] = []
    for node in chain:
        selector = _strip_selector_prefix(node.get("selector", ""))
        if not selector:
            continue
        parts.append(selector)
    return " ".join(parts)


def _combine_xpath_chain(chain: list[dict]) -> str:
    """Combine a selector chain into a single XPath expression."""
    if not chain:
        return ""
    result = _strip_selector_prefix(chain[0].get("selector", ""))
    if not result:
        return ""
    for node in chain[1:]:
        rel = _strip_selector_prefix(node.get("selector", ""))
        if not rel:
            continue
        if rel.startswith(".//"):
            result += "//" + rel[3:]
        elif rel.startswith("./"):
            result += "/" + rel[2:]
        elif rel.startswith("//"):
            result += rel
        else:
            # Treat bare relative XPath as descendant.
            result += "//" + rel
    return result


def compute_selector_chain(
    elements: list[models.WorkflowElement],
    target_name: str,
) -> dict | None:
    """
    Compute the effective selector chain from the outermost root element down
    to the target element.

    Returns None if the target does not exist. Raises ValueError on cycles.
    """
    index = build_element_index(elements)
    if target_name not in index:
        return None

    chain: list[dict] = []
    visited: set[str] = set()
    current_name: str | None = target_name

    while current_name:
        if current_name in visited:
            raise ValueError(f"Cycle detected in anchor chain at '{current_name}'")
        visited.add(current_name)
        el = index.get(current_name)
        if not el:
            raise ValueError(f"Broken chain: element '{current_name}' not found")

        if el.anchor_element_name:
            selector = el.relative_selector or ""
            kind = "child"
        else:
            selector = el.web_selector or ""
            kind = el.element_kind or "plain"

        chain.insert(0, {
            "name": el.name,
            "element_kind": el.element_kind,
            "selector": selector,
            "kind": kind,
        })
        current_name = el.anchor_element_name

    if not chain:
        return None

    root_name = chain[0]["name"]
    root_el = index.get(root_name)
    if not root_el or root_el.anchor_element_name or not chain[0]["selector"]:
        # The chain did not terminate at a root element with a global selector.
        raise ValueError(
            f"Selector chain for '{target_name}' does not terminate at a root element"
        )

    return {
        "name": target_name,
        "chain": chain,
        "combined_css": _combine_css_chain(chain),
        "combined_xpath": _combine_xpath_chain(chain),
    }


def get_element_by_name(workflow_id: int, name: str) -> models.WorkflowElement | None:
    """Fetch a single workflow element by name."""
    db = SessionLocal()
    try:
        return (
            db.query(models.WorkflowElement)
            .filter(
                models.WorkflowElement.workflow_id == workflow_id,
                models.WorkflowElement.name == name,
            )
            .first()
        )
    finally:
        db.close()


async def save_captured_element(payload: dict) -> models.WorkflowElement | None:
    """
    Persist a captured element from the browser extension into a workflow's element library.
    Returns the saved element or None on failure.
    """
    db = SessionLocal()
    try:
        workflow_id = payload.get("workflowId")
        if not isinstance(workflow_id, int) or not workflow_id:
            print("[elements_service] invalid workflowId in capture payload")
            return None
        workflow_exists = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
        if not workflow_exists:
            print(f"[elements_service] workflow {workflow_id} not found")
            return None

        page_url = payload.get("pageUrl", "")[:2048]
        raw_name = payload.get("name", "").strip()
        tag = payload.get("tag", "element")
        text_preview = (payload.get("text", "") or "").strip()

        name = raw_name[:128]
        if not name:
            if text_preview:
                name = f"{tag}_{text_preview[:20]}"
            else:
                name = f"{tag}_unknown"

        # Partition candidates by family
        candidates = payload.get("candidates", [])
        css_cands, xpath_cands, drission_cands = _partition_candidates(candidates)

        # Build attributes from payload
        attributes = payload.get("attrs", {}) or {}
        # NOTE: payload.id is the database row id in edit mode; do not store it
        # as a DOM attribute. The DOM id, if any, already lives in attrs.id.
        if payload.get("classes"):
            attributes["class"] = " ".join(payload["classes"])

        # Store list detection metadata (from browser extension structural fingerprint algorithm)
        list_container = payload.get("listContainer", "")
        list_item = payload.get("listItem", "")
        list_size = payload.get("listSize", 0)
        if list_container or list_item or list_size:
            attributes["__rpa_list_container"] = list_container
            attributes["__rpa_list_item"] = list_item
            attributes["__rpa_list_size"] = list_size

        # Determine selectors
        web_selector = (
            payload.get("webSelector", "") or payload.get("selector", "") or payload.get("locator", "")
        )[:4000]
        drission_selector = (payload.get("drissionSelector", "") or "")[:4000]

        # If no explicit drission_selector, try to find a drission candidate
        if not drission_selector and drission_cands:
            drission_selector = drission_cands[0].get("syntax", "")[:4000]

        # If no explicit web_selector, try css then xpath candidates
        if not web_selector:
            if css_cands:
                web_selector = css_cands[0].get("syntax", "")[:4000]
            elif xpath_cands:
                web_selector = xpath_cands[0].get("syntax", "")[:4000]

        # target_mode is deprecated in the UI; keep column default for backward compat.
        target_mode = "single"

        # Element kind: plain | anchor | child
        element_kind = payload.get("elementKind") or payload.get("element_kind") or "plain"
        if element_kind not in {"plain", "anchor", "child"}:
            element_kind = "plain"

        # Normalize legacy anchor_mode values to the new constrained set.
        anchor_mode = payload.get("anchorMode") or payload.get("anchor_mode") or "none"
        if anchor_mode in ("auto", "anchor-first"):
            anchor_mode = "anchor-first"
        elif anchor_mode == "backfill":
            anchor_mode = "manual"
        elif anchor_mode not in {"none", "manual"}:
            anchor_mode = "none"

        # If the user manually edited the relative selector, record it as manual.
        if payload.get("relativeManuallyEdited"):
            anchor_mode = "manual"

        relative_selector = (payload.get("relativeSelector", "") or "")[:4000]
        anchor_selector = (payload.get("anchorSelector", "") or "")[:4000]
        anchor_element_name = (payload.get("anchorElementName") or payload.get("anchor_element_name") or None)
        if anchor_element_name:
            anchor_element_name = anchor_element_name[:128]

        # Child elements are resolved relative to their anchor at runtime, so the
        # global target selector captured from the full path is neither verified
        # nor meaningful. Keep only the verified relative selector + anchor info.
        if element_kind == "child":
            web_selector = ""

        screenshot = payload.get("screenshot")
        if isinstance(screenshot, str) and len(screenshot) > 5_000_000:
            print("[elements_service] screenshot too large, dropping")
            screenshot = None

        # Child elements must reference an existing element in the same workflow.
        if element_kind == "child":
            if not anchor_element_name:
                print("[elements_service] child element requires anchor_element_name")
                return None
            anchor_el = (
                db.query(models.WorkflowElement)
                .filter(
                    models.WorkflowElement.workflow_id == workflow_id,
                    models.WorkflowElement.name == anchor_element_name,
                )
                .first()
            )
            if not anchor_el:
                print(f"[elements_service] child element references unknown anchor '{anchor_element_name}'")
                return None
            if not anchor_selector and anchor_el.web_selector:
                anchor_selector = anchor_el.web_selector
            if not relative_selector:
                print("[elements_service] child element requires relative_selector")
                return None
            # Force anchor_mode to anchor-first when not manually edited.
            if anchor_mode != "manual":
                anchor_mode = "anchor-first"

        # If an explicit anchor element name is provided, also store its selector
        # in anchor_selector for content-script/runtime fallback.
        if anchor_element_name and not anchor_selector:
            anchor_el = (
                db.query(models.WorkflowElement)
                .filter(
                    models.WorkflowElement.workflow_id == workflow_id,
                    models.WorkflowElement.name == anchor_element_name,
                )
                .first()
            )
            if anchor_el and anchor_el.web_selector:
                anchor_selector = anchor_el.web_selector

        # Check for existing element by explicit id first (edit mode), then by name.
        existing = None
        el_id = payload.get("id")
        if isinstance(el_id, int) and el_id:
            existing = (
                db.query(models.WorkflowElement)
                .filter(
                    models.WorkflowElement.workflow_id == workflow_id,
                    models.WorkflowElement.id == el_id,
                )
                .first()
            )
        if not existing:
            existing = (
                db.query(models.WorkflowElement)
                .filter(
                    models.WorkflowElement.workflow_id == workflow_id,
                    models.WorkflowElement.name == name,
                )
                .first()
            )

        if existing:
            # When editing by id and renaming, make sure the new name is not
            # already used by another element in the same workflow.
            if existing.id and el_id and existing.name != name:
                name_taken = (
                    db.query(models.WorkflowElement)
                    .filter(
                        models.WorkflowElement.workflow_id == workflow_id,
                        models.WorkflowElement.name == name,
                        models.WorkflowElement.id != existing.id,
                    )
                    .first()
                )
                if name_taken:
                    raise ValueError(
                        f"name '{name}' already exists in workflow {workflow_id}"
                    )

            # Update existing element
            existing.name = name
            existing.element_kind = element_kind
            existing.target_mode = target_mode
            existing.css_candidates = json.dumps(css_cands)
            existing.xpath_candidates = json.dumps(xpath_cands)
            existing.drission_candidates = json.dumps(drission_cands)
            existing.web_selector = web_selector
            existing.drission_selector = drission_selector
            existing.relative_selector = relative_selector
            existing.anchor_selector = anchor_selector
            existing.anchor_element_name = anchor_element_name
            existing.anchor_mode = anchor_mode
            existing.dom_path = json.dumps(payload.get("path", []))
            existing.attributes = json.dumps(attributes)
            existing.screenshot = payload.get("screenshot")
            existing.page_url = page_url
            db.commit()
            db.refresh(existing)
            print(f"[elements_service] updated element '{name}' (id={existing.id}) in workflow {workflow_id}")
            return existing

        # Create new element
        el = models.WorkflowElement(
            workflow_id=workflow_id,
            name=name,
            element_kind=element_kind,
            target_mode=target_mode,
            css_candidates=json.dumps(css_cands),
            xpath_candidates=json.dumps(xpath_cands),
            drission_candidates=json.dumps(drission_cands),
            web_selector=web_selector,
            drission_selector=drission_selector,
            relative_selector=relative_selector,
            anchor_selector=anchor_selector,
            anchor_element_name=anchor_element_name,
            anchor_mode=anchor_mode,
            dom_path=json.dumps(payload.get("path", [])),
            attributes=json.dumps(attributes),
            screenshot=payload.get("screenshot"),
            page_url=page_url,
        )
        db.add(el)
        db.commit()
        db.refresh(el)
        print(f"[elements_service] saved element '{name}' in workflow {workflow_id}")
        return el
    except Exception as e:
        print(f"[elements_service] save failed: {e}")
        return None
    finally:
        db.close()
