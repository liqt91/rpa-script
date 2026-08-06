"""
Tests for extension handler resolution with the active command set.

Legacy commands were removed (see ADR-0010 follow-up); only commands registered
in commands/extension_commands/ resolve to a runtime.
"""

from src.repo import models
from src.runtime.workflow.extension_emitter import build_instructions, _get_extension_runtime

# Active extension commands (commands/extension_commands/)
ACTIVE_EXTENSION = [
    "clickElement", "closeBrowser", "closeTab", "getElementLink", "getText",
    "hover", "inputElement", "launchBrowser", "navigate", "newTab",
    "pressKey", "scrollIntoView", "switchTab", "takeScreenshot", "waitForElement",
]


def test_active_handlers_all_resolve():
    """Every active extension command resolves to a valid runtime."""
    for htype in ACTIVE_EXTENSION:
        runtime = _get_extension_runtime(htype)
        assert runtime is not None, f"'{htype}' not found in registry"
        handler = runtime.get("handler")
        assert handler, f"'{htype}' has no handler name: {runtime}"


def test_active_handlers_produce_instructions(db_session):
    """All active commands must produce build_instructions output."""
    wf = models.Workflow(name="command-set-test", url="https://example.com")
    db_session.add(wf)
    db_session.flush()

    for i, htype in enumerate(ACTIVE_EXTENSION):
        node = models.WorkflowNode(
            workflow_id=wf.id, cmd=htype, order=i,
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
    assert len(instructions) == len(ACTIVE_EXTENSION), \
        f"Expected {len(ACTIVE_EXTENSION)} instructions, got {len(instructions)}"

    type_order = [i["cmdType"] for i in instructions]
    assert type_order == ACTIVE_EXTENSION, \
        f"Order mismatch: {type_order}"


def test_legacy_types_no_longer_resolve():
    """Removed legacy command names must not resolve to a runtime."""
    for old_type in ("click", "input", "getAttr", "getHtml", "getValue",
                     "scrollToBottom", "inputAndPressEnter", "executeJs"):
        assert _get_extension_runtime(old_type) is None, \
            f"legacy command still resolves: {old_type!r}"


def test_realistic_workflow(db_session):
    """New-command workflow: navigate, input+Enter, click, getText — all emit."""
    import json
    wf = models.Workflow(name="command-realistic", url="https://example.com")
    db_session.add(wf)
    db_session.flush()

    node_data = [
        ("navigate", 1, {"url": "https://example.com"}),
        ("inputElement", 2, {"text": "hello", "pressEnter": True}),
        ("clickElement", 3, {}),
        ("getText", 4, {}),
    ]
    for ntype, order, extra_dict in node_data:
        db_session.add(models.WorkflowNode(
            workflow_id=wf.id, cmd=ntype, order=order,
            extra=json.dumps(extra_dict), enabled=1,
        ))
    db_session.flush()

    loaded = (
        db_session.query(models.WorkflowNode)
        .filter(models.WorkflowNode.workflow_id == wf.id)
        .order_by(models.WorkflowNode.order)
        .all()
    )

    instructions = build_instructions(loaded)
    assert [i["cmdType"] for i in instructions] == [
        "navigate", "inputElement", "clickElement", "getText",
    ]
    assert instructions[1]["extra"].get("pressEnter") is True
