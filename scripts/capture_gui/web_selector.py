"""UIA 无障碍树网页元素 → CSS / XPath 选择器生成器（纯函数，无浏览器依赖）。

设计目标：把 capture_gui 从网页 UIA 树捕获到的单个元素特征（class / id / role /
aria 属性 / 可访问名 / 兄弟序号）转成一组**可定位、有打分**的 CSS / XPath 候选，
供写入元素库时产出非空 web_selector。这样网页捕获可以脱离浏览器扩展，运行时
照常按 css/xpath 定位（不再只有"DOM 链 + 图像兜底"）。

输入（单个 UIA 节点的特征 dict）：
    {
      "class_name":  "btn btn-primary",   # ClassName，空格分隔的 CSS 类
      "automation_id": "submit-btn",       # AutomationId（多为 DOM id）
      "control_type": "ButtonControl",     # ControlTypeName（由 ARIA role 映射）
      "name":        "提交",              # 可访问名（文本 / aria-label / title）
      "aria_role":   "button",            # AriaRole（可空）
      "aria_props":  {"label":"提交", "expanded":"false"},  # AriaProperties（可空）
      "index":       2,                   # 同父亲兄弟序号（可空）
      "attrs":       {},                  # 其他可选 HTML 属性线索
    }

输出：按分数降序的候选列表，每项 {family, syntax, score}，其中 syntax 形如
"css:.btn" / "xpath://button[@class='btn']"。调用方把 top css 放进 css_selector，
top xpath 放进 xpath，全部装进 candidates。

打分原则（越高越精确）：
    id(AutomationId)  >  class  >  role/tag+属性 >  name文本 > 兄弟序号
    - 每候选叠加"额外约束越多分越高"（属性/文本能显著唯一化）。
"""

from __future__ import annotations

# ControlTypeName → 候选 HTML 标签（Chromium 把 ARIA role 映射为 UIA control type，
# 反向映射回常见标签）。若 AriaRole 提供了更准确语义，优先用 role 而非标签。
_CONTROL_TYPE_TAG = {
    "EditControl":             "input",
    "ComboBoxControl":         "input",
    "ButtonControl":           "button",
    "SplitButtonControl":      "button",
    "HyperlinkControl":        "a",
    "ImageControl":            "img",
    "ListItemControl":         "li",
    "TabItemControl":          "[role=tab]",
    "TreeItemControl":         "[role=treeitem]",
    "RadioButtonControl":      "[role=radio]",
    "CheckBoxControl":         "[role=checkbox]",
    "SliderControl":           "[role=slider]",
    "TextControl":             "span",
    "GroupControl":            "section",
    "CustomControl":           "div",
    "PaneControl":             "div",
    "DocumentControl":         "article",
    "HeaderControl":           "header",
    "MenuItemControl":         "[role=menuitem]",
    "TabListControl":          "[role=tablist]",
    "DataGridControl":         "table",
}

# 会被当作"强语义"的 role：直接用 [role=] 定位即可（比 div 有区分度）。
_ROLE_TAG_EXACT = {
    "button", "link", "textbox", "searchbox", "checkbox", "radio", "option",
    "tab", "treeitem", "slider", "combobox", "listbox", "menuitem", "menuitemcheckbox",
}


def _esc_attr(value: str) -> str:
    """转义 XPath 属性值里的引号；CSS 属性值转义引号/反斜杠。"""
    return value.replace("'", "\\'").replace('"', '\\"')


def _esc_class_token(token: str) -> str:
    """CSS 类名 token 转义：类名中不能含空格；非法字符按 CSS.escape 简化处理。"""
    out = []
    for ch in token:
        if ch in ".#:[](){}\"' >+~" or ch.isspace():
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _classes(node: dict) -> list[str]:
    raw = (node.get("class_name") or "").strip()
    return [c for c in raw.split() if c] if raw else []


def _tag_for(node: dict) -> str:
    """标签选择器（CSS 用）：优先 AriaRole 强语义，其次 ControlTypeName 映射。"""
    role = (node.get("aria_role") or "").strip().lower()
    if role in _ROLE_TAG_EXACT:
        return f"[role={role}]"
    ct = (node.get("control_type") or "").strip()
    return _CONTROL_TYPE_TAG.get(ct, "div")


def _tag_for_xpath(node: dict) -> str:
    """标签选择器（XPath 用）：强 role 用 `*`（配合 @role 条件），否则用映射 tag。"""
    role = (node.get("aria_role") or "").strip().lower()
    if role in _ROLE_TAG_EXACT:
        return "*"
    ct = (node.get("control_type") or "").strip()
    tag = _CONTROL_TYPE_TAG.get(ct, "div")
    # ControlType 映射出的 [role=...] 形式（tab/treenode 等），XPath 用 * + @role
    return "*" if tag.startswith("[") else tag


def _css_id(node: dict) -> str | None:
    aid = (node.get("automation_id") or "").strip()
    # AutomationId 若是纯数字/生成值（如 Chromium 的 '#text'、'xx' 无 id 语义），
    # 不作为 id 用（id 选择器要求合法 CSS id，纯数字合法但很不可靠）。保留它作为属性。
    if (node.get("_aid_is_id", True) and aid and
            not any(ch in aid for ch in ".'\"[]()= ,<>")):
        return aid
    return None


def _css_id_candidate(node: dict) -> str | None:
    """纯 id 候选：. #id"""
    aid = _css_id(node)
    return f"#{_esc_class_token(aid)}" if aid else None


