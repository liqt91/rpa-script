import pytest
import json
from src.repo import models
from src.runtime.workflow.extension_runner import run_workflow_extension


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
        nodes = db.query(models.WorkflowNode).filter(models.WorkflowNode.workflow_id == workflow_id).order_by(models.WorkflowNode.order).all()
        result = await run_workflow_extension(
            wf, nodes,
            initial_parameters={"postUrl": "https://post.example.com/123"},
        )
        assert result["success"] is True, result
        set_var_result = [x for x in result.get("results", []) if x.get("result", {}).get("setVar") == "targetUrl"]
        assert set_var_result, result
        assert set_var_result[0]["result"]["value"] == "https://post.example.com/123"
    finally:
        db.close()
