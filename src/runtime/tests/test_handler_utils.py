"""
测试 convert_value / resolve_vars / resolve_vars_json / clean_var_ref
"""
import pytest
from src.runtime.workflow.handlers.utils import (
    resolve_vars,
    resolve_vars_json,
    convert_value,
    clean_var_ref,
)


class TestResolveVars:
    def test_basic_replacement(self):
        assert resolve_vars("hello {{name}}", {"name": "world"}) == "hello world"

    def test_missing_var_keeps_placeholder(self):
        assert resolve_vars("hello {{missing}}", {}) == "hello {{missing}}"

    def test_multiple_vars(self):
        result = resolve_vars("{{a}} and {{b}}", {"a": "1", "b": "2"})
        assert result == "1 and 2"

    def test_chinese_var_names(self):
        assert resolve_vars("${当前关键词}", {"当前关键词": "知乎"}) == "知乎"

    def test_list_var_to_string(self):
        # resolve_vars 用 str()，列表变成 Python repr
        result = resolve_vars("{{items}}", {"items": ["a", "b"]})
        assert result == "['a', 'b']"


class TestResolveVarsJson:
    def test_string_gets_quoted(self):
        result = resolve_vars_json("{{name}}", {"name": "hello"})
        assert result == '"hello"'

    def test_number_stays_number(self):
        result = resolve_vars_json("{{n}}", {"n": 42})
        assert result == "42"

    def test_list_gets_json(self):
        result = resolve_vars_json("{{items}}", {"items": ["a", "b"]})
        assert result == '["a", "b"]'

    def test_dict_gets_json(self):
        result = resolve_vars_json("{{d}}", {"d": {"k": "v"}})
        assert result == '{"k": "v"}'

    def test_in_array_template(self):
        result = resolve_vars_json("[{{a}}, {{b}}]", {"a": "hello, world", "b": "foo"})
        assert result == '["hello, world", "foo"]'

    def test_missing_var_keeps_placeholder(self):
        result = resolve_vars_json("[{{a}}, {{missing}}]", {"a": "x"})
        assert result == '["x", {{missing}}]'


class TestConvertValue:
    def test_str_input(self):
        assert convert_value("hello {{n}}", "str-input", {"n": "x"}) == "hello x"

    def test_int_number(self):
        assert convert_value("42", "int-number") == 42
        assert convert_value("3.14", "int-number") == 3
        assert convert_value("abc", "int-number") == 0

    def test_bool_check(self):
        assert convert_value("true", "bool-check") is True
        assert convert_value("1", "bool-check") is True
        assert convert_value("yes", "bool-check") is True
        assert convert_value("false", "bool-check") is False

    def test_list_input_json(self):
        result = convert_value('["a", "b"]', "list-input")
        assert result == ["a", "b"]

    def test_list_input_with_vars(self):
        result = convert_value("[{{a}}, {{b}}]", "list-input", {"a": "hello", "b": "world"})
        assert result == ["hello", "world"]

    def test_list_input_comma_in_value(self):
        result = convert_value('[{{a}}, {{b}}]', "list-input", {"a": "hello, world", "b": "foo"})
        assert result == ["hello, world", "foo"]

    def test_list_input_invalid_json_fallback(self):
        result = convert_value("not json", "list-input")
        assert result == ["not json"]

    def test_any_input(self):
        assert convert_value("123", "any-input") == 123
        assert convert_value("true", "any-input") is True
        assert convert_value("hello", "any-input") == "hello"

    def test_any_expr(self):
        assert convert_value("len(x)", "any-expr", {"x": [1, 2, 3]}) == 3

    def test_legacy_type_names(self):
        assert convert_value("42", "number") == 42  # old → int-number
        assert convert_value('["a"]', "list") == ["a"]  # old → list-input

    def test_dropdown_no_transform(self):
        assert convert_value("chrome", "str-dropdown") == "chrome"


class TestCleanVarRef:
    def test_strips_dollar_brace(self):
        assert clean_var_ref("{{statistic}}") == "statistic"

    def test_strips_double_brace(self):
        assert clean_var_ref("{{statistic}}") == "statistic"

    def test_plain_name_passthrough(self):
        assert clean_var_ref("statistic") == "statistic"

    def test_chinese_name(self):
        assert clean_var_ref("${当前关键词}") == "当前关键词"
