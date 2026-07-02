"""End-to-end tests for the element_kind capture redesign (ADR 0006)."""

import pytest
import json

from src.repo import runtime_models as models
from src.service.elements_service import save_captured_element, build_element_tree, compute_selector_chain
from src.runtime.workflow.extension_emitter import build_instructions
from src.runtime.workflow.emitters._registry import _loc_call_by_name


@pytest.fixture
def workflow(db_session):
    wf = models.Workflow(name="test-capture-kind", url="http://example.com")
    db_session.add(wf)
    db_session.commit()
    db_session.refresh(wf)
    return wf


@pytest.mark.asyncio
async def test_save_anchor_element(workflow, db_session):
    el = await save_captured_element({
        "workflowId": workflow.id,
        "name": "comment_card",
        "elementKind": "anchor",
        "webSelector": "css:.comment-card",
        "selectorFamily": "css",
        "candidates": [{"syntax": "css:.comment-card", "family": "css", "score": 10, "matchCount": 5}],
    })
    assert el is not None
    assert el.element_kind == "anchor"
    assert el.anchor_mode == "none"
    db_element = db_session.query(models.WorkflowElement).filter_by(id=el.id).first()
    assert db_element.element_kind == "anchor"


@pytest.mark.asyncio
async def test_save_child_element_requires_anchor(workflow, db_session):
    # Saving a child without a matching anchor element must fail.
    result = await save_captured_element({
        "workflowId": workflow.id,
        "name": "author_name",
        "elementKind": "child",
        "webSelector": "css:.author",
        "relativeSelector": "css:.author",
        "anchorElementName": "comment_card",
        "selectorFamily": "css",
        "candidates": [],
    })
    assert result is None


@pytest.mark.asyncio
async def test_save_child_element_with_anchor(workflow, db_session):
    # First capture the anchor.
    anchor = await save_captured_element({
        "workflowId": workflow.id,
        "name": "comment_card",
        "elementKind": "anchor",
        "webSelector": "css:.comment-card",
        "selectorFamily": "css",
        "candidates": [],
    })
    assert anchor is not None

    # Then capture a child relative to the anchor.
    child = await save_captured_element({
        "workflowId": workflow.id,
        "name": "author_name",
        "elementKind": "child",
        "webSelector": "css:.author",
        "relativeSelector": "css:.author",
        "anchorElementName": "comment_card",
        "selectorFamily": "css",
        "candidates": [],
    })
    assert child is not None
    assert child.element_kind == "child"
    assert child.anchor_mode == "anchor-first"
    assert child.anchor_element_name == "comment_card"
    assert child.anchor_selector == "css:.comment-card"


@pytest.mark.asyncio
async def test_manual_child_element_uses_manual_mode(workflow, db_session):
    anchor = await save_captured_element({
        "workflowId": workflow.id,
        "name": "comment_card",
        "elementKind": "anchor",
        "webSelector": "css:.comment-card",
        "selectorFamily": "css",
        "candidates": [],
    })
    assert anchor is not None

    child = await save_captured_element({
        "workflowId": workflow.id,
        "name": "author_name",
        "elementKind": "child",
        "webSelector": "css:.author",
        "relativeSelector": "css:.author",
        "anchorElementName": "comment_card",
        "relativeManuallyEdited": True,
        "selectorFamily": "css",
        "candidates": [],
    })
    assert child is not None
    assert child.anchor_mode == "manual"


def test_extension_emitter_injects_relative_for_child(workflow, db_session):
    anchor = models.WorkflowElement(
        workflow_id=workflow.id,
        name="comment_card",
        element_kind="anchor",
        web_selector="css:.comment-card",
        drission_selector=".comment-card",
    )
    child = models.WorkflowElement(
        workflow_id=workflow.id,
        name="author_name",
        element_kind="child",
        web_selector="css:.author",
        drission_selector=".author",
        relative_selector="css:.author",
        anchor_selector="css:.comment-card",
        anchor_element_name="comment_card",
        anchor_mode="anchor-first",
    )
    db_session.add_all([anchor, child])
    db_session.commit()

    element_map = {"comment_card": anchor, "author_name": child}

    # Build a forEachElement loop over the anchor with a click on the child inside.
    loop_node = models.WorkflowNode(
        workflow_id=workflow.id,
        order=0,
        type="forEachElement",
        element_name="comment_card",
        extra=json.dumps({"itemVar": "item"}),
    )
    click_node = models.WorkflowNode(
        workflow_id=workflow.id,
        order=1,
        parent_id=1,  # placeholder; builder groups by parent_id
        type="click",
        element_name="author_name",
        extra="{}",
    )
    end_node = models.WorkflowNode(
        workflow_id=workflow.id,
        order=2,
        parent_id=1,
        type="endFor",
        extra="{}",
    )
    db_session.add_all([loop_node, click_node, end_node])
    db_session.commit()

    instructions = build_instructions([loop_node, click_node, end_node], element_map)
    assert len(instructions) == 1
    loop_inst = instructions[0]
    assert loop_inst["cmdType"] == "forEachElement"
    assert loop_inst["body"]
    click_inst = loop_inst["body"][0]
    assert click_inst["extra"].get("relativeLocator") == ".author"
    assert click_inst["extra"].get("relativeSelectorFamily") == "css"


