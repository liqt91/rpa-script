"""
测试 backend handler 的正确性。
使用 run_handler / run_sequence 快速构建测试场景。
"""
import pytest
from .handler_test_utils import make_runner, run_handler


class TestSetVar:
    @pytest.mark.asyncio
    async def test_set_string(self):
        r = await run_handler("setVar", {
            "name": "{{x}}", "value": "hello", "valueType": "str-input",
        })
        assert r.vars["x"] == "hello"

    @pytest.mark.asyncio
    async def test_set_int(self):
        r = await run_handler("setVar", {
            "name": "{{x}}", "value": "42", "valueType": "int-number",
        })
        assert r.vars["x"] == 42

    @pytest.mark.asyncio
    async def test_set_list_with_any_input(self):
        r = await run_handler("setVar", {
            "name": "{{x}}", "value": '["a", "b"]', "valueType": "any-input",
        })
        assert r.vars["x"] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_set_with_reference_to_other_var(self):
        r = make_runner(vars={"source": "hello"})
        r = await run_handler("setVar", {
            "name": "{{x}}", "value": "{{source}}", "valueType": "any-input",
        }, r)
        assert r.vars["x"] == "hello"


class TestLog:
    @pytest.mark.asyncio
    async def test_log_with_vars(self):
        r = make_runner(vars={"name": "test"})
        await run_handler("log", {"message": "processing {{name}}"}, r)
        # log 不修改状态，只验证不报错
        assert r.completed == 1

    @pytest.mark.asyncio
    async def test_log_any_input(self):
        r = make_runner(vars={"count": 5})
        await run_handler("log", {"message": "count={{count}}"}, r)
        assert r.completed == 1

