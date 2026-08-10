"""MCP 服务器入口（ADR-0011）：默认 stdio 传输。

用法:
    python -m src.mcp_server.server      # stdio（Claude Desktop / Claude Code）
    python -m src.mcp_server.http        # streamable HTTP（独立进程）

环境变量见 src/mcp_server/config.py（RPA_BACKEND_URL / RPA_API_TOKEN 等）。
"""

from fastmcp import FastMCP

from . import config, resources
from .tools import browser, run_control, workflow_edit, workflow_read


def create_server() -> FastMCP:
    mcp = FastMCP("rpa-script")
    groups = config.enabled_tool_groups()
    if "read" in groups:
        workflow_read.register(mcp)
        resources.register(mcp)
    if "write" in groups:
        workflow_edit.register(mcp)
    if "run" in groups:
        run_control.register(mcp)
    if "browser" in groups:
        browser.register(mcp)
    return mcp


mcp = create_server()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
