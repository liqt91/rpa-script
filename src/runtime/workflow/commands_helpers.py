"""Command field helpers — extracted from legacy commands.py."""
import copy


def _element_name_field(required: bool = True) -> dict:
    return {"name": "element_name", "label": "元素", "type": "element", "required": required, "isPrimaryElement": True}

def _timeout_field(default: int = 10) -> dict:
    return {"name": "timeout", "label": "超时(秒)", "type": "number", "default": default, "group": "advanced"}

def _var_field(name: str = "varName", label: str = "保存到变量") -> dict:
    return {"name": name, "label": label, "type": "string", "required": False, "group": "output"}

def _window_var_field() -> dict:
    return {"name": "windowVar", "label": "窗口变量", "type": "string", "required": False, "default": "browser1", "placeholder": "如 browser1", "group": "input"}

def _scope_field() -> dict:
    return {
        "name": "scope", "label": "匹配范围", "type": "select",
        "options": [
            {"label": "在当前外层元素内查找", "value": "local"},
            {"label": "全页面匹配", "value": "global"},
        ],
        "default": "local", "group": "advanced",
    }

def _on_error_field(default: str = "stop") -> dict:
    return {
        "name": "onError", "label": "执行失败时", "type": "select",
        "options": [{"label": "停止", "value": "stop"}, {"label": "继续", "value": "continue"}, {"label": "重试", "value": "retry"}],
        "default": default, "group": "advanced",
    }

def _retry_count_field(default: int = 3) -> dict:
    return {"name": "retryCount", "label": "重试次数", "type": "number", "default": default, "group": "advanced"}

def _visibility_mode_field() -> dict:
    return {
        "name": "visibilityMode", "label": "元素可见性", "type": "select",
        "options": [{"label": "匹配可见元素", "value": "visible"}, {"label": "匹配所有元素", "value": "any"}],
        "default": "visible", "group": "advanced",
    }

def _use_relative_field() -> dict:
    return {"name": "useRelative", "label": "使用相对解析", "type": "boolean", "default": True, "group": "anchor"}

def _loop_anchor_field() -> dict:
    return {"name": "loopAnchor", "label": "锚点元素", "type": "select", "options": [{"label": "最近外层循环", "value": ""}], "default": "", "group": "anchor"}

def _reference_item_field() -> dict:
    return {"name": "referenceItemItself", "label": "引用循环项本身", "type": "boolean", "default": False, "group": "anchor"}


def _attach_common_advanced(fields: list[dict]) -> list[dict]:
    """为指令字段列表附加通用高级参数（如果不存在）。"""
    result = copy.deepcopy(fields)
    names = {f.get("name") for f in result}
    has_element = "element_name" in names
    if "onError" not in names:
        result.append(_on_error_field())
    if "retryCount" not in names:
        result.append(_retry_count_field())
    if "timeout" not in names:
        result.append(_timeout_field())
    if has_element and "visibilityMode" not in names:
        result.append(_visibility_mode_field())
    if has_element and "useRelative" not in names:
        result.append(_use_relative_field())
    if has_element and "loopAnchor" not in names:
        result.append(_loop_anchor_field())
    if has_element and "referenceItemItself" not in names:
        result.append(_reference_item_field())
    if "humanLike" not in names:
        result.append({"name": "humanLike", "label": "拟人化操作", "type": "boolean", "default": True, "group": "advanced"})
    return result
