"""project_router RPA_HOME 集中流程根 —— /home /list /create 测试。"""
from pathlib import Path

from src.runtime.routers import project_router as pr


def test_project_home_create_list(tmp_path, monkeypatch):
    monkeypatch.setattr(pr.config, "RPA_HOME", str(tmp_path / "RPA主页"))

    # /home 返回根
    home = pr.project_home()
    assert home["ok"]
    assert Path(home["rpaHome"]) == (tmp_path / "RPA主页").resolve()

    # /create 在根下建流程目录（rpa.json + 空 workflow.json，幂等）
    r = pr.project_create({"name": "知乎热搜", "description": "测试流程"})
    assert r["ok"]
    root = Path(r["path"])
    assert root.is_dir()
    assert (root / "rpa.json").is_file()
    assert (root / "workflow.json").is_file()
    assert (root / "elements.json").is_file()
    assert (root / "images").is_dir()
    assert (root / "run_logs").is_dir()
    assert root.parent == (tmp_path / "RPA主页").resolve()

    # /list 枚举根下所有流程
    flows = pr.project_list()
    assert flows["ok"]
    assert flows["count"] == 1
    assert flows["flows"][0]["name"] == "知乎热搜"
    assert flows["flows"][0]["slug"] == "知乎热搜"

    # 再创建同名 → 幂等，不重复
    pr.project_create({"name": "知乎热搜", "description": "重复"})
    assert pr.project_list()["count"] == 1

    # 空白 name → 400
    import pytest
    with pytest.raises(Exception):
        pr.project_create({"name": "   "})


def test_project_list_empty_when_unset(tmp_path, monkeypatch):
    monkeypatch.setattr(pr.config, "RPA_HOME", str(tmp_path / "不存在的RPA主页"))
    assert pr.project_list()["count"] == 0
