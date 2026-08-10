"""P3 运行控制工具（ADR-0011）。"""

from fastmcp import FastMCP

from ..client import get_client


def register(mcp: FastMCP) -> None:
    @mcp.tool(tags={"run"})
    async def run_workflow(
        wf_id: int,
        parameters: dict | None = None,
        initial_table_data: dict | None = None,
        run_id: str = "",
    ) -> dict:
        """通过浏览器扩展运行工作流（阻塞至完成，可能耗时数分钟）。

        parameters: {"变量名": "值"} 覆盖流程参数默认值。
        initial_table_data: {"columns": [...], "rows": [...]} 预置表格数据。
        返回 {success, runId, completedSteps, totalSteps, failedSteps, outputs, error}。
        运行进度可用 get_run_log(wf_id, runId) 查询。
        """
        payload: dict = {"parameters": parameters or {}}
        if initial_table_data:
            payload["initialTableData"] = initial_table_data
        params = {"run_id": run_id} if run_id else {}
        return await get_client().post(
            f"/api/workflows/{wf_id}/run/extension", json=payload, params=params
        )

    @mcp.tool(tags={"run"})
    async def run_status() -> dict:
        """运行容量与活跃运行概览（maxConcurrent/activeCount/availableSlots）。"""
        return await get_client().get("/api/workflows/runs/status")

    @mcp.tool(tags={"run"})
    async def list_active_runs() -> list:
        """列出当前正在运行的工作流（runId/workflowId/workflowName）。"""
        return await get_client().get("/api/workflows/runs/active")

    @mcp.tool(tags={"run"})
    async def pause_run(wf_id: int, run_id: str) -> dict:
        """暂停指定运行。"""
        return await get_client().post(f"/api/workflows/{wf_id}/run/{run_id}/pause")

    @mcp.tool(tags={"run"})
    async def resume_run(wf_id: int, run_id: str) -> dict:
        """恢复指定运行。"""
        return await get_client().post(f"/api/workflows/{wf_id}/run/{run_id}/resume")

    @mcp.tool(tags={"run"})
    async def stop_run(wf_id: int, run_id: str) -> dict:
        """停止指定运行。"""
        return await get_client().post(f"/api/workflows/{wf_id}/run/{run_id}/stop")

    @mcp.tool(tags={"run"})
    async def stop_all_runs() -> dict:
        """停止全部正在运行的工作流。"""
        return await get_client().post("/api/workflows/runs/active/stop")
