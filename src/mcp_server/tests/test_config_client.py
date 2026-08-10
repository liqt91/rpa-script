"""src/mcp_server 配置与客户端单元测试（不依赖真实后端）。"""

import asyncio

import httpx
import pytest

from src.mcp_server import config
from src.mcp_server.client import RpaApiError, RpaClient


def test_enabled_tool_groups_default(monkeypatch):
    monkeypatch.delenv("RPA_MCP_TOOLS", raising=False)
    assert config.enabled_tool_groups() == {"read", "write", "run", "browser"}


def test_enabled_tool_groups_whitelist(monkeypatch):
    monkeypatch.setenv("RPA_MCP_TOOLS", "read, browser ,,")
    assert config.enabled_tool_groups() == {"read", "browser"}


def test_backend_url_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("RPA_BACKEND_URL", "http://localhost:8000/")
    assert config.backend_url() == "http://localhost:8000"


def test_checked_maps_error_detail():
    req = httpx.Request("GET", "http://x")
    resp = httpx.Response(409, json={"detail": "没有浏览器扩展连接"}, request=req)
    with pytest.raises(RpaApiError, match="409"):
        RpaClient._checked(resp)


def test_checked_passthrough_json():
    req = httpx.Request("GET", "http://x")
    resp = httpx.Response(200, json={"status": "ok"}, request=req)
    assert RpaClient._checked(resp) == {"status": "ok"}


def test_missing_auth_config_raises(monkeypatch):
    monkeypatch.delenv("RPA_API_TOKEN", raising=False)
    monkeypatch.delenv("RPA_USERNAME", raising=False)
    monkeypatch.delenv("RPA_PASSWORD", raising=False)
    client = RpaClient()

    async def scenario():
        await client._ensure_token()

    with pytest.raises(RpaApiError, match="未配置认证"):
        asyncio.run(scenario())
