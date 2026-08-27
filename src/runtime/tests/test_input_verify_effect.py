"""verifyEffect 声明式效果验证 — runner 侧单元测试。

场景：inputElement 模拟键盘输入（OS SendInput）后，handler 在结果里声明
verifyEffect={kind: readbackValue, expect}，runner 必须在回车前回读目标元素
value 并比对；不一致则步骤失败（抓「焦点被抢导致按键没落到输入框」）。
"""
import pytest

from src.runtime.workflow import extension_runner as er
from src.runtime.workflow.extension_runner import ExtensionRunner


def _make_runner() -> ExtensionRunner:
    r = ExtensionRunner(client_id="ext_test")
    r._current_step = {"nodeId": "n1", "cmdType": "inputElement", "cmdLabel": "输入文本"}
    return r


def _instr() -> dict:
    return {
        "stepId": "step_1",
        "nodeId": "n1",
        "cmdType": "inputElement",
        "locator": "#search-input-in-feeds",
        "selectorFamily": "css",
        "extra": {"text": "摄影", "simulateKeyboard": True, "onError": "stop"},
    }


def _os_result(with_verify: bool = True) -> dict:
    r = {"input": "摄影", "length": 2, "osType": "摄影", "osClear": True}
    if with_verify:
        r["verifyEffect"] = {"kind": "readbackValue", "expect": "摄影"}
    return r


@pytest.mark.asyncio
async def test_os_input_readback_match_succeeds(monkeypatch):
    """OS 键入后回读值与期望一致 → 步骤成功且带 inputVerified 标记。"""
    r = _make_runner()

    async def fake_send_wait(self, step_id, instr, timeout):
        return _os_result(with_verify=True)

    async def fake_call(self, handler, payload, timeout=10):
        assert handler == "getText"
        assert payload["locator"] == "#search-input-in-feeds"
        return {"value": "摄影"}

    monkeypatch.setattr(ExtensionRunner, "_send_and_wait", fake_send_wait)
    monkeypatch.setattr(ExtensionRunner, "_call_extension_handler", fake_call)
    monkeypatch.setattr(er, "_os_type_text", lambda text, clear_first=False: True)

    ok = await r._execute_instruction(_instr())
    assert ok is True
    assert r.failed_steps == []
    assert r.results[0]["result"].get("inputVerified") is True


@pytest.mark.asyncio
async def test_os_input_readback_mismatch_fails(monkeypatch):
    """回读值与期望不一致（焦点被抢，按键没落到输入框）→ 步骤失败。"""
    r = _make_runner()

    async def fake_send_wait(self, step_id, instr, timeout):
        return _os_result(with_verify=True)

    async def fake_call(self, handler, payload, timeout=10):
        return {"value": ""}  # 焦点跑偏：目标元素没收到任何字符

    monkeypatch.setattr(ExtensionRunner, "_send_and_wait", fake_send_wait)
    monkeypatch.setattr(ExtensionRunner, "_call_extension_handler", fake_call)
    monkeypatch.setattr(er, "_os_type_text", lambda text, clear_first=False: True)

    ok = await r._execute_instruction(_instr())
    assert ok is False
    assert len(r.failed_steps) == 1
    assert "回读校验失败" in r.failed_steps[0]["error"]


@pytest.mark.asyncio
async def test_os_input_without_verify_declaration_skips_readback(monkeypatch):
    """handler 未声明 verifyEffect → 不做回读（兼容旧 handler/无验证需求的指令）。"""
    r = _make_runner()
    calls = []

    async def fake_send_wait(self, step_id, instr, timeout):
        return _os_result(with_verify=False)

    async def fake_call(self, handler, payload, timeout=10):
        calls.append(handler)
        return {"value": "摄影"}

    monkeypatch.setattr(ExtensionRunner, "_send_and_wait", fake_send_wait)
    monkeypatch.setattr(ExtensionRunner, "_call_extension_handler", fake_call)
    monkeypatch.setattr(er, "_os_type_text", lambda text, clear_first=False: True)

    ok = await r._execute_instruction(_instr())
    assert ok is True
    assert calls == []  # 未声明验证 → 不触发任何回读调用
    assert "inputVerified" not in r.results[0]["result"]
