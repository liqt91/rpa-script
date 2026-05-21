"""Dify client unit tests (透传模式)."""

from unittest.mock import patch, MagicMock

from src.runtime.dify_client import DifyClient, _validate_payload


def test_dify_client_not_configured():
    from unittest.mock import patch
    with patch("src.runtime.dify_client.config.DIFY_BASE_URL", ""):
        client = DifyClient()
        assert not client.is_configured()


def test_list_capabilities_empty():
    """无配置时返回空列表。"""
    client = DifyClient()
    assert client.list_capabilities() == []


# ---------- 参数校验 ----------

def test_validate_payload_text_missing_user():
    errors = _validate_payload("text", {"query": "hi"})
    assert "缺少必填字段: user" in errors


def test_validate_payload_text_has_conversation_id():
    errors = _validate_payload("text", {"query": "hi", "user": "u1", "conversation_id": "x"})
    assert "text 类型不支持 conversation_id 字段" in errors


def test_validate_payload_text_empty():
    errors = _validate_payload("text", {"user": "u1"})
    assert "text 类型需要 query 或 inputs 至少一个非空" in errors


def test_validate_payload_workflow_no_inputs():
    errors = _validate_payload("workflow", {"user": "u1"})
    assert "workflow 类型需要 inputs 字段" in errors


def test_validate_payload_workflow_has_query():
    errors = _validate_payload("workflow", {"inputs": {}, "user": "u1", "query": "x"})
    assert "workflow 类型不支持 query 字段" in errors


def test_validate_payload_chat_ok():
    errors = _validate_payload("chat", {"query": "hi", "user": "u1"})
    assert errors == []


def test_validate_payload_workflow_ok():
    errors = _validate_payload("workflow", {"inputs": {"a": 1}, "user": "u1"})
    assert errors == []


# ---------- invoke ----------

@patch("src.runtime.dify_client.httpx.Client")
def test_invoke_text(mock_client_class):
    """透传调用 text 类型。"""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "answer": "分析结果",
        "metadata": {"usage": {"total_tokens": 10}},
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__enter__.return_value = mock_client

    client = DifyClient()
    client.base_url = "http://dify.local"

    app_cfg = {"api_key": "test-key", "app_type": "text"}
    payload = {"query": "分析情感", "inputs": {}, "response_mode": "blocking", "user": "u1"}
    result = client.invoke(app_cfg, payload)

    assert result["answer"] == "分析结果"
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "http://dify.local/v1/completion-messages"
    assert call_args[1]["headers"]["Authorization"] == "Bearer test-key"
    assert call_args[1]["json"]["query"] == "分析情感"


@patch("src.runtime.dify_client.httpx.Client")
def test_invoke_workflow(mock_client_class):
    """透传调用 workflow 类型。"""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": {"outputs": {"result": "done"}, "status": "succeeded"},
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__enter__.return_value = mock_client

    client = DifyClient()
    client.base_url = "http://dify.local"

    app_cfg = {"api_key": "test-key", "app_type": "workflow"}
    payload = {"inputs": {"text": "hello"}, "response_mode": "blocking", "user": "u1"}
    result = client.invoke(app_cfg, payload)

    assert result["data"]["outputs"]["result"] == "done"
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "http://dify.local/v1/workflows/run"


@patch("src.runtime.dify_client.httpx.Client")
def test_invoke_chat(mock_client_class):
    """透传调用 chat 类型。"""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "answer": "回答",
        "conversation_id": "conv-1",
        "message_id": "msg-1",
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post.return_value = mock_response
    mock_client_class.return_value.__enter__.return_value = mock_client

    client = DifyClient()
    client.base_url = "http://dify.local"

    app_cfg = {"api_key": "test-key", "app_type": "chat"}
    payload = {"query": "hi", "inputs": {}, "response_mode": "blocking", "user": "u1"}
    result = client.invoke(app_cfg, payload)

    assert result["answer"] == "回答"
    assert result["conversation_id"] == "conv-1"
