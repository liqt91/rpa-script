"""MCP server 工具注册测试（不依赖真实后端，仅验证装配）。"""

import asyncio

from src.mcp_server import server


def _tool_names(mcp) -> set[str]:
    tools = asyncio.run(mcp.list_tools())
    return {t.name for t in tools}


def test_default_registers_all_groups(monkeypatch):
    monkeypatch.delenv("RPA_MCP_TOOLS", raising=False)
    mcp = server.create_server()
    names = _tool_names(mcp)
    expected = {
        # P1 read
        "health_check", "list_workflows", "get_workflow", "list_workflow_nodes",
        "list_workflow_elements", "get_element_chain", "list_commands",
        "list_runs", "get_run_log", "get_run_table",
        # P2 write
        "create_workflow", "update_workflow", "delete_workflow",
        "save_workflow_nodes", "add_node", "update_node", "delete_node",
        "reorder_nodes",
        # P3 run
        "run_workflow", "run_status", "list_active_runs",
        "pause_run", "resume_run", "stop_run", "stop_all_runs",
        # P5 browser
        "list_browser_commands", "browser_exec", "browser_navigate",
        "browser_current_url", "browser_click", "browser_get_text",
        "browser_input", "browser_element_exists",
    }
    assert expected <= names


def test_group_whitelist(monkeypatch):
    monkeypatch.setenv("RPA_MCP_TOOLS", "read")
    mcp = server.create_server()
    names = _tool_names(mcp)
    assert "health_check" in names
    assert "create_workflow" not in names
    assert "run_workflow" not in names
    assert "browser_exec" not in names


def test_module_level_server_exists():
    assert server.mcp is not None
