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

import base64
import json
import os
import re
from dataclasses import asdict
from scripts.capture_gui.overlay import ElementInfo


def _info_to_dict(info: ElementInfo, keep_screenshot: bool = False) -> dict:
    d = asdict(info)
    d.pop("hwnd", None)
    if not keep_screenshot:
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
        uia_target_index=d.get("uia_target_index", -1),
        uia_available=d.get("uia_available", True),
        elevation_blocked=d.get("elevation_blocked", False),
        css_selector=d.get("css_selector", ""),
        xpath=d.get("xpath", ""),
        tag_name=d.get("tag_name", ""),
        win32_path=d.get("win32_path", []),
        candidates=d.get("candidates", []),
        screenshot=d.get("screenshot", ""),
        dom_path=d.get("dom_path", []),
        elem_attrs=d.get("elem_attrs", {}),
        dom_editor_path=d.get("dom_editor_path", []),
        attrs=d.get("attrs", {}),
        list_info=d.get("list_info", {}),
        page_url=d.get("page_url", ""),
        region=d.get("region", {}),
        threshold=d.get("threshold", 0.8),
        match_method=d.get("match_method", "template"),
        screen_size=d.get("screen_size", {}),
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


# ---------------------------------------------------------------------------
# 工作区（一目录一流程）就地写回
# 与 src/runtime/routers/project_router.project_save_element 产出同构的 entry
# （element_type/web_selector/css_candidates/.../image），供 capture 进程直接
# 把捕获元素落进工作区 elements.json，不依赖 runtime/fastapi 层。
#
# 写回协议（capture-unification-plan v2.2）：捕获只写 elements.json，不碰
# workflow.json —— 编辑器对 workflow.json 是整文档读-改-写，捕获写进去会被
# 编辑器下次保存用旧内存副本覆盖；拆文件后写入域分离，竞态工程性消除。
# ---------------------------------------------------------------------------


def _partition_candidates(candidates):
    """[{family,syntax}] → (css, xpath)（drission 一并归入 css 兜底决策略，这里只分类）。"""
    css, xpath, other = [], [], []
    for c in candidates or []:
        fam = (c.get("family") or c.get("type") or "css").lower()
        if fam in ("css", "drission"):
            css.append({"family": fam, "syntax": c.get("syntax", "")})
        elif fam == "xpath":
            xpath.append({"family": "xpath", "syntax": c.get("syntax", "")})
    return css, xpath, other


def _safe_name(name):
    return "".join(c for c in (name or "") if c.isalnum() or c in ("_", "-")) or "element"


def _persist_screenshot(images_dir, name, screenshot):
    """把 base64/dataURL 截图落盘 images/<safe>.png，返回相对路径或 None。"""
    if not screenshot or not isinstance(screenshot, str):
        return None
    s = screenshot.strip()
    m = re.match(r"^data:[^;]+;base64,(.*)$", s, re.S) if s.startswith("data:") else None
    raw = m.group(1) if m else (s if "," not in s else "")
    try:
        b = base64.b64decode(raw, validate=False) if raw else b""
    except Exception:
        return None
    if not b or not (b.startswith(b"\x89PNG") or b.startswith(b"\xff\xd8")):
        return None
    safe = _safe_name(name)
    images_dir.mkdir(parents=True, exist_ok=True)
    (images_dir / f"{safe}.png").write_bytes(b)
    return f"images/{safe}.png"


