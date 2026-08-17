"""
T1 纯后端控制流测试：条件判断 / try/catch / 循环边界。

全部为本地指令（setVar/log/if*/for*/while/try），不依赖浏览器扩展连接，
走真实 emitter→instructions→runner 管线（与 command-test E2E 同构，只是无浏览器）。
见 docs/指令全量测试方案-20260814.md §4。
"""
import json

import pytest

from src.repo import models
from src.runtime.workflow.extension_runner import run_workflow_extension

_CTR = [0]


def _build_workflow(spec):
    """nodes_spec: [{"cmd", "extra", "elementName"?, "parentOrder"?}]，直接写 DB（仿 build_workflow.py）。"""
    _CTR[0] += 1
    db = models.SessionLocal()
    try:
        wf = models.Workflow(name=f"T1控制流-{_CTR[0]}")
        db.add(wf)
        db.flush()
        id_by_order = {}
        node_ids = {}
        for i, n in enumerate(spec, 1):
            order = n.get("order", i)
            node = models.WorkflowNode(
                workflow_id=wf.id, order=order, cmd=n["cmd"],
                element_name=n.get("elementName"),
                extra=json.dumps(n.get("extra", {}), ensure_ascii=False),
            )
            db.add(node)
            db.flush()
            id_by_order[order] = node.id
            node_ids[id(node)] = node
        for n in spec:
            po = n.get("parentOrder")
            if po is not None:
                parent_id = id_by_order.get(po)
                if parent_id is None:
                    raise ValueError(f"parentOrder {po} not found")
                db.query(models.WorkflowNode).filter_by(id=id_by_order[n.get("order", spec.index(n) + 1)]) \
                    .update({"parent_id": parent_id})
        db.commit()
        nodes = (
            db.query(models.WorkflowNode)
            .filter_by(workflow_id=wf.id)
            .order_by(models.WorkflowNode.order)
            .all()
        )
        return wf, nodes
    finally:
        db.close()


async def _run(spec):
    wf, nodes = _build_workflow(spec)
    return await run_workflow_extension(wf, nodes)


def _logs(results):
    """收集 log 结果。P2 已知行为：log 条目是裸 {"log","level"}（无 result 包装）。"""
    out = []
    for r in results:
        if not isinstance(r, dict):
            continue
        if "log" in r:
            out.append(r["log"])
        elif isinstance(r.get("result"), dict) and "log" in r["result"]:
            out.append(r["result"]["log"])
    return out


def _result_of(results, key):
    """收集指令结果字段（裸条目或 result 包装均可）。"""
    out = []
    for r in results:
        if not isinstance(r, dict):
            continue
        if key in r:
            out.append(r[key])
        elif isinstance(r.get("result"), dict) and key in r["result"]:
            out.append(r["result"][key])
    return out


# ── 条件判断：ifVarEquals ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_if_var_equals_true_branch():
    res = await _run([
        {"cmd": "setVar", "extra": {"name": "{{a}}", "value": "5", "valueType": "number"}},
        {"cmd": "ifVarEquals", "extra": {"varName": "a", "compareTo": "5"}},
        {"cmd": "log", "parentOrder": 2, "extra": {"message": "eq-ok", "level": "info"}},
        {"cmd": "endIf", "extra": {}},
    ])
    assert res["success"], res
    assert "eq-ok" in _logs(res["results"])


@pytest.mark.asyncio
async def test_if_var_equals_false_branch_skipped():
    res = await _run([
        {"cmd": "setVar", "extra": {"name": "{{a}}", "value": "5", "valueType": "number"}},
        {"cmd": "ifVarEquals", "extra": {"varName": "a", "compareTo": "9"}},
        {"cmd": "log", "parentOrder": 2, "extra": {"message": "eq-ok", "level": "info"}},
        {"cmd": "endIf", "extra": {}},
    ])
    assert res["success"], res
    assert "eq-ok" not in _logs(res["results"])


@pytest.mark.asyncio
async def test_if_var_equals_greater_than():
    res = await _run([
        {"cmd": "setVar", "extra": {"name": "{{a}}", "value": "7", "valueType": "number"}},
        {"cmd": "ifVarEquals", "extra": {"varName": "a", "compareTo": "5",
                                         "valueType": "number", "operator": "greaterThan"}},
        {"cmd": "log", "parentOrder": 2, "extra": {"message": "gt-ok", "level": "info"}},
        {"cmd": "endIf", "extra": {}},
    ])
    assert res["success"], res
    assert "gt-ok" in _logs(res["results"])


