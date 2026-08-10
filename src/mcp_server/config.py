"""MCP 服务器配置（ADR-0011）：全部来自环境变量，不依赖其他层。"""

import os


def backend_url() -> str:
    return os.environ.get("RPA_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def api_token() -> str:
    return os.environ.get("RPA_API_TOKEN", "")


def username() -> str:
    return os.environ.get("RPA_USERNAME", "")


def password() -> str:
    return os.environ.get("RPA_PASSWORD", "")


def enabled_tool_groups() -> set[str]:
    """RPA_MCP_TOOLS=read,write,run,browser 白名单；空则全部启用。"""
    raw = os.environ.get("RPA_MCP_TOOLS", "").strip()
    if not raw:
        return {"read", "write", "run", "browser"}
    return {g.strip() for g in raw.split(",") if g.strip()}


def http_host() -> str:
    return os.environ.get("RPA_MCP_HTTP_HOST", "127.0.0.1")


def http_port() -> int:
    return int(os.environ.get("RPA_MCP_HTTP_PORT", "8765"))