def test_extension_emitter_nested_forEachElement_child_anchor(workflow, db_session):
    anchor = models.WorkflowElement(
        workflow_id=workflow.id,
        name="comment_card",
        element_kind="anchor",
        web_selector="css:.comment-card",
        drission_selector=".comment-card",
    )
    child = models.WorkflowElement(
        workflow_id=workflow.id,
        name="author_name",
        element_kind="child",
        relative_selector="css:.author",
        anchor_element_name="comment_card",
        anchor_mode="anchor-first",
    )
    grandchild = models.WorkflowElement(
        workflow_id=workflow.id,
        name="author_avatar",
        element_kind="child",
        relative_selector="css:.avatar",
        anchor_element_name="author_name",
        anchor_mode="anchor-first",
    )
    db_session.add_all([anchor, child, grandchild])
    db_session.commit()

    element_map = {"comment_card": anchor, "author_name": child, "author_avatar": grandchild}

    outer_loop = models.WorkflowNode(
        workflow_id=workflow.id,
        order=0,
        type="forEachElement",
        element_name="comment_card",
        extra=json.dumps({"itemVar": "item"}),
    )
    db_session.add(outer_loop)
    db_session.commit()
    db_session.refresh(outer_loop)

    inner_loop = models.WorkflowNode(
        workflow_id=workflow.id,
        order=1,
        parent_id=outer_loop.id,
        type="forEachElement",
        element_name="author_name",
        extra=json.dumps({"itemVar": "author"}),
    )
    db_session.add(inner_loop)
    db_session.commit()
    db_session.refresh(inner_loop)

    click_node = models.WorkflowNode(
        workflow_id=workflow.id,
        order=2,
        parent_id=inner_loop.id,
        type="click",
        element_name="author_avatar",
        extra="{}",
    )
    inner_end = models.WorkflowNode(
        workflow_id=workflow.id,
        order=3,
        parent_id=outer_loop.id,
        type="endFor",
        extra="{}",
    )
    outer_end = models.WorkflowNode(
        workflow_id=workflow.id,
        order=4,
        type="endFor",
        extra="{}",
    )
    db_session.add_all([click_node, inner_end, outer_end])
    db_session.commit()

    instructions = build_instructions(
        [outer_loop, inner_loop, click_node, inner_end, outer_end], element_map
    )
    assert len(instructions) == 1
    outer = instructions[0]
    assert outer["cmdType"] == "forEachElement"
    assert outer["locator"] == "css:.comment-card"
    assert outer["extra"].get("useRelative") is None

    inner = outer["body"][0]
    assert inner["cmdType"] == "forEachElement"
    assert inner["extra"].get("useRelative") is True
    assert inner["extra"].get("relativeLocator") == ".author"
    assert inner["extra"].get("relativeSelectorFamily") == "css"
    assert inner["locator"] == ".author"

    click_inst = inner["body"][0]
    assert click_inst["extra"].get("relativeLocator") == ".avatar"
    assert click_inst["extra"].get("relativeSelectorFamily") == "css"


def test_python_emitter_child_outside_loop_raises(workflow, db_session):
    anchor = models.WorkflowElement(
        workflow_id=workflow.id,
        name="comment_card",
        element_kind="anchor",
        web_selector="css:.comment-card",
        drission_selector=".comment-card",
    )
    child = models.WorkflowElement(
        workflow_id=workflow.id,
        name="author_name",
        element_kind="child",
        web_selector="css:.author",
        drission_selector=".author",
        relative_selector="css:.author",
        anchor_element_name="comment_card",
        anchor_mode="anchor-first",
    )
    db_session.add_all([anchor, child])
    db_session.commit()

    element_map = {"comment_card": anchor, "author_name": child}
    with pytest.raises(ValueError, match="child element"):
        _loc_call_by_name("author_name", {}, element_map)