def _meta_attr_conds(node: dict) -> list[str]:
    """生成可用于 XPath 的属性条件 ['@role='x'', '@aria-checked='true'']，以及同源 CSS。"""
    conds: list[str] = []
    role = (node.get("aria_role") or "").strip().lower()
    if role:
        conds.append(f"@role='{_esc_attr(role)}'")
    props = node.get("aria_props") or {}
    if isinstance(props, dict):
        for k, v in props.items():
            if v == "":
                continue
            conds.append(f"@{k}='{_esc_attr(str(v))}'")
    return conds


def _role_css(node: dict) -> str:
    role = (node.get("aria_role") or "").strip().lower()
    return f"[role={role}]" if role else ""


def _name_attr_candidate(node: dict) -> tuple[str, str] | None:
    """返回 (css片段, xpath条件) 或 None。可访问名唯一化线索。"""
    name = (node.get("name") or "").strip()
    if not name:
        return None
    return (f"[aria-label='{_esc_attr(name)}']", f"@aria-label='{_esc_attr(name)}'")


def _index_candidate(node: dict, tag_css: str) -> str | None:
    idx = node.get("index")
    if not isinstance(idx, int) or idx < 0:
        return None
    # 位置选择器：父内第 N 个同级。低分，仅当没有更强候选时做兜底。
    return f"{tag_css}:nth-of-type({idx + 1})"


def _make_xpath(tag: str, id_cond: str = "", class_cond: str = "",
                attr_conds: list[str] | None = None, idx: int | None = None) -> str:
    """组合 XPath。id/class 用 contains 或 = 精确。"""
    parts = []
    if id_cond:
        parts.append(id_cond)
    if class_cond:
        parts.append(class_cond)
    for c in (attr_conds or []):
        if c:
            parts.append(c)
    path = f"//{tag}"
    if parts:
        path += "[" + " and ".join(parts) + "]"
    if isinstance(idx, int) and idx >= 0:
        path = f"({path})[{idx + 1}]"
    return path


def generate_selectors(node: dict) -> list[dict]:
    """核心入口：把节点特征转成排序后的候选列表 [{family, syntax, score}]。

    返回空列表=该节点无任何可派生定位线索（纯视觉 div 无 class/id/role/name，
    只能靠后代或图像兜底）。
    """
    classes = _classes(node)
    css_id = _css_id(node)
    tag_css = _tag_for(node)
    tag_xpath = _tag_for_xpath(node)
    idx = node.get("index")
    attr_conds = _meta_attr_conds(node)
    role_css = _role_css(node)
    name_sel = _name_attr_candidate(node)

    id_score = 100
    class_score = 60
    tag_attr_score = 30
    name_score = 25
    idx_score = 10

    cands: list[dict] = []

    # ── 1) id ──
    if css_id:
        cands.append({"family": "css", "syntax": f"#{_esc_class_token(css_id)}",
                      "score": id_score})
        cands.append({"family": "xpath",
                      "syntax": _make_xpath(tag_xpath, id_cond=f"@id='{_esc_attr(css_id)}'"),
                      "score": id_score})

    # ── 2) class ──
    if classes:
        css_cls = ".".join(_esc_class_token(c) for c in classes[:3])
        cs = f"{tag_css}.{css_cls}" if tag_css not in ("div", "") else f".{css_cls}"
        cands.append({"family": "css", "syntax": cs, "score": class_score + len(classes)})
        cls_conds = " and ".join(f"contains(concat(' ', normalize-space(@class), ' '), ' {c} ')"
                                 for c in classes[:3])
        cands.append({"family": "xpath", "syntax": _make_xpath(tag_xpath, class_cond=cls_conds),
                      "score": class_score + len(classes)})

    # ── 3) role / aria 属性 ──
    if attr_conds:
        # 强 role 已体现在 tag_css([role=x])；此时去掉重复的 role 条件
        attr_css_conds = attr_conds
        if role_css:
            attr_css_conds = [a for a in attr_css_conds if not a.startswith("@role=")]
        css_attr = role_css
        for ac in attr_css_conds:
            if ac.startswith("@") and "=" in ac:
                attr, _, val = ac[1:].partition("=")
                css_attr += f"[{attr}={val}]"
        if css_attr:
            cands.append({"family": "css", "syntax": css_attr, "score": tag_attr_score})
        cands.append({"family": "xpath", "syntax": _make_xpath(tag_xpath, attr_conds=attr_conds),
                      "score": tag_attr_score})

    # ── 4) name 可访问名（挂在 tag 上）──
    if name_sel:
        csc, xpc = name_sel
        cands.append({"family": "xpath", "syntax": _make_xpath(tag_xpath, attr_conds=[xpc]),
                      "score": name_score})
        cands.append({"family": "css", "syntax": f"{tag_css}{csc}", "score": name_score - 3})

    # ── 5) 兄弟序号（兜底）──
    if idx is not None:
        ic = _index_candidate(node, tag_css)
        if ic:
            cands.append({"family": "css", "syntax": ic, "score": idx_score})
            cands.append({"family": "xpath",
                          "syntax": _make_xpath(tag_xpath, idx=idx),
                          "score": idx_score})

    # 去重、去空、按分数降序
    seen = set()
    result = []
    for c in sorted(cands, key=lambda x: -x["score"]):
        key = (c["family"], c["syntax"])
        if key in seen or not c["syntax"]:
            continue
        seen.add(key)
        result.append(c)
    return result
