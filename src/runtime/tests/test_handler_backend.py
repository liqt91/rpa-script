"""
测试 backend handler 的正确性。
使用 run_handler / run_sequence 快速构建测试场景。
"""
import pytest
from .handler_test_utils import make_runner, run_handler, run_sequence


class TestSetVar:
    async def test_set_string(self):
        r = await run_handler("setVar", {
            "name": "{{x}}", "value": "hello", "valueType": "str-input",
        })
        assert r.vars["x"] == "hello"

    async def test_set_int(self):
        r = await run_handler("setVar", {
            "name": "{{x}}", "value": "42", "valueType": "int-number",
        })
        assert r.vars["x"] == 42

    async def test_set_list_with_any_input(self):
        r = await run_handler("setVar", {
            "name": "{{x}}", "value": '["a", "b"]', "valueType": "any-input",
        })
        assert r.vars["x"] == ["a", "b"]

    async def test_set_with_reference_to_other_var(self):
        r = make_runner(vars={"source": "hello"})
        r = await run_handler("setVar", {
            "name": "{{x}}", "value": "{{source}}", "valueType": "any-input",
        }, r)
        assert r.vars["x"] == "hello"


class TestWriteTableRow:
    async def test_append_single_row(self):
        r = await run_handler("writeTableRow", {
            "rowData": '["colA", "colB", "colC"]',
            "writeMode": "append",
        })
        assert len(r._table_data["rows"]) == 1
        assert r._table_data["rows"][0] == {"A": "colA", "B": "colB", "C": "colC"}

    async def test_with_variables(self):
        r = make_runner(vars={"a": "hello", "b": "world"})
        r = await run_handler("writeTableRow", {
            "rowData": '[{{a}}, {{b}}]',
            "writeMode": "append",
        }, r)
        assert r._table_data["rows"][0] == {"A": "hello", "B": "world"}

    async def test_comma_in_value_no_split(self):
        r = make_runner(vars={"text": "hello, world"})
        r = await run_handler("writeTableRow", {
            "rowData": '[{{text}}]',
            "writeMode": "append",
        }, r)
        assert r._table_data["rows"][0] == {"A": "hello, world"}


class TestSequence:
    async def test_setvar_then_writetablerow(self):
        """模拟知乎竞品统计的核心流程：设变量 → 写表格"""
        r = await run_sequence([
            ("setVar", {"name": "{{kws}}", "value": '["知乎", "同花顺"]', "valueType": "any-input"}),
            ("setVar", {"name": "{{title}}", "value": "如何学习", "valueType": "any-input"}),
            ("writeTableRow", {"rowData": '[{{kws}}, {{title}}]', "writeMode": "append"}),
        ])
        assert len(r._table_data["rows"]) == 1
        row = r._table_data["rows"][0]
        assert row["A"] == ["知乎", "同花顺"]  # list stored in A
        assert row["B"] == "如何学习"          # string stored in B

    async def test_multiple_rows(self):
        """连续写入多行"""
        r = await run_sequence([
            ("writeTableRow", {"rowData": '["A1", "B1"]', "writeMode": "append"}),
            ("writeTableRow", {"rowData": '["A2", "B2"]', "writeMode": "append"}),
            ("writeTableRow", {"rowData": '["A3", "B3"]', "writeMode": "append"}),
        ])
        assert len(r._table_data["rows"]) == 3
        assert r._table_data["rows"][1]["A"] == "A2"


class TestLog:
    async def test_log_with_vars(self):
        r = make_runner(vars={"name": "test"})
        await run_handler("log", {"message": "processing {{name}}"}, r)
        # log 不修改状态，只验证不报错
        assert r.completed == 1

    async def test_log_any_input(self):
        r = make_runner(vars={"count": 5})
        await run_handler("log", {"message": "count={{count}}"}, r)
        assert r.completed == 1


class TestIncrement:
    async def test_increment_existing(self):
        r = make_runner(vars={"i": 0})
        r = await run_handler("increment", {"varName": "{{i}}", "step": 1}, r)
        assert r.vars["i"] == 1

    async def test_increment_negative(self):
        r = make_runner(vars={"i": 10})
        r = await run_handler("increment", {"varName": "{{i}}", "step": -3}, r)
        assert r.vars["i"] == 7
