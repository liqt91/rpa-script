"""
Element capture service — business logic for saving captured DOM elements.

Runtime routers delegate here; this layer orchestrates repo calls.
"""

import json
from urllib.parse import urlparse

from src.repo import runtime_models as models
from src.repo.models import SessionLocal


async def save_captured_element(payload: dict) -> models.CapturedElement | None:
    """
    Persist a captured element from the browser extension.
    Returns the saved element or None on failure.
    """
    db = SessionLocal()
    try:
        page_url = payload.get("pageUrl", "")
        hostname = urlparse(page_url).hostname or ""
        locator = payload.get("locator", "")
        tag = payload.get("tag", "element")
        text_preview = (payload.get("text", "") or "").strip()
        raw_name = payload.get("name", "")
        print(f"[elements_service] raw_name={raw_name!r} tag={tag} locator={locator[:30]}")
        name = raw_name
        if not name:
            if text_preview:
                name = f"{tag}_{text_preview[:20]}"
            elif locator:
                name = f"{tag}_{locator[:30]}"
            else:
                name = f"{tag}_unknown"

        el = models.CapturedElement(
            user_id=1,  # local single-user mode
            name=name,
            description="",
            locator=locator,
            locator_type=payload.get("locatorType", "css"),
            method="ele",
            candidates=json.dumps(payload.get("candidates", [])),
            features=json.dumps(payload.get("features", {})),
            css_selector=locator if payload.get("locatorType") == "css" else None,
            tag=tag,
            text_preview=(payload.get("text", "") or "")[:128],
            page_url=page_url,
            hostname=hostname,
            screenshot=payload.get("screenshot"),
        )
        db.add(el)
        db.commit()
        db.refresh(el)
        return el
    except Exception:
        return None
    finally:
        db.close()
