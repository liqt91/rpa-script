"""桌面元素捕获归一化测试 — element_type 选择 + target_index 保留 + 层级字段。"""

from src.service.elements_service import normalize_element_capture


def _uia_chain(with_index=True):
    """root → leaf 的完整 UIA 链（目标在中段 idx=2）。"""
    def _rect(w, h, left, top, right, bottom):
        return {"width": w, "height": h, "left": left, "top": top, "right": right, "bottom": bottom}

    nodes = [
        {"name": "窗口", "class_name": "Chrome_WidgetWin_1", "control_type": "WindowControl",
         "automation_id": "", "rect": _rect(1200, 800, 0, 0, 1200, 800)},
        {"name": "", "class_name": "", "control_type": "PaneControl",
         "automation_id": "", "rect": _rect(1200, 700, 0, 50, 1200, 750)},
        {"name": "确定", "class_name": "", "control_type": "ButtonControl",
         "automation_id": "okBtn", "rect": _rect(80, 30, 100, 200, 180, 230)},
        {"name": "", "class_name": "", "control_type": "TextControl",
         "automation_id": "", "rect": _rect(40, 20, 110, 205, 150, 225)},
    ]
    if with_index:
        for i, n in enumerate(nodes):
            if i > 0:
                n["index"] = 0
            n["enabled"] = True
            n["is_off_screen"] = False
    return nodes


def test_normalize_uia_keeps_full_chain_and_target_index():
    attrs = {
        "element_type": "win32",
        "name": "确定",
        "uia_path": _uia_chain(),
        "uia_target_index": 2,
        "win32_path": [{"hwnd": 1, "class_name": "Chrome_WidgetWin_1", "title": "窗口", "rect": {}}],
        "rect": {"width": 80, "height": 30},
        "screenshot": "data:image/png;base64,xxx",
    }
    out = normalize_element_capture(attrs)
    assert out["element_type"] == "uia"
    a = out["attributes"]
    # 完整链保留（4 层），身份字段取自 target 层（idx=2 的 Button）
    assert len(a["path"]) == 4
    assert a["uia_target_index"] == 2
    assert a["control_type"] == "ButtonControl"
    assert a["automation_id"] == "okBtn"
    assert a["name"] == "确定"
    # 每层的 index/enabled 字段保留
    assert a["path"][3]["control_type"] == "TextControl"
    assert a["path"][2]["index"] == 0
    assert a["path"][2]["enabled"] is True


def test_normalize_uia_target_index_out_of_range_falls_back_to_leaf():
    attrs = {
        "element_type": "win32",
        "name": "x",
        "uia_path": _uia_chain(),
        "uia_target_index": 99,
        "win32_path": [{"hwnd": 1, "class_name": "C", "title": "t", "rect": {}}],
        "rect": {},
    }
    out = normalize_element_capture(attrs)
    a = out["attributes"]
    assert a["uia_target_index"] == 3  # 回落到最后一层
    assert a["control_type"] == "TextControl"


def test_normalize_uia_without_target_index_defaults_to_leaf():
    attrs = {
        "element_type": "win32",
        "name": "x",
        "uia_path": _uia_chain(),
        "win32_path": [{"hwnd": 1, "class_name": "C", "title": "t", "rect": {}}],
        "rect": {},
    }
    out = normalize_element_capture(attrs)
    a = out["attributes"]
    assert a["uia_target_index"] == 3


def test_normalize_win32_path_keeps_sibling_index():
    win32_path = [
        {"hwnd": 10, "class_name": "Notepad", "title": "无标题", "rect": {"width": 800, "height": 600},
         "index": 0, "enabled": True, "visible": True},
        {"hwnd": 11, "class_name": "Edit", "title": "", "rect": {"width": 780, "height": 560},
         "index": 1, "enabled": True, "visible": True},
    ]
    attrs = {
        "element_type": "win32",
        "name": "Edit",
        "win32_path": win32_path,
        "rect": {"width": 780, "height": 560},
    }
    out = normalize_element_capture(attrs)
    assert out["element_type"] == "win32"
    a = out["attributes"]
    assert a["path"][1]["index"] == 1
    assert a["path"][1]["enabled"] is True
