import pytest
import json
from src.repo import models
from src.runtime.workflow.extension_runner import run_workflow_extension
from src.runtime.workflow.extension_emitter import _match_brackets
from src.repo.runtime_models import WorkflowNode
from src.providers.workflow_lock import workflow_lock


@pytest.fixture
def workflow_id(client, auth_headers):
    r = client.post(
        "/api/workflows",
        json={"name": "参数测试", "url": "${postUrl}"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_workflow_parameters_crud(client, auth_headers, workflow_id):
    # GET returns empty list by default
    r = client.get(f"/api/workflows/{workflow_id}", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["parameters"] == []

    # Update parameters
    params = [{"name": "postUrl", "label": "帖子链接", "type": "text", "default": "https://example.com"}]
    r = client.put(
        f"/api/workflows/{workflow_id}",
        json={"parameters": params},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["parameters"] == params

    # Stored in DB as JSON string
    db = models.SessionLocal()
    try:
        wf = db.get(models.Workflow, workflow_id)
        assert json.loads(wf.parameters) == params
    finally:
        db.close()


@pytest.mark.anyio
async def test_run_injects_initial_parameters(client, auth_headers, workflow_id):
    params = [{"name": "postUrl", "label": "帖子链接", "type": "text", "default": "https://default.example.com"}]
    client.put(
        f"/api/workflows/{workflow_id}",
        json={"parameters": params},
        headers=auth_headers,
    )

    # Add a local setVar node that uses the parameter
    r = client.post(
        f"/api/workflows/{workflow_id}/nodes",
        json={
            "type": "setVar",
            "order": 1,
            "extra": {"name": "targetUrl", "value": "${postUrl}", "valueType": "string"},
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text

    db = models.SessionLocal()
    try:
        wf = db.get(models.Workflow, workflow_id)
        nodes = (
            db.query(models.WorkflowNode)
            .filter(models.WorkflowNode.workflow_id == workflow_id)
            .order_by(models.WorkflowNode.order)
            .all()
        )
        result = await run_workflow_extension(
            wf, nodes,
            initial_parameters={"postUrl": "https://post.example.com/123"},
        )
        assert result["success"] is True, result
        set_var_result = [
            x for x in result.get("results", [])
            if x.get("result", {}).get("setVar") == "targetUrl"
        ]
        assert set_var_result, result
        assert set_var_result[0]["result"]["value"] == "https://post.example.com/123"
    finally:
        db.close()


def test_match_brackets_pairs_end_try_with_try_not_catch():
    """Regression: endTry must close the original try, not the catch branch."""
    nodes = [
        WorkflowNode(id=1, order=1, type="try", workflow_id=1),
        WorkflowNode(id=2, order=2, type="log", workflow_id=1),
        WorkflowNode(id=3, order=3, type="catch", workflow_id=1),
        WorkflowNode(id=4, order=4, type="log", workflow_id=1),
        WorkflowNode(id=5, order=5, type="endTry", workflow_id=1),
    ]
    container_close, container_branch = _match_brackets(nodes)
    assert container_close == {1: 5}, f"endTry should close try(1), got {container_close}"
    assert container_branch == {1: 3}, f"catch should be branch of try(1), got {container_branch}"


def test_match_brackets_if_else_pairs_with_if():
    """else must not become the container that endIf closes."""
    nodes = [
        WorkflowNode(id=1, order=1, type="ifElementVisible", workflow_id=1),
        WorkflowNode(id=2, order=2, type="log", workflow_id=1),
        WorkflowNode(id=3, order=3, type="else", workflow_id=1),
        WorkflowNode(id=4, order=4, type="log", workflow_id=1),
        WorkflowNode(id=5, order=5, type="endIf", workflow_id=1),
    ]
    container_close, container_branch = _match_brackets(nodes)
    assert container_close == {1: 5}, f"endIf should close if(1), got {container_close}"
    assert container_branch == {1: 3}, f"else should be branch of if(1), got {container_branch}"


def test_match_brackets_nested_if_inside_try():
    """Nested if/else inside try must not confuse the outer try/catch pairing."""
    nodes = [
        WorkflowNode(id=1, order=1, type="try", workflow_id=1),
        WorkflowNode(id=2, order=2, type="log", workflow_id=1),
        WorkflowNode(id=3, order=3, type="ifElementVisible", workflow_id=1),
        WorkflowNode(id=4, order=4, type="log", workflow_id=1),
        WorkflowNode(id=5, order=5, type="else", workflow_id=1),
        WorkflowNode(id=6, order=6, type="log", workflow_id=1),
        WorkflowNode(id=7, order=7, type="endIf", workflow_id=1),
        WorkflowNode(id=8, order=8, type="catch", workflow_id=1),
        WorkflowNode(id=9, order=9, type="log", workflow_id=1),
        WorkflowNode(id=10, order=10, type="endTry", workflow_id=1),
    ]
    container_close, container_branch = _match_brackets(nodes)
    assert container_close == {3: 7, 1: 10}, f"unexpected close map: {container_close}"
    assert container_branch == {3: 5, 1: 8}, f"unexpected branch map: {container_branch}"


@pytest.mark.anyio
async def test_workflow_concurrency_lock_blocks_second_run(client, auth_headers, workflow_id, monkeypatch):
    """When the global workflow lock is held, a second run/extension request returns 503."""
    r = client.post(
        f"/api/workflows/{workflow_id}/nodes",
        json={
            "type": "setVar",
            "order": 1,
            "extra": {"name": "x", "value": "1", "valueType": "number"},
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text

    # Shorten the server-side lock timeout so the test does not wait 30s.
    import src.runtime.routers.workflows_router as router_module
    monkeypatch.setattr(router_module, "WORKFLOW_LOCK_TIMEOUT_SECONDS", 0.05)

    async with workflow_lock():
        r = client.post(
            f"/api/workflows/{workflow_id}/run/extension",
            json={},
            headers=auth_headers,
        )
        assert r.status_code == 503, r.text
        assert r.headers.get("retry-after") == "1"
        assert "capacity full" in r.json()["detail"].lower()
