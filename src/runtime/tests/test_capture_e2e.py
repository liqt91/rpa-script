"""捕获统一入口端到端测试（ADR-0010，feature: capture-unified-entry-storage）。

覆盖「GUI 捕获 → 保存 → 元素库显示/验证」的完整链路（缺的 e2e 一步）：

- 通过 POST /api/projects/elements/save（项目目录元素库唯一落点）保存 GUI 捕获
  payload（web / win32 / uia 三类），走 normalize_element_capture 归一化；
- 用 _load_project_elements 读回 elements.json，验证元素库「显示」所需字段
  （name / element_type / web_selector / css_candidates / attributes / image 落盘）；
- 同名替换、截图 dataURL 落盘 images/<name>.png、桌面祖先链保留。

与现有单测的分工：test_elements_json_split.py 覆盖 store.save_element_to_workspace
直写 + project_router 读写合并；本文件覆盖 HTTP 端点「捕获→保存→读回验证」的
端到端闭环，正是 feature_list 中 capture-unified-entry-storage.test 一步。
"""
import json

import pytest
from fastapi.testclient import TestClient

from src.runtime.routers.project_router import _load_project_elements


@pytest.fixture()
def client(app):
    """host_guard 只放行本机 host；用 localhost 作为 base_url 通过。"""
    return TestClient(app, base_url="http://localhost")


@pytest.fixture()
def proj(tmp_path):
    """一个最小 RPA 流程工作区（含 rpa.json）。"""
    (tmp_path / "rpa.json").write_text(
        json.dumps({"name": "t", "version": 1}), encoding="utf-8"
    )
    return tmp_path


def _save(client, proj, payload):
    return client.post(
        f"/api/projects/elements/save?path={proj}", json=payload
    )


def _entries(proj):
    return _load_project_elements(proj)


def test_web_capture_save_then_readback(client, proj):
    """GUI web 捕获 → save 端点 → 元素库读回验证（显示字段齐全）。"""
    payload = {
        "name": "搜索框",
        "attributes": {
            "element_type": "web",
            "css_selector": "#kw",
            "candidates": [
                {"family": "css", "syntax": "#kw", "score": 10},
                {"family": "xpath", "syntax": "//input[@id='kw']", "score": 5},
            ],
            "dom_path": ["html", "body", "input"],
            "elem_attrs": {"id": "kw", "placeholder": "搜索"},
            "page_url": "https://example.com/",
        },
    }
    r = _save(client, proj, payload)
    assert r.status_code == 200
    assert r.json()["ok"] is True and r.json()["name"] == "搜索框"

    els = _entries(proj)
    assert [e["name"] for e in els] == ["搜索框"]
    e = els[0]
    assert e["element_type"] == "web"
    assert e["web_selector"] == "#kw"
    # 候选分区：css/xpath 各归其位（显示候选列表需要）
    assert e["css_candidates"][0]["syntax"] == "#kw"
    assert e["xpath_candidates"][0]["syntax"] == "//input[@id='kw']"
    assert e["attributes"]["id"] == "kw"
    assert e["attributes"]["element_type"] == "web"


def test_web_capture_selector_falls_back_to_candidate(client, proj):
    """无 css_selector 时从候选推导：显示端仍能拿到选择器。"""
    payload = {
        "name": "按钮",
        "attributes": {
            "element_type": "web",
            "candidates": [{"family": "css", "syntax": ".submit"}],
            "dom_path": [],
            "elem_attrs": {},
        },
    }
    r = _save(client, proj, payload)
    assert r.status_code == 200
    e = _entries(proj)[0]
    assert e["web_selector"] == ".submit"


def test_web_capture_screenshot_lands_on_disk(client, proj):
    """截图 dataURL 落盘 images/<name>.png，元素库 imagePath 指向它（含 image 要求）。"""
    png = (
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    )
    import base64

    dataurl = "data:image/png;base64," + base64.b64encode(png).decode()
    payload = {
        "name": "logo",
        "screenshot": dataurl,
        "attributes": {
            "element_type": "web",
            "css_selector": "#logo",
            "candidates": [{"family": "css", "syntax": "#logo"}],
            "dom_path": [],
            "elem_attrs": {},
        },
    }
    r = _save(client, proj, payload)
    assert r.status_code == 200
    e = _entries(proj)[0]
    assert e["image"] == "images/logo.png"
    assert (proj / "images" / "logo.png").exists()


def test_win32_capture_save_then_readback(client, proj):
    """GUI win32 捕获 → 元素库读回：祖先链进 attributes.path，类型 win32。"""
    payload = {
        "name": "编辑框",
        "attributes": {
            "element_type": "win32",
            "name": "编辑框",
            "class_name": "Edit",
            "title": "",
            "hwnd": 11,
            "rect": {"width": 780, "height": 560},
            "win32_path": [
                {"hwnd": 10, "class_name": "Notepad", "title": "无标题", "rect": {}},
                {"hwnd": 11, "class_name": "Edit", "title": "", "rect": {}},
            ],
        },
    }
    r = _save(client, proj, payload)
    assert r.status_code == 200
    e = _entries(proj)[0]
    assert e["element_type"] == "win32"
    a = e["attributes"]
    assert a["element_type"] == "win32"
    assert len(a["path"]) == 2
    assert a["path"][1]["class_name"] == "Edit"


def test_uia_capture_save_then_readback(client, proj):
    """GUI uia 捕获（win32 壳 + uia_path）→ 归入 uia，target_index 保留。"""
    payload = {
        "name": "确定",
        "attributes": {
            "element_type": "win32",
            "name": "确定",
            "uia_path": [
                {"name": "窗口", "control_type": "WindowControl",
                 "rect": {"width": 1200, "height": 800}},
                {"name": "确定", "control_type": "ButtonControl", "automation_id": "okBtn",
                 "rect": {"width": 80, "height": 30}},
            ],
            "uia_target_index": 1,
            "win32_path": [{"hwnd": 1, "class_name": "W", "title": "窗口", "rect": {}}],
            "rect": {"width": 80, "height": 30},
        },
    }
    r = _save(client, proj, payload)
    assert r.status_code == 200
    e = _entries(proj)[0]
    assert e["element_type"] == "uia"
    a = e["attributes"]
    assert a["control_type"] == "ButtonControl"
    assert a["automation_id"] == "okBtn"
    assert a["uia_target_index"] == 1
    assert len(a["path"]) == 2


def test_same_name_replace(client, proj):
    """同名捕获 → 覆盖而非新增（元素库显示单行）。"""
    base = {
        "attributes": {
            "element_type": "web",
            "candidates": [{"family": "css", "syntax": "#a"}],
            "dom_path": [],
            "elem_attrs": {},
        },
    }
    _save(client, proj, {**base, "name": "元素A"})
    _save(client, proj, {
        "name": "元素A",
        "attributes": {
            "element_type": "web",
            "candidates": [{"family": "css", "syntax": "#b"}],
            "dom_path": [],
            "elem_attrs": {},
        },
    })
    els = _entries(proj)
    assert len(els) == 1
    assert els[0]["web_selector"] == "#b"


def test_save_not_workspace_returns_403(client, tmp_path):
    """非流程目录（缺 rpa.json）→ 403。"""
    r = _save(client, tmp_path, {"name": "x", "attributes": {"element_type": "web"}})
    assert r.status_code == 403


def test_save_missing_name_returns_400(client, proj):
    """缺元素名 → 400。"""
    r = _save(client, proj, {"attributes": {"element_type": "web"}})
    assert r.status_code == 400