def save_element_to_workspace(workspace, info: dict, name=None):
    """把捕获元素（info dict，_info_to_dict 产物）就地写进工作区目录。

    写 elements.json 的 elements（同名替换，原子写） + screenshot 落 images/。
    不碰 workflow.json（编辑器对它整文档读-改-写，写进去会被旧内存副本覆盖）。
    返回 {ok, name, count} 或抛 ValueError（非流程工作区 / 无名称）。
    """
    from pathlib import Path

    root = Path(workspace)
    if not (root / "rpa.json").is_file():
        raise ValueError("该目录不是 RPA 流程工作区（缺少 rpa.json）")
    name = (name or info.get("name") or "").strip()
    if not name:
        # 无名称时用 css_selector / 控件类型生成显示名
        cs = (info.get("css_selector") or "")
        name = cs.strip("#. ") or info.get("control_type") or "捕获元素"

    # elements.json 布局：{"version": 1, "elements": [...]}（缺文件时新建）
    el_path = root / "elements.json"
    if el_path.exists():
        try:
            edata = json.loads(el_path.read_text(encoding="utf-8-sig"))
        except Exception:
            edata = {}
    else:
        edata = {}
    if not isinstance(edata, dict):
        edata = {}
    elements = edata.setdefault("elements", [])
    if not isinstance(elements, list):
        edata["elements"] = elements = []

    et = info.get("element_type", "web")
    if et == "web":
        candidates = info.get("candidates") or []
        css, xpath, _ = _partition_candidates(candidates)
        selector = info.get("css_selector")
        if not selector and css:
            selector = css[0].get("syntax", "")
        if not selector and xpath:
            selector = xpath[0].get("syntax", "")
        attrs = dict(info.get("elem_attrs") or {})
        attrs.setdefault("element_type", "web")
        dom_path = info.get("dom_path") or []
        img_rel = _persist_screenshot(root / "images", name, info.get("screenshot"))
        if img_rel:
            attrs["imagePath"] = img_rel
        entry = {
            "name": name,
            "element_type": "web",
            "element_kind": "plain",
            "web_selector": selector[:4000],
            "css_candidates": css,
            "xpath_candidates": xpath,
            "drission_candidates": [],
            "dom_path": dom_path,
            "attributes": attrs,
            "page_url": info.get("page_url", ""),
            "image": img_rel,
            "screenshot": info.get("screenshot"),
            "anchor_element_name": info.get("anchor_element_name"),
            "relative_selector": info.get("relative_selector", ""),
        }
    else:
        # 桌面：win32/uia 祖先链
        uia_path = info.get("uia_path") or []
        win32_path = info.get("win32_path") or []
        if uia_path:
            et = "uia"
            tidx = info.get("uia_target_index", -1)
            leaf = uia_path[tidx] if isinstance(uia_path[tidx], dict) else {}
            path = uia_path
            attrs = {
                "element_type": "uia",
                "name": leaf.get("name", "") or info.get("name", ""),
                "class_name": leaf.get("class_name", "") or info.get("class_name", ""),
                "control_type": leaf.get("control_type", ""),
                "automation_id": leaf.get("automation_id", ""),
                "uia_target_index": tidx,
            }
        else:
            et = "win32"
            path = win32_path or info.get("path") or []
            attrs = {
                "element_type": "win32",
                "hwnd": info.get("hwnd", 0),
                "class_name": info.get("class_name", ""),
                "title": info.get("title", ""),
            }
        attrs["path"] = path
        img_rel = _persist_screenshot(root / "images", name, info.get("screenshot"))
        if img_rel:
            attrs["imagePath"] = img_rel
        entry = {
            "name": name,
            "element_type": et,
            "element_kind": "plain",
            "web_selector": "",
            "css_candidates": [],
            "xpath_candidates": [],
            "drission_candidates": [],
            "dom_path": [],
            "attributes": attrs,
            "page_url": info.get("page_url", ""),
            "image": img_rel,
            "screenshot": info.get("screenshot"),
            "anchor_element_name": info.get("anchor_element_name"),
            "relative_selector": info.get("relative_selector", ""),
        }

    idx = next((i for i, e in enumerate(elements) if e.get("name") == name), None)
    if idx is not None:
        elements[idx] = entry
    else:
        elements.append(entry)
    edata.setdefault("version", 1)
    raw = json.dumps(edata, ensure_ascii=False, indent=2)
    tmp = el_path.with_suffix(".tmp")
    tmp.write_text(raw, encoding="utf-8")
    tmp.replace(el_path)
    return {"ok": True, "name": name, "count": len(elements)}
