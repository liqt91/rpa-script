"""单指令沙盒测试 API。"""

import pytest


@pytest.mark.asyncio
async def test_sandbox_setvar(client, auth_headers):
    """POST /api/commands/definitions/{type}/test 直接执行 backend handler。"""
    r = client.post(
        "/api/commands/definitions/setVar/test",
        headers=auth_headers,
        json={"extra": {"name": "{{x}}", "value": "42", "valueType": "int-number"}},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["vars"]["x"] == 42
    assert data["results"][0]["result"]["setVar"] == "x"
    assert data["error"] is None


@pytest.mark.asyncio
async def test_sandbox_unknown_handler(client, auth_headers):
    """不存在的指令返回 404。"""
    r = client.post(
        "/api/commands/definitions/nonexistent/test",
        headers=auth_headers,
        json={"extra": {}},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_sandbox_error_handling(client, auth_headers):
    """handler 抛异常时返回 success=False 和错误信息。"""
    r = client.post(
        "/api/commands/definitions/setVar/test",
        headers=auth_headers,
        json={"extra": {"name": "{{x}}", "value": "=1/0", "valueType": "any-expr"}},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is False
    assert data["error"] is not None


@pytest.mark.asyncio
async def test_get_test_templates(client, auth_headers):
    """GET /api/commands/definitions/{type}/test-templates 返回指令的测试模板。"""
    r = client.get("/api/commands/definitions/setVar/test-templates", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["cmd"] == "setVar"
    assert len(data["templates"]) >= 1
    tpl = data["templates"][0]
    assert tpl["name"] == "设置数字变量"
    assert tpl["params"]["varName"] == "count"
    assert len(tpl["nodes"]) == 2


@pytest.mark.asyncio
async def test_run_test_flow(client, auth_headers):
    """POST /api/commands/definitions/{type}/test-flow 执行测试流程。"""
    r = client.post(
        "/api/commands/definitions/setVar/test-flow",
        headers=auth_headers,
        json={
            "nodes": [
                {"cmd": "setVar", "order": 1, "extra": {"name": "{{x}}", "value": "42", "valueType": "int-number"}},
                {"cmd": "log", "order": 2, "extra": {"message": "x = {{x}}"}},
            ],
            "vars": {},
            "clientId": None,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["results"][0]["result"]["setVar"] == "x"
    assert data["results"][0]["result"]["value"] == 42
    assert data["error"] is None


@pytest.mark.asyncio
async def test_run_test_flow_empty_nodes(client, auth_headers):
    """nodes 为空时返回 400。"""
    r = client.post(
        "/api/commands/definitions/setVar/test-flow",
        headers=auth_headers,
        json={"nodes": [], "vars": {}},
    )
    assert r.status_code == 400
