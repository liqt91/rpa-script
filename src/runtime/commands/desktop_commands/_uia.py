"""UIAutomation 工具库 — _uia.py

封装 Windows UI Automation COM 接口，提供控件查找、点击、输入等操作。
基于 uiautomation 库（需 pip install uiautomation）。
"""

import os
import sys
from pathlib import Path


# ── 懒加载，不需要 UIA 的环境不会报错 ──
_uia_module = None


def _venv_site_packages() -> str | None:
    """定位项目 venv 的 site-packages 目录。

    后端可能被任意解释器拉起（uv 基解释器、裸 python 等），其环境里可能没有
    uiautomation。运行时 UIA 命令需要在此类解释器上也能工作 —— 退而加载项目
    venv（.venv/venv）里安装好的 uiautomation。仅当 venv 的 Python 主次版本与
    当前解释器一致时才使用（ABI 兼容），否则保持不可用并交给 is_uia_available
    报错。
    """
    try:
        root = Path(__file__).resolve().parents[4]  # src/runtime/commands/desktop_commands/_uia.py -> 项目根
    except IndexError:
        return None
    for env in (".venv", "venv"):
        sp = root / env / "Lib" / "site-packages"
        if not sp.is_dir():
            continue
        # 校验 venv 的 Python 版本与当前解释器一致
        cfg = root / env / "pyvenv.cfg"
        if cfg.exists():
            try:
                ver = next(
                    line.split("=", 1)[1].strip()
                    for line in cfg.read_text(encoding="utf-8").splitlines()
                    if line.strip().lower().startswith("version")
                )
                vparts = ver.split(".")
                if len(vparts) >= 2 and (int(vparts[0]), int(vparts[1])) != sys.version_info[:2]:
                    continue
            except (ValueError, OSError):
                continue
        return str(sp)
    return None


def _get_uia():
    """懒加载 uiautomation 模块（当前解释器缺依赖时回退到项目 venv）。"""
    global _uia_module
    if _uia_module is None:
        try:
            import uiautomation as uia
        except ImportError:
            sp = _venv_site_packages()
            if sp and os.name == "nt":
                # 追加到末尾，避免遮蔽当前解释器已有的同名包
                sys.path.append(sp)
                import uiautomation as uia
            else:
                raise
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


def find_window_by_class(class_name: str) -> dict | None:
    """按类名查找顶层窗口（混合架构应用如 Windows Terminal：标题随激活标签变化，类名稳定）。"""
    if not class_name:
        return None
    uia = _get_uia()
    desktop = uia.GetRootControl()
    try:
        ctrl = desktop.WindowControl(ClassName=class_name, Depth=1)
        if ctrl and ctrl.Exists(0, 0):
            return _ctrl_to_dict(ctrl)
    except Exception:
        pass
    return None


def find_child_by_name(parent_uia, name: str, control_type: str = None, depth: int = 5) -> dict | None:
    """在 UIA 父控件下按名称查找子控件。"""
    _get_uia()
    parent = _to_uia_control(parent_uia)
    if not parent:
        return None
    kwargs = {"Name": name, "Depth": depth}
    if control_type:
        ctrl = parent.__getattribute__(control_type)(Name=name, Depth=depth)
    else:
        ctrl = parent.Control(**kwargs)
    if ctrl and ctrl.Exists(0, 0):
        return _ctrl_to_dict(ctrl)
    return None


def find_child_by_class(parent_uia, class_name: str, depth: int = 5) -> dict | None:
    """在 UIA 父控件下按类名查找子控件。"""
    _get_uia()
    parent = _to_uia_control(parent_uia)
    if not parent:
        return None
    ctrl = parent.Control(ClassName=class_name, Depth=depth)
    if ctrl and ctrl.Exists(0, 0):
        return _ctrl_to_dict(ctrl)
    return None


def find_child_by_auto_id(parent_uia, automation_id: str, depth: int = 5) -> dict | None:
    """在 UIA 父控件下按 AutomationId 查找子控件。"""
    _get_uia()
    parent = _to_uia_control(parent_uia)
    if not parent:
        return None
    ctrl = parent.Control(AutomationId=automation_id, Depth=depth)
    if ctrl and ctrl.Exists(0, 0):
        return _ctrl_to_dict(ctrl)
    return None


