"""P1 工作流只读工具（ADR-0011）。"""

from fastmcp import FastMCP

from ..client import get_client


def register(mcp: FastMCP) -> None:
    @mcp.tool(tags={"read"})
    async def health_check() -> dict:
        """后端健康检查，返回 {status: 'ok'} 表示后端可达。"""
        return await get_client().get("/health", auth=False)

    @mcp.tool(tags={"read"})
    async def list_workflows() -> list:
        """列出所有工作流（id/名称/描述/url 等）。"""
        return await get_client().get("/api/workflows")

    @mcp.tool(tags={"read"})
    async def get_workflow(wf_id: int) -> dict:
        """获取工作流详情（含节点列表与参数定义）。"""
        return await get_client().get(f"/api/workflows/{wf_id}")

    @mcp.tool(tags={"read"})
    async def list_workflow_nodes(wf_id: int) -> list:
        """列出工作流的全部节点（含容器层级 parent_id）。"""
        return await get_client().get(f"/api/workflows/{wf_id}/nodes")

    @mcp.tool(tags={"read"})
    async def list_workflow_elements(wf_id: int) -> list:
        """列出工作流元素库（选择器、锚点、截图等）。"""
        return await get_client().get(f"/api/workflows/{wf_id}/elements")

    @mcp.tool(tags={"read"})
    async def get_element_chain(wf_id: int, name: str) -> dict:
        """查询元素的有效选择器链（child-as-anchor 逐层解析）。"""
        return await get_client().get(f"/api/workflows/{wf_id}/elements/{name}/chain")

    @mcp.tool(tags={"read"})
    async def list_commands() -> dict:
        """列出工作流编辑器可用指令目录（含容器/分支类型）。"""
        return await get_client().get("/api/workflows/commands")

    @mcp.tool(tags={"read"})
    async def list_runs(wf_id: int | None = None, limit: int = 50) -> list:
        """列出运行历史；wf_id 为空则跨工作流查询最近记录。"""
        client = get_client()
        if wf_id is None:
            return await client.get("/api/workflows/runs", params={"limit": limit})
        return await client.get(f"/api/workflows/{wf_id}/runs", params={"limit": limit})

    @mcp.tool(tags={"read"})
    async def get_run_log(wf_id: int, run_id: str) -> dict:
        """读取某次运行的逐步日志事件（可用于进度查询/排错）。"""
        return await get_client().get(f"/api/workflows/{wf_id}/runs/{run_id}/log")

    @mcp.tool(tags={"read"})
    async def get_run_table(wf_id: int, run_id: str) -> dict:
        """读取某次运行产出的表格数据（columns/rows）。"""
        return await get_client().get(f"/api/workflows/{wf_id}/runs/{run_id}/table")