# ── 条件判断：ifListContains / ifDictContains / ifVarContains ─────

@pytest.mark.asyncio
async def test_if_list_contains_true_and_false():
    res = await _run([
        {"cmd": "setVar", "extra": {"name": "{{lst}}", "value": '["a","b","c"]', "valueType": "any-input"}},
        {"cmd": "ifListContains", "extra": {"listVar": "lst", "value": "b"}},
        {"cmd": "log", "parentOrder": 2, "extra": {"message": "in-ok", "level": "info"}},
        {"cmd": "endIf", "extra": {}},
        {"cmd": "ifListContains", "extra": {"listVar": "lst", "value": "z"}},
        {"cmd": "log", "parentOrder": 5, "extra": {"message": "not-in", "level": "info"}},
        {"cmd": "endIf", "extra": {}},
    ])
    assert res["success"], res
    logs = _logs(res["results"])
    assert "in-ok" in logs
    assert "not-in" not in logs


@pytest.mark.asyncio
async def test_if_dict_contains_key():
    res = await _run([
        {"cmd": "setVar", "extra": {"name": "{{d}}", "value": '{"k": "v"}', "valueType": "any-input"}},
        {"cmd": "ifDictContains", "extra": {"dictVar": "d", "key": "k"}},
        {"cmd": "log", "parentOrder": 2, "extra": {"message": "key-ok", "level": "info"}},
        {"cmd": "endIf", "extra": {}},
        {"cmd": "ifDictContains", "extra": {"dictVar": "d", "key": "missing"}},
        {"cmd": "log", "parentOrder": 5, "extra": {"message": "key-miss", "level": "info"}},
        {"cmd": "endIf", "extra": {}},
    ])
    assert res["success"], res
    logs = _logs(res["results"])
    assert "key-ok" in logs
    assert "key-miss" not in logs


@pytest.mark.asyncio
async def test_if_var_contains_string():
    res = await _run([
        {"cmd": "setVar", "extra": {"name": "{{s}}", "value": "hello world", "valueType": "string"}},
        {"cmd": "ifVarContains", "extra": {"varName": "s", "substring": "lo wo"}},
        {"cmd": "log", "parentOrder": 2, "extra": {"message": "sub-ok", "level": "info"}},
        {"cmd": "endIf", "extra": {}},
        {"cmd": "ifVarContains", "extra": {"varName": "s", "substring": "zzz"}},
        {"cmd": "log", "parentOrder": 5, "extra": {"message": "sub-miss", "level": "info"}},
        {"cmd": "endIf", "extra": {}},
    ])
    assert res["success"], res
    logs = _logs(res["results"])
    assert "sub-ok" in logs
    assert "sub-miss" not in logs


# ── try/catch ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_try_success_no_catch():
    res = await _run([
        {"cmd": "try", "extra": {}},
        {"cmd": "log", "parentOrder": 1, "extra": {"message": "try-ok", "level": "info"}},
        {"cmd": "endTry", "extra": {}},
    ])
    assert res["success"], res
    assert "try-ok" in _logs(res["results"])


@pytest.mark.asyncio
async def test_try_catch_caught_on_failed_step():
    res = await _run([
        {"cmd": "try", "extra": {}},
        {"cmd": "noSuchCommand", "parentOrder": 1, "extra": {"onError": "stop"}},
        {"cmd": "catch", "extra": {}},
        {"cmd": "log", "parentOrder": 3, "extra": {"message": "caught", "level": "info"}},
        {"cmd": "endTry", "extra": {}},
    ])
    assert res["success"], res
    assert "caught" in _logs(res["results"])


@pytest.mark.asyncio
async def test_try_catch_error_var_injected():
    res = await _run([
        {"cmd": "try", "extra": {"errorVar": "err"}},
        {"cmd": "noSuchCommand", "parentOrder": 1, "extra": {"onError": "stop"}},
        {"cmd": "catch", "extra": {}},
        {"cmd": "log", "parentOrder": 3, "extra": {"message": "err={{err}}", "level": "info"}},
        {"cmd": "endTry", "extra": {}},
    ])
    assert res["success"], res
    logs = _logs(res["results"])
    assert any("err=" in x and "noSuchCommand" in x for x in logs), logs


