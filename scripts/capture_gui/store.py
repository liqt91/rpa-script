"""元素库 JSON 持久化。

文件格式:
{
    "version": 1,
    "elements": [
        {
            "name": "...",
            "element_type": "win32|uia|web",
            "class_name": "...",
            "title": "...",
            "rect": {...},
            "win32_path": [...],
            "uia_path": [...],
            "control_type": "...",
            "automation_id": "...",
            "css_selector": "...",
            "xpath": "...",
            "tag_name": "...",
            "hwnd": 0
        }
    ]
}
"""

import json
import os
from dataclasses import asdict
from scripts.capture_gui.overlay import ElementInfo


def _info_to_dict(info: ElementInfo) -> dict:
    d = asdict(info)
    d.pop("hwnd", None)
    d.pop("screenshot", None)  # 不存到文件，太大
    return d


def _dict_to_info(d: dict) -> ElementInfo:
    return ElementInfo(
        name=d.get("name", ""),
        element_type=d.get("element_type", "win32"),
        class_name=d.get("class_name", ""),
        title=d.get("title", ""),
        rect=d.get("rect", {}),
        hwnd=0,
        control_type=d.get("control_type", ""),
        automation_id=d.get("automation_id", ""),
        uia_path=d.get("uia_path", []),
        css_selector=d.get("css_selector", ""),
        xpath=d.get("xpath", ""),
        tag_name=d.get("tag_name", ""),
        win32_path=d.get("win32_path", []),
        candidates=d.get("candidates", []),
        screenshot=d.get("screenshot", ""),
        dom_path=d.get("dom_path", []),
        elem_attrs=d.get("elem_attrs", {}),
        list_info=d.get("list_info", {}),
        tab_id=d.get("tab_id", 0) or 0,
    )


class ElementStore:
    """元素库管理。"""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.elements: list[ElementInfo] = []
        self._load()

    def _load(self):
        if not os.path.exists(self.filepath):
            self.elements = []
            return
        with open(self.filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.elements = [_dict_to_info(e) for e in data.get("elements", [])]

    def save(self):
        data = {
            "version": 1,
            "elements": [_info_to_dict(e) for e in self.elements],
        }
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add(self, info: ElementInfo):
        # 自动生成名称
        if not info.name:
            info.name = f"{info.element_type}_{info.class_name}"
        self.elements.append(info)
        self.save()

    def remove(self, index: int):
        if 0 <= index < len(self.elements):
            self.elements.pop(index)
            self.save()

    def update(self, index: int, info: ElementInfo):
        if 0 <= index < len(self.elements):
            self.elements[index] = info
            self.save()

    def __len__(self):
        return len(self.elements)
