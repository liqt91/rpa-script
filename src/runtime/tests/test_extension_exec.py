"""extension/exec 与 extension/commands 端点测试（ADR-0011）。

模式同 test_verify_selector.py：FakeConn 填充进程级 ext_manager，
通过 ext_manager.dispatch() 模拟扩展回包。
"""

import asyncio

import pytest
from fastapi import HTTPException

from src.runtime.routers.extension_router import (
    exec_extension_command,
    list_extension_commands,
)
from src.runtime.websocket_manager import ext_manager


class FakeConn:
    def __init__(self, cid, browser="edge"):
        self.client_id = cid
        self.browser = browser
        self.sent = []

    async def send(self, msg):
        self.sent.append(msg)


def _run(coro):
    try:
        return asyncio.run(coro)
    finally:
        ext_manager._connections.clear()


def test_exec_missing_type():
    with pytest.raises(HTTPException) as exc:
        _run(exec_extension_command({}))
    assert exc.value.status_code == 400


def test_exec_no_connections():
    with pytest.raises(HTTPException) as exc:
        _run(exec_extension_command({"type": "getCurrentUrl"}))
    assert exc.value.status_code == 409


def test_exec_success():
    async def scenario():
        conn = FakeConn("c1")
        ext_manager._connections["c1"] = conn

        async def responder():
            await asyncio.sleep(0.05)
            sent = conn.sent[0]["payload"]
            await ext_manager.dispatch("stepResult", {
                "stepId": sent["stepId"],
                "result": {"url": "https://example.com"},
            }, "c1")

        t = asyncio.ensure_future(responder())
        res = await exec_extension_command({"type": "getCurrentUrl", "timeout": 5})
        await t
        return res, conn

    res, conn = _run(scenario())
    assert res["success"] is True
    assert res["result"] == {"url": "https://example.com"}
    assert res["clientId"] == "c1"
    # 发送给扩展的消息遵循 executeStep 协议
    assert conn.sent[0]["action"] == "executeStep"
    assert conn.sent[0]["payload"]["type"] == "getCurrentUrl"
    assert conn.sent[0]["payload"]["stepId"].startswith("exec_")


def test_exec_step_error_passthrough():
    async def scenario():
        conn = FakeConn("c1")
        ext_manager._connections["c1"] = conn

        async def responder():
            await asyncio.sleep(0.05)
            sent = conn.sent[0]["payload"]
            await ext_manager.dispatch("stepError", {
                "stepId": sent["stepId"],
                "error": "元素未找到",
            }, "c1")

        t = asyncio.ensure_future(responder())
        res = await exec_extension_command(
            {"type": "clickElement", "locator": "#x", "timeout": 5}
        )
        await t
        return res

    res = _run(scenario())
    assert res["success"] is False
    assert res["error"] == "元素未找到"


def test_exec_client_id_not_found():
    async def scenario():
        ext_manager._connections["c1"] = FakeConn("c1")
        await exec_extension_command({"type": "getCurrentUrl", "clientId": "nope"})

    with pytest.raises(HTTPException) as exc:
        _run(scenario())
    assert exc.value.status_code == 409


def test_exec_timeout_returns_504_and_cleans_future():
    async def scenario():
        ext_manager._connections["c1"] = FakeConn("c1")
        with pytest.raises(HTTPException) as exc:
            await exec_extension_command({"type": "getCurrentUrl", "timeout": 0.05})
        assert exc.value.status_code == 504
        # 超时后 future 已从注册表清除，无泄漏
        assert ext_manager._step_futures == {}

    _run(scenario())


def test_exec_timeout_clamped(monkeypatch):
    monkeypatch.setattr(
        "src.runtime.routers.extension_router.MAX_EXEC_TIMEOUT", 5.0
    )

    async def scenario():
        ext_manager._connections["c1"] = FakeConn("c1")
        with pytest.raises(HTTPException) as exc:
            await exec_extension_command({"type": "getCurrentUrl", "timeout": 99999})
        # 超时被钳制到 MAX_EXEC_TIMEOUT（此处 mock 为 5s），而非请求的 99999
        assert exc.value.status_code == 504
        assert "5.0" in exc.value.detail

    _run(scenario())


def test_exec_cancelled_cleans_future():
    async def scenario():
        ext_manager._connections["c1"] = FakeConn("c1")
        task = asyncio.ensure_future(
            exec_extension_command({"type": "getCurrentUrl", "timeout": 30})
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # 取消路径同样清理 future，无泄漏
        assert ext_manager._step_futures == {}

    _run(scenario())


def test_commands_catalog_shape():
    res = _run(_commands_coro())
    assert "commands" in res
    assert len(res["commands"]) > 0
    for cmd in res["commands"]:
        assert cmd["type"]
        assert cmd["cmd"]
    types = {c["type"] for c in res["commands"]}
    # 抽查几个确定性存在的扩展指令
    assert "clickElement" in types
    assert "getText" in types


async def _commands_coro():
    return list_extension_commands()
