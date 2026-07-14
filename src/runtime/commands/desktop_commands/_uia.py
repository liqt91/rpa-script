"""UIAutomation 工具库 — _uia.py

封装 Windows UI Automation COM 接口，提供控件查找、点击、输入等操作。
基于 uiautomation 库（需 pip install uiautomation）。
"""


# ── 懒加载，不需要 UIA 的环境不会报错 ──
_uia_module = None


def _get_uia():
    """懒加载 uiautomation 模块。"""
    global _uia_module
    if _uia_module is None:
        import uiautomation as uia
        _uia_module = uia
    return _uia_module


def is_uia_available() -> bool:
    """检查 UIA 是否可用。"""
    try:
        _get_uia()
        return True
    except ImportError:
        return False


# ── 核心查找函数 ──

def find_window_by_title(title: str, depth: int = 3) -> dict | None:
    """按标题查找顶层窗口（UIA 方式）。
    
    使用 UIA 的 Desktop 为根，搜索匹配标题的窗口。
    返回 {name, class_name, automation_id, control_type, rect, uia_element}。
    """
    uia = _get_uia()
    desktop = uia.GetRootControl()
    ctrl = desktop.WindowControl(Name=title, Depth=depth)
    if ctrl and ctrl.Exists(0, 0):
        return _ctrl_to_dict(ctrl)
    return None


def find_window_by_title_fuzzy(title: str, depth: int = 3) -> list[dict]:
    """模糊标题匹配查找窗口。"""
    uia = _get_uia()
    desktop = uia.GetRootControl()
    results = []
    for win in desktop.GetChildren():
        try:
            if win.ControlTypeName in ("WindowControl", "PaneControl"):
                name = win.Name or ""
                if title.lower() in name.lower():
                    results.append(_ctrl_to_dict(win))
        except Exception:
            continue
    return results


def find_child_by_name(parent_uia, name: str, control_type: str = None, depth: int = 5) -> dict | None:
    """在 UIA 父控件下按名称查找子控件。"""
    uia = _get_uia()
    parent = _to_uia_control(parent_uia)
    if not parent:
        return None
    kwargs = {"Name": name, "Depth": depth}
    ctrl = parent.Control(**kwargs) if not control_type else parent.__getattribute__(control_type)(Name=name, Depth=depth)
    if ctrl and ctrl.Exists(0, 0):
        return _ctrl_to_dict(ctrl)
    return None


def find_child_by_class(parent_uia, class_name: str, depth: int = 5) -> dict | None:
    """在 UIA 父控件下按类名查找子控件。"""
    uia = _get_uia()
    parent = _to_uia_control(parent_uia)
    if not parent:
        return None
    ctrl = parent.Control(ClassName=class_name, Depth=depth)
    if ctrl and ctrl.Exists(0, 0):
        return _ctrl_to_dict(ctrl)
    return None


def find_child_by_auto_id(parent_uia, automation_id: str, depth: int = 5) -> dict | None:
    """在 UIA 父控件下按 AutomationId 查找子控件。"""
    uia = _get_uia()
    parent = _to_uia_control(parent_uia)
    if not parent:
        return None
    ctrl = parent.Control(AutomationId=automation_id, Depth=depth)
    if ctrl and ctrl.Exists(0, 0):
        return _ctrl_to_dict(ctrl)
    return None


# ── 操作函数 ──

def click_element(uia_ctrl: dict) -> bool:
    """点击 UIA 控件。使用 InvokePattern 或模拟点击。"""
    try:
        ctrl = _to_uia_control(uia_ctrl)
        if not ctrl:
            return False
        ctrl.Click()
        return True
    except Exception:
        return False


