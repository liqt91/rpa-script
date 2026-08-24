"""elements.json 拆分：捕获/保存写 elements.json，不碰 workflow.json；读取合并遗留。

覆盖：
- store.save_element_to_workspace → elements.json（同名替换、原子写、截图落 images/）
- project_router._load_project_elements / _save_project_elements（遗留合并）
- extension_runner.load_project_workflow（elements.json 优先 + workflow.json 遗留兜底）
"""
import json

import pytest

from scripts.capture_gui.store import save_element_to_workspace
from src.runtime.routers.project_router import (
    _load_project_elements,
    _save_project_elements,
)
from src.runtime.workflow.extension_runner import load_project_workflow


@pytest.fixture()
def workspace(tmp_path):
    (tmp_path / "rpa.json").write_text(
        json.dumps({"name": "t", "version": 1}), encoding="utf-8"
    )
    return tmp_path


def _web_info(name="搜索框", selector="#search-input"):
    return {
        "name": name,
        "element_type": "web",
        "css_selector": selector,
        "candidates": [{"family": "css", "syntax": selector}],
        "elem_attrs": {"id": "search-input"},
        "dom_path": [],
        "page_url": "http://x",
        "screenshot": None,
    }


class TestSaveElementToWorkspace:
    def test_writes_elements_json_not_workflow(self, workspace):
        r = save_element_to_workspace(str(workspace), _web_info())
        assert r["ok"] and r["count"] == 1
        el = json.loads((workspace / "elements.json").read_text(encoding="utf-8"))
        assert el["elements"][0]["web_selector"] == "#search-input"
        assert not (workspace / "workflow.json").exists()  # 不创建/不碰 workflow.json

    def test_same_name_replace(self, workspace):
        save_element_to_workspace(str(workspace), _web_info(selector="#a"))
        r = save_element_to_workspace(str(workspace), _web_info(selector="#b"))
        assert r["count"] == 1
        el = json.loads((workspace / "elements.json").read_text(encoding="utf-8"))
        assert el["elements"][0]["web_selector"] == "#b"

    def test_not_workspace_raises(self, tmp_path):
        with pytest.raises(ValueError):
            save_element_to_workspace(str(tmp_path), _web_info())


class TestProjectElementsMerge:
    def test_elements_json_priority_over_legacy(self, workspace):
        _save_project_elements(workspace, [{"name": "a", "web_selector": "#new"}])
        (workspace / "workflow.json").write_text(json.dumps({
            "name": "t", "nodes": [],
            "elements": [{"name": "a", "web_selector": "#old"},
                         {"name": "b", "web_selector": "#legacy"}],
        }), encoding="utf-8")
        els = _load_project_elements(workspace)
        by_name = {e["name"]: e for e in els}
        assert by_name["a"]["web_selector"] == "#new"      # elements.json 赢
        assert by_name["b"]["web_selector"] == "#legacy"   # 遗留补齐
        assert len(els) == 2

    def test_missing_elements_json_falls_back_to_legacy(self, workspace):
        (workspace / "workflow.json").write_text(json.dumps({
            "name": "t", "nodes": [],
            "elements": [{"name": "x", "web_selector": "#x"}],
        }), encoding="utf-8")
        els = _load_project_elements(workspace)
        assert [e["name"] for e in els] == ["x"]


class TestLoadProjectWorkflowMerge:
    def test_runner_merges_elements_json(self, workspace):
        (workspace / "workflow.json").write_text(json.dumps({
            "name": "t", "nodes": [{"cmd": "clickElement", "element_name": "a"}],
            "elements": [{"name": "a", "web_selector": "#old"},
                         {"name": "b", "web_selector": "#legacy"}],
        }), encoding="utf-8")
        (workspace / "elements.json").write_text(json.dumps({
            "version": 1,
            "elements": [{"name": "a", "web_selector": "#new", "element_kind": "plain"}],
        }), encoding="utf-8")
        wf, nodes, element_map = load_project_workflow(str(workspace))
        assert wf.name == "t"
        assert len(nodes) == 1
        assert element_map["a"].web_selector == "#new"
        assert element_map["b"].web_selector == "#legacy"

    def test_runner_without_elements_json(self, workspace):
        (workspace / "workflow.json").write_text(json.dumps({
            "name": "t", "nodes": [],
            "elements": [{"name": "x", "web_selector": "#x"}],
        }), encoding="utf-8")
        _, _, element_map = load_project_workflow(str(workspace))
        assert element_map["x"].web_selector == "#x"
