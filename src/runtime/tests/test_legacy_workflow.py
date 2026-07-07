"""
Tests for legacy workflow type support.

Ensures that old type names (e.g. 'click', 'input') still produce valid
instructions through the LEGACY_MAP fallback in extension_emitter.
"""

import pytest
from src.repo import models
from src.runtime.workflow.extension_emitter import build_instructions, _get_extension_runtime

# Every old type name mapped in LEGACY_MAP
LEGACY_TYPES = [
    "click", "input", "clearInput", "doubleClick", "rightClick", "hover",
    "unhover", "selectOption", "getAttr", "getHtml", "getText", "getValue",
    "scrollToBottom", "scrollToTop", "scrollBy", "scrollOneScreen",
    "inputAndPressEnter", "clickCurrentLoopItem",
    "pressKey", "keyCombo",
    "getPageTitle", "getElementCount",
    "takeScreenshot", "executeJs",
    "waitForElement", "waitForText", "waitForUrl", "waitForLoad",
    "waitForElementHide",
]


def test_legacy_map_covers_all_old_types():
    """LEGACY_MAP must map every known old type to a handler."""
    for old_type in LEGACY_TYPES:
        runtime = _get_extension_runtime(old_type)
        assert runtime is not None, f"LEGACY_MAP missing: {old_type!r}"
        assert "handler" in runtime, f"LEGACY_MAP entry for {old_type!r} has no handler"
        assert isinstance(runtime["handler"], str) and runtime["handler"], \
            f"LEGACY_MAP handler for {old_type!r} is empty"


def test_build_instructions_no_loss_for_legacy_types(db_session):
    """Nodes with legacy type names should not be lost in build_instructions()."""
    wf = models.Workflow(name="legacy-test", url="https://example.com")
    db_session.add(wf)
    db_session.flush()

    nodes = []
    for i, old_type in enumerate(LEGACY_TYPES):
        node = models.WorkflowNode(
            workflow_id=wf.id,
            type=old_type,
            order=i,
            extra="{}",
            enabled=1,
        )
        db_session.add(node)
        nodes.append(node)

    db_session.flush()

    # Load from DB to ensure we get real ORM objects
    loaded = (
        db_session.query(models.WorkflowNode)
        .filter(models.WorkflowNode.workflow_id == wf.id)
        .order_by(models.WorkflowNode.order)
        .all()
    )

    assert len(loaded) == len(LEGACY_TYPES), "Not all legacy nodes persisted"

    instructions = build_instructions(loaded)
    instruction_count = len(instructions)

    # Every legacy type that maps to a valid handler should produce an
    # instruction. Types mapped to container-only handlers may still produce
    # output if the handler exists.
    assert instruction_count > 0, "build_instructions produced zero instructions"
    assert instruction_count == len(LEGACY_TYPES), \
        f"Expected {len(LEGACY_TYPES)} instructions, got {instruction_count}"


def test_legacy_workflow_realistic(db_session):
    """Simulate a realistic old workflow: open page, click, input, wait, get text."""
    wf = models.Workflow(name="legacy-realistic", url="https://example.com")
    db_session.add(wf)
    db_session.flush()

    # Old-style nodes (typical RPA flow)
    node_data = [
        ("navigate", 1, {}),
        ("click", 2, {"elementName": "search-btn"}),
        ("input", 3, {"elementName": "search-input", "text": "hello"}),
        ("waitForElement", 4, {"seconds": 3}),
        ("getText", 5, {"elementName": "result-title"}),
    ]

    nodes = []
    for ntype, order, extra_dict in node_data:
        import json
        node = models.WorkflowNode(
            workflow_id=wf.id,
            type=ntype,
            order=order,
            extra=json.dumps(extra_dict),
            enabled=1,
        )
        db_session.add(node)
        nodes.append(node)

    db_session.flush()

    loaded = (
        db_session.query(models.WorkflowNode)
        .filter(models.WorkflowNode.workflow_id == wf.id)
        .order_by(models.WorkflowNode.order)
        .all()
    )

    instructions = build_instructions(loaded)

    # navigate should produce an instruction (it's a modern type)
    # click, input, waitForElement, getText should all be covered by LEGACY_MAP
    assert len(instructions) == 5, \
        f"Expected 5 instructions, got {len(instructions)}: {[i['cmdType'] for i in instructions]}"

    # Verify order: original node order should be preserved
    type_order = [i["cmdType"] for i in instructions]
    assert type_order == ["navigate", "click", "input", "waitForElement", "getText"], \
        f"Unexpected instruction order: {type_order}"
