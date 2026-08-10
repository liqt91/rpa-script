"""MCP resources（ADR-0011）：工作流与运行记录的只读视图。"""

import json

from fastmcp import FastMCP

from .client import get_client


def register(mcp: FastMCP) -> None:
    @mcp.resource("workflow://{wf_id}", mime_type="application/json")
    async def workflow_detail(wf_id: str) -> str:
        """工作流详情（含节点）。"""
        data = await get_client().get(f"/api/workflows/{wf_id}")
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.resource("workflow://{wf_id}/runs", mime_type="application/json")
    async def workflow_runs(wf_id: str) -> str:
        """工作流运行历史。"""
        data = await get_client().get(f"/api/workflows/{wf_id}/runs")
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.resource("run://{wf_id}/{run_id}/log", mime_type="application/json")
    async def run_log(wf_id: str, run_id: str) -> str:
        """某次运行的逐步日志事件。"""
        data = await get_client().get(f"/api/workflows/{wf_id}/runs/{run_id}/log")
        return json.dumps(data, ensure_ascii=False, indent=2)
