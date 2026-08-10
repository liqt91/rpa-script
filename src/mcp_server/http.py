"""streamable HTTP 传输入口（ADR-0011）：独立进程，不改动主后端。

用法:
    python -m src.mcp_server.http
监听地址由 RPA_MCP_HTTP_HOST / RPA_MCP_HTTP_PORT 控制（默认 127.0.0.1:8765），
MCP endpoint 为 http://host:port/mcp。
"""

from . import config
from .server import create_server


def main() -> None:
    mcp = create_server()
    mcp.run(
        transport="streamable-http",
        host=config.http_host(),
        port=config.http_port(),
        path="/mcp",
    )


if __name__ == "__main__":
    main()