# ── 循环边界 ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_for_range_negative_step():
    res = await _run([
        {"cmd": "forRange", "extra": {"start": 10, "end": 2, "step": -2, "itemVar": "j"}},
        {"cmd": "log", "parentOrder": 1, "extra": {"message": "j={{j}}", "level": "info"}},
        {"cmd": "endLoop", "extra": {}},
    ])
    assert res["success"], res
    logs = _logs(res["results"])
    assert logs == ["j=10", "j=8", "j=6", "j=4", "j=2"], logs


@pytest.mark.asyncio
async def test_for_range_zero_step_coerced_to_one():
    res = await _run([
        {"cmd": "forRange", "extra": {"start": 0, "end": 2, "step": 0, "itemVar": "i"}},
        {"cmd": "log", "parentOrder": 1, "extra": {"message": "i={{i}}", "level": "info"}},
        {"cmd": "endLoop", "extra": {}},
    ])
    assert res["success"], res
    assert _logs(res["results"]) == ["i=0", "i=1", "i=2"]


@pytest.mark.asyncio
async def test_for_list_empty_runs_zero_times():
    res = await _run([
        {"cmd": "setVar", "extra": {"name": "{{lst}}", "value": "[]", "valueType": "any-input"}},
        {"cmd": "forList", "extra": {"listVar": "lst", "itemVar": "i"}},
        {"cmd": "log", "parentOrder": 2, "extra": {"message": "iter", "level": "info"}},
        {"cmd": "endLoop", "extra": {}},
    ])
    assert res["success"], res
    assert "iter" not in _logs(res["results"])


@pytest.mark.asyncio
async def test_while_max_iterations_fuse():
    res = await _run([
        {"cmd": "whileCondition", "extra": {"conditionType": "expression", "condition": "True", "maxIterations": 3}},
        {"cmd": "log", "parentOrder": 1, "extra": {"message": "tick", "level": "info"}},
        {"cmd": "endLoop", "extra": {}},
    ])
    assert res["success"], res
    assert _logs(res["results"]) == ["tick", "tick", "tick"]


@pytest.mark.asyncio
async def test_break_exits_loop_immediately():
    """break 首次迭代即退出 → 循环体 log 只执行 1 次。"""
    res = await _run([
        {"cmd": "forRange", "extra": {"start": 0, "end": 9, "step": 1, "itemVar": "i"}},
        {"cmd": "log", "parentOrder": 1, "extra": {"message": "iter", "level": "info"}},
        {"cmd": "break", "parentOrder": 1, "extra": {}},
        {"cmd": "endLoop", "extra": {}},
    ])
    assert res["success"], res
    assert _logs(res["results"]) == ["iter"]


@pytest.mark.asyncio
async def test_continue_runs_all_iterations():
    """continue 跳过本次剩余体 → 循环体 log 执行全部 10 次。"""
    res = await _run([
        {"cmd": "forRange", "extra": {"start": 0, "end": 9, "step": 1, "itemVar": "i"}},
        {"cmd": "log", "parentOrder": 1, "extra": {"message": "iter", "level": "info"}},
        {"cmd": "continue", "parentOrder": 1, "extra": {}},
        {"cmd": "endLoop", "extra": {}},
    ])
    assert res["success"], res
    assert _logs(res["results"]) == ["iter"] * 10


@pytest.mark.asyncio
async def test_navigate_without_locator_bypasses_p4_check(monkeypatch):
    """navigate 等无定位器指令应跳过 P4 locator 校验，直接下发扩展（此前必失败）。

    回归：P4 校验曾对所有带 locator 键的指令生效，navigate/newTab/launchBrowser
    因 locator 为空被误判失败 —— DSH 文件式构建的导航工作流会踩到。
    """
    from src.runtime.workflow.extension_runner import ExtensionRunner

    runner = ExtensionRunner("")
    sent = {}

    async def fake_send_and_wait(step_id, instr, timeout):
        sent["instr"] = instr
        return {"success": True, "navigatedTo": instr.get("extra", {}).get("url")}

    monkeypatch.setattr(runner, "_send_and_wait", fake_send_and_wait)

    instr = {
        "stepId": "step_1", "nodeId": 1, "order": 1, "cmdType": "navigate",
        "cmdLabel": "页面跳转", "type": "navigate",
        "locator": "", "selectorFamily": "css", "action": "",
        "extra": {"url": "https://www.baidu.com"},
    }
    runner._current_step = instr  # 真实流程由 _run_body 设置，直接调用需镜像
    ok = await runner._execute_instruction(instr)
    assert ok is True, "navigate 不应因空 locator 失败"
    assert sent["instr"]["extra"]["url"] == "https://www.baidu.com", "extra.url 应原样下发"
    assert runner.completed == 1