def test_build_element_tree_nested_children(workflow, db_session):
    anchor = models.WorkflowElement(
        workflow_id=workflow.id,
        name="comment_card",
        element_kind="anchor",
        web_selector="css:.comment-card",
    )
    child = models.WorkflowElement(
        workflow_id=workflow.id,
        name="author_name",
        element_kind="child",
        relative_selector="css:.author",
        anchor_element_name="comment_card",
    )
    grandchild = models.WorkflowElement(
        workflow_id=workflow.id,
        name="author_avatar",
        element_kind="child",
        relative_selector="css:.avatar",
        anchor_element_name="author_name",
    )
    orphan = models.WorkflowElement(
        workflow_id=workflow.id,
        name="broken_child",
        element_kind="child",
        relative_selector="css:.broken",
        anchor_element_name="missing_anchor",
    )
    db_session.add_all([anchor, child, grandchild, orphan])
    db_session.commit()

    elements = db_session.query(models.WorkflowElement).filter_by(workflow_id=workflow.id).all()
    tree, orphans = build_element_tree(elements)

    assert len(tree) == 2  # anchor + orphan
    root_names = {node["name"] for node in tree}
    assert "comment_card" in root_names
    assert "broken_child" in root_names
    assert "broken_child" in orphans

    # Find comment_card node and verify nested children
    comment_node = next(node for node in tree if node["name"] == "comment_card")
    assert len(comment_node["children"]) == 1
    author_node = comment_node["children"][0]
    assert author_node["name"] == "author_name"
    assert len(author_node["children"]) == 1
    avatar_node = author_node["children"][0]
    assert avatar_node["name"] == "author_avatar"


def test_compute_selector_chain_nested(workflow, db_session):
    anchor = models.WorkflowElement(
        workflow_id=workflow.id,
        name="comment_card",
        element_kind="anchor",
        web_selector="css:.comment-card",
    )
    child = models.WorkflowElement(
        workflow_id=workflow.id,
        name="author_name",
        element_kind="child",
        relative_selector="css:.author",
        anchor_element_name="comment_card",
    )
    grandchild = models.WorkflowElement(
        workflow_id=workflow.id,
        name="author_avatar",
        element_kind="child",
        relative_selector="css:.avatar",
        anchor_element_name="author_name",
    )
    db_session.add_all([anchor, child, grandchild])
    db_session.commit()

    elements = db_session.query(models.WorkflowElement).filter_by(workflow_id=workflow.id).all()
    result = compute_selector_chain(elements, "author_avatar")

    assert result is not None
    assert result["name"] == "author_avatar"
    assert [node["name"] for node in result["chain"]] == ["comment_card", "author_name", "author_avatar"]
    assert result["combined_css"] == ".comment-card .author .avatar"


def test_compute_selector_chain_xpath(workflow, db_session):
    anchor = models.WorkflowElement(
        workflow_id=workflow.id,
        name="comment_card",
        element_kind="anchor",
        web_selector="xpath://div[contains(@class,'comment-card')]",
    )
    child = models.WorkflowElement(
        workflow_id=workflow.id,
        name="author_name",
        element_kind="child",
        relative_selector="xpath:.//span[contains(@class,'author')]",
        anchor_element_name="comment_card",
    )
    db_session.add_all([anchor, child])
    db_session.commit()

    elements = db_session.query(models.WorkflowElement).filter_by(workflow_id=workflow.id).all()
    result = compute_selector_chain(elements, "author_name")

    assert result is not None
    assert result["combined_xpath"] == "//div[contains(@class,'comment-card')]//span[contains(@class,'author')]"


def test_compute_selector_chain_cycle_raises(workflow, db_session):
    a = models.WorkflowElement(
        workflow_id=workflow.id,
        name="a",
        element_kind="child",
        relative_selector="css:.a",
        anchor_element_name="b",
    )
    b = models.WorkflowElement(
        workflow_id=workflow.id,
        name="b",
        element_kind="child",
        relative_selector="css:.b",
        anchor_element_name="a",
    )
    db_session.add_all([a, b])
    db_session.commit()

    elements = db_session.query(models.WorkflowElement).filter_by(workflow_id=workflow.id).all()
    with pytest.raises(ValueError, match="Cycle detected"):
        compute_selector_chain(elements, "a")
