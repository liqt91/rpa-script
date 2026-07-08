"""
Tests for extension handler resolution with curated command set.
"""

import pytest
from src.repo import models
from src.runtime.workflow.extension_emitter import build_instructions, _get_extension_runtime

# Curated extension handlers (16 from our selected subset)
CURATED_EXTENSION = [
    "checkElementExists", "clickElement", "closeBrowser", "executeJs",
    "getAttribute", "getText", "getValue", "hover", "inputText",
    "navigate", "newTab", "pressKey", "scrollIntoView", "scrollToBottom",
    "takeScreenshot", "waitForElement",
]


def test_curated_handlers_all_resolve():
    """Every curated extension handler resolves to a valid runtime."""
    for htype in CURATED_EXTENSION:
        runtime = _get_extension_runtime(htype)
        assert runtime is not None, f"'{htype}' not found in registry or LEGACY_MAP"
        handler = runtime.get("handler")
        assert handler, f"'{htype}' has no handler name: {runtime}"


def test_curated_handlers_produce_instructions(db_session):
    """All curated handlers must produce build_instructions output."""
    wf = models.Workflow(name="curated-test", url="https://example.com")
    db_session.add(wf)
    db_session.flush()

    for i, htype in enumerate(CURATED_EXTENSION):
        node = models.WorkflowNode(
            workflow_id=wf.id, type=htype, order=i,
            extra="{}", enabled=1,
        )
        db_session.add(node)
    db_session.flush()

    loaded = (
        db_session.query(models.WorkflowNode)
        .filter(models.WorkflowNode.workflow_id == wf.id)
        .order_by(models.WorkflowNode.order)
        .all()
    )

    instructions = build_instructions(loaded)
    assert len(instructions) == len(CURATED_EXTENSION), \
        f"Expected {len(CURATED_EXTENSION)} instructions, got {len(instructions)}"

    type_order = [i["cmdType"] for i in instructions]
    assert type_order == CURATED_EXTENSION, \
        f"Order mismatch: {type_order}"


# ── Legacy type support ──────────────────────────────────────

LEGACY_TYPES = [
    "click", "input", "hover", "getText", "getValue",
    "scrollToBottom", "executeJs", "waitForElement",
]


def test_legacy_map_covers_basic_types():
    """LEGACY_MAP must cover common old type names."""
    for old_type in LEGACY_TYPES:
        runtime = _get_extension_runtime(old_type)
        assert runtime is not None, f"LEGACY_MAP missing: {old_type!r}"


def test_legacy_workflow_realistic(db_session):
    """Old workflow: navigate, click, input, wait, getText — all resolve."""
    import json
    wf = models.Workflow(name="legacy-realistic", url="https://example.com")
    db_session.add(wf)
    db_session.flush()

    node_data = [
        ("navigate", 1, {}),
        ("click", 2, {"elementName": "search-btn"}),
        ("input", 3, {"elementName": "search-input", "text": "hello"}),
        ("waitForElement", 4, {"seconds": 3}),
        ("getText", 5, {"elementName": "result-title"}),
    ]

    for ntype, order, extra_dict in node_data:
        node = models.WorkflowNode(
            workflow_id=wf.id, type=ntype, order=order,
            extra=json.dumps(extra_dict), enabled=1,
        )
        db_session.add(node)
    db_session.flush()

    loaded = (
        db_session.query(models.WorkflowNode)
        .filter(models.WorkflowNode.workflow_id == wf.id)
        .order_by(models.WorkflowNode.order)
        .all()
    )

    instructions = build_instructions(loaded)
    assert len(instructions) == 5
    assert [i["cmdType"] for i in instructions] == [
        "navigate", "click", "input", "waitForElement", "getText",
    ]