def find_child_by_enum(parent_uia, info: dict) -> dict | None:
    """兜底子级定位：uiautomation 的 .Control(...) 条件搜索对部分应用（Win11 记事本等）
    恒失败 —— GetChildren() 直接枚举可见，但 ClassName/AutomationId/Name 条件搜索
    exists=False。此时直接枚举父级子控件，按路径信息（index/control_type/name/
    class_name/automation_id）匹配。"""
    parent = _to_uia_control(parent_uia)
    if parent is None:
        return None
    want_index = info.get("index")
    want_type = (info.get("control_type") or "").strip().lower()
    want_name = (info.get("name") or "").strip()
    want_class = (info.get("class_name") or "").strip()
    want_aid = (info.get("automation_id") or "").strip()
    try:
        children = parent.GetChildren()
    except Exception:
        return None
    for i, c in enumerate(children):
        if want_index is not None and i != want_index:
            continue
        try:
            if want_type and (c.ControlTypeName or "").lower() != want_type:
                continue
            if want_name and (c.Name or "").strip() != want_name:
                continue
            if want_class and (c.ClassName or "").strip() != want_class:
                continue
            if want_aid and (c.AutomationId or "").strip() != want_aid:
                continue
        except Exception:
            continue
        return _ctrl_to_dict(c)
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


def find_child_by_index(parent_uia, index: int, control_type: str = None,
                        class_name: str = "") -> dict | None:
    """按兄弟序号精确定位直接子控件（index = 父级 GetChildren 列表中的第几个，0 起）。
    control_type/class_name 仅作校验（类型漂移时回退 None，由调用方走模糊策略）。"""
    _get_uia()
    parent = _to_uia_control(parent_uia)
    if not parent or index is None or index < 0:
        return None
    try:
        children = parent.GetChildren()
    except Exception:
        return None
    if index >= len(children):
        return None
    child = children[index]
    try:
        if control_type and child.ControlTypeName != control_type:
            return None
        if class_name and (child.ClassName or "") != class_name:
            return None
    except Exception:
        return None
    return _ctrl_to_dict(child)


# ── 元素库路径导航 ──

def pick_from_path(path_json: list, level_index: int = -1,
                   target_index: int = None) -> dict | None:
    """从控件层级路径中按序号定位 UIA 控件。

    path_json: 元素库中存的全路径 [{name, class_name, control_type, automation_id, index, ...}, ...]
    level_index: 0=顶层, -1=目标层级（target_index 有效时优先，否则最后一层）
    target_index: 捕获时目标元素在 path 中的层级序号（完整链 root→leaf 时定位目标用）

    返回 {name, class_name, control_type, automation_id, rect, uia_element}
    """
    if not path_json:
        return None

    if level_index < 0:
        if target_index is not None and 0 <= target_index < len(path_json):
            level_index = target_index
        else:
            level_index = max(0, len(path_json) + level_index)
    if level_index >= len(path_json):
        level_index = len(path_json) - 1

    _get_uia()
    target = None

    def _resolve_top(info):
        """顶层窗口定位：标题精确 → 模糊 → 类名（混合应用标题会变，类名兜底）。"""
        name = (info.get("name") or "").strip()
        if name:
            t = find_window_by_title(name)
            if not t:
                fuzzy = find_window_by_title_fuzzy(name)
                if fuzzy:
                    t = fuzzy[0]
            if t:
                return t
        return find_window_by_class(info.get("class_name", ""))

    if level_index == 0:
        info = path_json[0]
        target = _resolve_top(info)
    else:
        # 先找顶层
        top = path_json[0]
        parent = _resolve_top(top)

        if not parent:
            return None

        # 逐层下钻
        for i in range(1, level_index + 1):
            info = path_json[i]
            child = None
            # 1) 兄弟序号精确定位（新格式捕获，含 index）
            if info.get("index") is not None:
                child = find_child_by_index(parent, info.get("index"),
                                            control_type=info.get("control_type") or None,
                                            class_name=info.get("class_name", ""))
            # 2) 回退：automation_id → name → class
            if not child:
                child = find_child_by_auto_id(parent, info.get("automation_id", ""))
            if not child:
                child = find_child_by_name(parent, info.get("name", ""))
            if not child:
                child = find_child_by_class(parent, info.get("class_name", ""))
            if not child:
                # 3) 兜底：条件搜索失效（Win11 记事本等）→ 直接枚举子级按信息匹配
                child = find_child_by_enum(parent, info)
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
    _get_uia()
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
