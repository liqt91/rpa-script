"""
Handler 单元测试辅助工具。

使用方式：
    from .handler_test_utils import make_runner, run_handler

    runner = make_runner(vars={"a": "hello"})
    result = await run_handler("setVar", {"name": "{{x}}", "value": "42", "valueType": "int-number"}, runner)
    assert runner.vars["x"] == 42
"""

import asyncio
from unittest.mock import MagicMock, AsyncMock


class _MockRunner:
    """模拟 ExtensionRunner，只提供 handler 需要的接口。"""

    def __init__(self, vars=None, table_data=None):
        self.vars = dict(vars or {})
        self._table_data = dict(table_data or {"columns": [], "rows": []})
        self.completed = 0
        self.failed_steps = []
        self.results = []
        self.client_id = "mock-client"
        self.run_id = "mock-run"
        self.workflow_id = 1
        self._stopped = False
        self._run_started_sent = True
        self._emit = AsyncMock()
        self._send_and_wait = AsyncMock()
        self._ensure_connected = AsyncMock()

    def _ensure_table_data(self):
        if not isinstance(self._table_data, dict):
            self._table_data = {"columns": [], "rows": []}
        self._table_data.setdefault("columns", [])
        self._table_data.setdefault("rows", [])
        return self._table_data

    def _resolve_loop_context(self, extra):
        return None


def make_runner(vars=None, table=None):
    """创建模拟 runner，可预设变量和表格数据。"""
    return _MockRunner(vars=vars, table_data=table)


async def run_handler(cmd_type, extra, runner=None, step_id="s1"):
    """执行一个 backend handler 并返回结果。

    Args:
        cmd_type: 指令类型，如 "setVar" "writeTableRow"
        extra: 参数字典，如 {"name": "{{x}}", "value": "42"}
        runner: 模拟 runner，不传则自动创建
        step_id: 步骤 ID

    Returns:
        runner 实例（含 results、vars 等结果）
    """
    from src.runtime.workflow.extension_runner import LOCAL_HANDLERS

    if runner is None:
        runner = make_runner()

    handler = LOCAL_HANDLERS.get(cmd_type)
    if handler is None:
        raise ValueError(f"Unknown handler: {cmd_type}")

    instr = {"extra": extra, "stepId": step_id, "nodeId": 1, "cmdType": cmd_type}
    success = await handler(runner, cmd_type, step_id, instr)
    if not success:
        # Collect error info
        raise RuntimeError(f"Handler {cmd_type} failed: {runner.failed_steps}")
    return runner


async def run_sequence(steps, vars=None, table=None):
    """按顺序执行多个 handler。

    Args:
        steps: [(cmd_type, extra), ...] 列表
        vars: 初始变量
        table: 初始表格

    Returns:
        runner 实例

    例:
        runner = await run_sequence([
            ("setVar", {"name": "{{x}}", "value": "10", "valueType": "int-number"}),
            ("setVar", {"name": "{{y}}", "value": "20", "valueType": "int-number"}),
            ("log", {"message": "x={{x}}, y={{y}}"}),
        ])
        assert runner.vars["x"] == 10
        assert runner.vars["y"] == 20
    """
    runner = make_runner(vars=vars, table=table)
    for i, (cmd_type, extra) in enumerate(steps):
        await run_handler(cmd_type, extra, runner, step_id=f"s{i+1}")
    return runner