def set_text(uia_ctrl: dict, text: str) -> bool:
    """向 UIA 控件设置文本。使用 ValuePattern 或 SendKeys。"""
    try:
        ctrl = _to_uia_control(uia_ctrl)
        if not ctrl:
            return False
        # 尝试 ValuePattern
        try:
            vp = ctrl.GetValuePattern()
            if vp:
                vp.SetValue(text)
                return True
        except Exception:
            pass
        # 降级：SendKeys
        ctrl.SendKeys(text)
        return True
    except Exception:
        return False


def get_text(uia_ctrl: dict) -> str:
    """获取 UIA 控件文本。"""
    try:
        ctrl = _to_uia_control(uia_ctrl)
        if not ctrl:
            return ""
        return ctrl.Name or ""
    except Exception:
        return ""


def get_control_type(uia_ctrl: dict) -> str:
    """获取控件类型名称。"""
    try:
        ctrl = _to_uia_control(uia_ctrl)
        if not ctrl:
            return ""
        return ctrl.ControlTypeName or ""
    except Exception:
        return ""


# ── 元素库路径导航 ──

def pick_from_path(path_json: list, level_index: int = -1) -> dict | None:
    """从控件层级路径中按序号定位 UIA 控件。
    
    path_json: 元素库中存的全路径 [{name, class_name, control_type, automation_id, ...}, ...]
    level_index: 0=顶层, -1=最后一层
    
    返回 {name, class_name, control_type, automation_id, rect, uia_element}
    """
    if not path_json:
        return None

    if level_index < 0:
        level_index = max(0, len(path_json) + level_index)
    if level_index >= len(path_json):
        level_index = len(path_json) - 1

    uia = _get_uia()
    target = None

    if level_index == 0:
        info = path_json[0]
        target = find_window_by_title(info.get("name", ""))
    else:
        # 先找顶层
        top = path_json[0]
        parent = find_window_by_title(top.get("name", ""))
        if not parent:
            parent = find_window_by_title_fuzzy(top.get("name", ""))
            if parent:
                parent = parent[0]

        if not parent:
            return None

        # 逐层下钻
        for i in range(1, level_index + 1):
            info = path_json[i]
            child = find_child_by_auto_id(parent, info.get("automation_id", ""))
            if not child:
                child = find_child_by_name(parent, info.get("name", ""))
            if not child:
                child = find_child_by_class(parent, info.get("class_name", ""))
            if not child:
                return None  # 某层没找到
            parent = child

        target = parent if level_index > 0 else None

    return target


# ── 工具函数 ──

def _ctrl_to_dict(ctrl) -> dict:
    """将 uiautomation 控件转为可序列化字典。"""
    try:
        rect = ctrl.BoundingRectangle
    except Exception:
        rect = None
    return {
        "name": ctrl.Name or "",
        "class_name": ctrl.ClassName or "",
        "control_type": ctrl.ControlTypeName or "",
        "automation_id": ctrl.AutomationId or "",
        "rect": {
            "left": rect.left if rect else 0,
            "top": rect.top if rect else 0,
            "right": rect.right if rect else 0,
            "bottom": rect.bottom if rect else 0,
            "width": rect.width() if rect else 0,
            "height": rect.height() if rect else 0,
        },
        "_uia_ctrl": ctrl,  # 不可序列化，仅内存使用
    }


def _to_uia_control(ctrl_dict: dict):
    """从字典中取 UIA 控件对象。"""
    if isinstance(ctrl_dict, dict) and "_uia_ctrl" in ctrl_dict:
        return ctrl_dict["_uia_ctrl"]
    return None


def get_ancestor_chain(ctrl) -> list[dict]:
    """获取从根到目标控件的完整路径。"""
    uia = _get_uia()
    chain = []
    current = _to_uia_control(ctrl) if isinstance(ctrl, dict) else ctrl
    if not current:
        return chain
    try:
        while current:
            chain.insert(0, _ctrl_to_dict(current))
            parent = current.GetParentControl()
            if not parent or parent.ControlTypeName == "DesktopControl":
                break
            current = parent
    except Exception:
        pass
    return chain
