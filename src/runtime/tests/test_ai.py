"""AI router: invoke (透传模式)."""

from unittest.mock import patch, MagicMock


# ---------- /api/ai/invoke 透传 ----------

def test_invoke_without_dify_config(client, auth_headers):
    """Dify 未配置时 invoke 返回 400。"""
    r = client.post(
        "/api/ai/invoke", headers=auth_headers,
        json={"capability": "sentiment", "payload": {"query": "hi", "user": "u1"}},
    )
    assert r.status_code == 400


def test_invoke_unknown_capability(client, auth_headers, monkeypatch):
    """未知的 AI 能力返回 400。"""
    from src.config import runtime_config as config
    monkeypatch.setattr(config, "DIFY_BASE_URL", "http://dify.local")

    r = client.post(
        "/api/ai/invoke", headers=auth_headers,
        json={"capability": "nonexistent", "payload": {"query": "hi", "user": "u1"}},
    )
    assert r.status_code == 400


def test_invoke_no_api_key(client, auth_headers, monkeypatch):
    """能力存在但无 API Key 返回 400。"""
    from src.config import runtime_config as config
    monkeypatch.setattr(config, "DIFY_BASE_URL", "http://dify.local")
    monkeypatch.setitem(config.DIFY_APPS, "sentiment", {
        "api_key": "",
        "app_type": "chat",
    })

    r = client.post(
        "/api/ai/invoke", headers=auth_headers,
        json={"capability": "sentiment", "payload": {"query": "hi", "user": "u1"}},
    )
    assert r.status_code == 400


def test_invoke_validation_error(client, auth_headers, monkeypatch):
    """payload 校验失败返回 400。"""
    from src.config import runtime_config as config
    monkeypatch.setattr(config, "DIFY_BASE_URL", "http://dify.local")
    monkeypatch.setitem(config.DIFY_APPS, "sentiment", {
        "api_key": "test-key",
        "app_type": "text",
    })

    # text 类型缺少 query 和 inputs
    r = client.post(
        "/api/ai/invoke", headers=auth_headers,
        json={"capability": "sentiment", "payload": {"user": "u1"}},
    )
    assert r.status_code == 400
    assert "query 或 inputs" in r.json()["detail"]


def test_invoke_workflow_with_query(client, auth_headers, monkeypatch):
    """workflow 传了 query 返回 400。"""
    from src.config import runtime_config as config
    monkeypatch.setattr(config, "DIFY_BASE_URL", "http://dify.local")
    monkeypatch.setitem(config.DIFY_APPS, "batch", {
        "api_key": "test-key",
        "app_type": "workflow",
    })

    r = client.post(
        "/api/ai/invoke", headers=auth_headers,
        json={"capability": "batch", "payload": {"inputs": {}, "user": "u1", "query": "x"}},
    )
    assert r.status_code == 400
    assert "不支持 query" in r.json()["detail"]


@patch("src.runtime.routers.other_routers.get_dify_client")
def test_get_app_parameters(mock_get_dify, client, auth_headers, monkeypatch):
    """从 Dify 获取应用参数并解析为 input_schema。"""
    from src.config import runtime_config as config
    monkeypatch.setattr(config, "DIFY_BASE_URL", "http://dify.local")
    monkeypatch.setitem(config.DIFY_APPS, "sentiment", {
        "api_key": "test-key",
        "app_type": "chat",
    })

    mock_dify = MagicMock()
    mock_dify.is_configured.return_value = True
    mock_dify.get_parameters.return_value = {
        "user_input_form": [
            {"text-input": {"label": "评论内容", "variable": "comments", "required": True, "max_length": 100}},
            {"select": {"label": "语言", "variable": "lang", "required": False, "options": ["zh", "en"]}},
        ],
        "file_upload": {"image": {"enabled": True}},
    }
    mock_get_dify.return_value = mock_dify

    r = client.get("/api/ai/apps/sentiment/parameters", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    schema = data["input_schema"]
    assert "comments" in schema
    assert schema["comments"]["type"] == "string"
    assert schema["comments"]["required"] is True
    assert schema["comments"]["description"] == "评论内容"
    assert "lang" in schema
    assert schema["lang"]["required"] is False


def test_invoke_input_schema_validation(client, auth_headers, monkeypatch):
    """inputs 字段 schema 校验失败返回 400。"""
    from src.config import runtime_config as config
    monkeypatch.setattr(config, "DIFY_BASE_URL", "http://dify.local")
    monkeypatch.setitem(config.DIFY_APPS, "sentiment", {
        "api_key": "test-key",
        "app_type": "chat",
        "input_schema": {
            "comments": {"type": "array", "required": True},
            "title": {"type": "string", "required": False},
        },
    })

    # 缺少必填字段 comments
    r = client.post(
        "/api/ai/invoke", headers=auth_headers,
        json={
            "capability": "sentiment",
            "payload": {"query": "分析情感", "inputs": {"title": "xxx"}, "response_mode": "blocking", "user": "u1"},
        },
    )
    assert r.status_code == 400
    assert "comments" in r.json()["detail"]

    # 类型错误：comments 应为 array
    r = client.post(
        "/api/ai/invoke", headers=auth_headers,
        json={
            "capability": "sentiment",
            "payload": {
                "query": "分析情感",
                "inputs": {"comments": "not-array"},
                "response_mode": "blocking",
                "user": "u1",
            },
        },
    )
    assert r.status_code == 400
    assert "array" in r.json()["detail"]


@patch("src.runtime.routers.other_routers.get_dify_client")
def test_invoke_success(mock_get_dify, client, auth_headers, monkeypatch):
    """透传调用成功。"""
    from src.config import runtime_config as config
    monkeypatch.setattr(config, "DIFY_BASE_URL", "http://dify.local")
    monkeypatch.setitem(config.DIFY_APPS, "sentiment", {
        "api_key": "test-key",
        "app_type": "chat",
        "input_schema": {"comments": {"type": "array", "required": True}},
    })

    mock_dify = MagicMock()
    mock_dify.is_configured.return_value = True
    mock_dify.invoke.return_value = {"answer": "积极", "conversation_id": "c1"}
    mock_get_dify.return_value = mock_dify

    r = client.post(
        "/api/ai/invoke", headers=auth_headers,
        json={
            "capability": "sentiment",
            "payload": {
                "query": "分析情感",
                "inputs": {"comments": [{"content": "很好"}]},
                "response_mode": "blocking",
                "user": "u1"
            },
        },
    )
    assert r.status_code == 200
    assert r.json()["answer"] == "积极"
