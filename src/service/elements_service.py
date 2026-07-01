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
        if payload.get("id"):
            attributes["id"] = payload["id"]
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
        web_selector = (payload.get("webSelector", "") or payload.get("selector", "") or payload.get("locator", ""))[:4000]
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

        screenshot = payload.get("screenshot")
        if isinstance(screenshot, str) and len(screenshot) > 5_000_000:
            print("[elements_service] screenshot too large, dropping")
            screenshot = None

        # Child elements must reference an existing anchor element in the same workflow.
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
            if anchor_el.element_kind != "anchor":
                print(f"[elements_service] referenced element '{anchor_element_name}' is not an anchor")
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

        # Check for existing element with same name in this workflow
        existing = (
            db.query(models.WorkflowElement)
            .filter(
                models.WorkflowElement.workflow_id == workflow_id,
                models.WorkflowElement.name == name,
            )
            .first()
        )

        if existing:
            # Update existing element
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
            print(f"[elements_service] updated element '{name}' in workflow {workflow_id}")
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
