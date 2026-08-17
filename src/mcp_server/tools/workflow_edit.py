"""P2 工作流创作工具（ADR-0011）。"""

from fastmcp import FastMCP

from ..client import RpaApiError, get_client


def register(mcp: FastMCP) -> None:
    @mcp.tool(tags={"write"})
    async def import_workflow(
        name: str,
        nodes: list,
        description: str = "",
        url: str = "",
        framework: str = "",
        parameters: list | None = None,
        elements: list | None = None,
    ) -> dict:
        """原子导入完整工作流定义（推荐构建方式，一次调用替代逐节点创建）。

        nodes: [{cmd, action?, element_name?, parent_id?, order?, extra?}]；
        新节点用字符串 temp_id 占位并在 parent_id 中引用，后端自动解析为真实 id。
        elements: [{name, selector|web_selector, selector_family?, ...}] 宽松 schema。
        任一步失败整体回滚。返回 {id, name, ...}。
        """
        payload = {
            "name": name,
            "description": description,
            "url": url,
            "framework": framework,
            "parameters": parameters or [],
            "nodes": nodes,
            "elements": elements or [],
        }
        return await get_client().post("/api/workflows/import", json=payload)

    @mcp.tool(tags={"write"})
    async def create_workflow(
        name: str,
        description: str = "",
        url: str = "",
        framework: str = "",
        parameters: list | None = None,
    ) -> dict:
        """创建工作流。parameters 形如 [{name, default, direction: in|out}]。"""
        payload = {
            "name": name,
            "description": description,
            "url": url,
            "framework": framework,
            "parameters": parameters or [],
        }
        return await get_client().post("/api/workflows", json=payload)

    @mcp.tool(tags={"write"})
    async def update_workflow(
        wf_id: int,
        name: str | None = None,
        description: str | None = None,
        url: str | None = None,
        framework: str | None = None,
        parameters: list | None = None,
    ) -> dict:
        """更新工作流元数据；仅传入需要修改的字段。"""
        payload = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if url is not None:
            payload["url"] = url
        if framework is not None:
            payload["framework"] = framework
        if parameters is not None:
            payload["parameters"] = parameters
        return await get_client().put(f"/api/workflows/{wf_id}", json=payload)

    @mcp.tool(tags={"write"})
    async def delete_workflow(wf_id: int) -> dict:
        """删除工作流（级联删除节点与元素库）。"""
        return await get_client().delete(f"/api/workflows/{wf_id}")

    @mcp.tool(tags={"write"})
    async def save_workflow_nodes(wf_id: int, nodes: list) -> list:
        """批量整体替换工作流节点。

        每个节点: {id?|temp_id?, cmd, action?, element_name?, parent_id?,
        order?, enabled?, extra?}。新节点用 temp_id 占位并在 parent_id 中引用，
        后端自动解析为真实 id；payload 中未出现的既有节点会被删除。
        """
        return await get_client().put(f"/api/workflows/{wf_id}/nodes/batch", json=nodes)

    @mcp.tool(tags={"write"})
    async def add_node(
        wf_id: int,
        cmd: str,
        action: str | None = None,
        element_name: str | None = None,
        parent_id: int | None = None,
        order: int = 0,
        extra: dict | None = None,
        enabled: bool | None = None,
    ) -> dict:
        """追加单个节点；order=0 时自动排到末尾。"""
        payload = {
            "cmd": cmd,
            "action": action,
            "element_name": element_name,
            "parent_id": parent_id,
            "order": order,
            "extra": extra or {},
            "enabled": enabled,
        }
        return await get_client().post(f"/api/workflows/{wf_id}/nodes", json=payload)

    @mcp.tool(tags={"write"})
    async def update_node(
        wf_id: int,
        node_id: int,
        cmd: str | None = None,
        action: str | None = None,
        element_name: str | None = None,
        parent_id: int | None = None,
        order: int | None = None,
        extra: dict | None = None,
        enabled: bool | None = None,
    ) -> dict:
        """更新单个节点；仅传入需要修改的字段（内部先取现状再整体提交）。"""
        client = get_client()
        nodes = await client.get(f"/api/workflows/{wf_id}/nodes")
        cur = next((n for n in nodes if n.get("id") == node_id), None)
        if cur is None:
            raise RpaApiError(f"节点不存在: wf={wf_id} node={node_id}")
        payload = {
            "cmd": cmd if cmd is not None else cur.get("cmd"),
            "action": action if action is not None else cur.get("action"),
            "element_name": (
                element_name if element_name is not None else cur.get("element_name")
            ),
            "parent_id": parent_id if parent_id is not None else cur.get("parent_id"),
            "order": order if order is not None else cur.get("order", 0),
            "extra": extra if extra is not None else (cur.get("extra") or {}),
            "enabled": enabled if enabled is not None else cur.get("enabled", 1),
        }
        return await client.put(f"/api/workflows/{wf_id}/nodes/{node_id}", json=payload)

    @mcp.tool(tags={"write"})
    async def delete_node(wf_id: int, node_id: int) -> dict:
        """删除节点（级联删除其子节点）。"""
        return await get_client().delete(f"/api/workflows/{wf_id}/nodes/{node_id}")

    @mcp.tool(tags={"write"})
    async def reorder_nodes(wf_id: int, orders: list) -> dict:
        """调整节点顺序/层级。orders: [{id, order, parent_id?}, ...]。"""
        return await get_client().post(f"/api/workflows/{wf_id}/nodes/reorder", json=orders)
