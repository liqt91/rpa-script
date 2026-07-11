"""
Handler 注册系统 — 每个 handler 声明自己的参数，自动生成指令配置。

使用方式:
    @register_handler(
        type="getText",
        label="获取文本",
        category="数据提取",
        runtime="extension",
        icon="fa-font",
    )
    class GetTextHandler:
        params = [Param(...), Param(...)]
"""

from typing import Optional, Any
from dataclasses import dataclass, field

# ─── Generic params injected into every instruction ──────────────

GENERIC_PARAMS = [
    {
        "name": "onError", "label": "执行失败时", "type": "str-dropdown",
        "options": [{"label": "停止", "value": "stop"}, {"label": "继续", "value": "continue"}, {"label": "重试", "value": "retry"}],
        "default": "stop", "group": "advanced",
    },
    {
        "name": "retryCount", "label": "重试次数", "type": "int-number",
        "default": 3, "group": "advanced",
    },
    {
        "name": "timeout", "label": "超时(秒)", "type": "int-number",
        "default": 10, "group": "advanced",
    },
    {
        "name": "humanLike", "label": "模拟人工操作", "type": "bool-check",
        "default": True, "group": "advanced",
    },
    {
        "name": "description", "label": "步骤说明", "type": "str-textarea",
        "default": "", "group": "advanced",
    },
]


@dataclass
class Param:
    """Handler 参数声明。handler 内部通过 `params["name"]` 读取。"""
    name: str                                    # 参数名，handler 代码中读取的 key
    label: str = ""                              # 编辑器显示标签
    type: str = "str-input"                         # str-input | str-textarea | str-var | str-dropdown | str-element | int-number | bool-check | list-input | dict-input | any-expr | any-input
    required: bool = False
    default: Any = None
    group: str = "主属性"                         # 主属性 | advanced | output | input | anchor
    options: list | None = None                  # type=select 时的选项
    placeholder: str = ""
    description: str = ""

    def to_dict(self) -> dict:
        d = {"name": self.name, "label": self.label or self.name, "type": self.type, "group": self.group}
        if self.required: d["required"] = True
        if self.default is not None: d["default"] = self.default
        if self.options: d["options"] = self.options
        if self.placeholder: d["placeholder"] = self.placeholder
        if self.description: d["description"] = self.description
        return d


# ─── Handler registry ────────────────────────────────────────────

_HANDLER_REGISTRY: dict[str, dict] = {}  # type -> handler definition


def register_handler(
    type: str,
    label: str,
    category: str,
    runtime: str = "extension",  # "extension" | "backend" | "control"
    icon: str = "fa-circle",
    icon_color: str = "text-gray-500",
    bg_color: str = "bg-gray-50",
    is_container: bool = False,
    is_branch: bool = False,
    is_structural: bool = False,
    closes_with: str | None = None,
    description: str = "",
    category_order: int = 0,
    command_order: int = 0,
    enabled: bool = True,
):
    """装饰器：注册一个 handler 及其参数声明。
    
    runtime 值:
      - "extension": 浏览器扩展执行 (content.js)
      - "backend": 后端本地执行 (extension_runner.py LOCAL_HANDLERS)
      - "control": 由 emitter 展开，不经过 handler 执行（容器/结构指令）
    """
    def decorator(cls):
        params = []
        if hasattr(cls, "params"):
            for p in cls.params:
                params.append(p.to_dict() if isinstance(p, Param) else p)

        _HANDLER_REGISTRY[type] = {
            "type": type,
            "label": label,
            "category": category,
            "runtime": runtime,
            "icon": icon,
            "iconColor": icon_color,
            "bgColor": bg_color,
            "isContainer": is_container,
            "isBranch": is_branch,
            "isStructural": is_structural,
            "closesWith": closes_with,
            "params": params,
            "description": description or (cls.__doc__ or "").strip(),
            "categoryOrder": category_order,
            "commandOrder": command_order,
            "enabled": enabled,
            "handler_class": cls,
        }
        return cls
    return decorator


def get_handler(type_name: str) -> dict | None:
    """返回 handler 定义（含 params）。"""
    return _HANDLER_REGISTRY.get(type_name)


def get_all_handlers() -> dict[str, dict]:
    """返回所有已注册的 handler。"""
    return dict(_HANDLER_REGISTRY)


def build_command_registry() -> dict[str, dict]:
    """从 handler 注册表 + 数据库覆盖 构建 COMMAND_REGISTRY。

    返回格式兼容原有的 COMMAND_REGISTRY 结构。
    """
    registry = {}
    for handler_type, hdef in _HANDLER_REGISTRY.items():
        if hdef["runtime"] == "backend":
            runtimes = {"extension": {"handler": handler_type, "local": True}}
        elif hdef["runtime"] == "extension":
            runtimes = {"extension": {"handler": hdef.get("runtime_handler", handler_type), "local": False}}
        else:
            # emitter / flow-control 指令没有运行时 handler
            runtimes = {}

        is_structural = hdef.get("isContainer") or hdef.get("isBranch") or hdef.get("isStructural")

        entry = {
            "type": handler_type,
            "label": hdef["label"],
            "category": hdef["category"],
            "icon": hdef["icon"],
            "iconColor": hdef["iconColor"],
            "bgColor": hdef["bgColor"],
            "isContainer": hdef["isContainer"],
            "isBranch": hdef["isBranch"],
            "isStructural": hdef["isStructural"],
            "closesWith": hdef["closesWith"],
            "fields": hdef["params"],
            "description": hdef["description"],
            "categoryOrder": hdef["categoryOrder"],
            "commandOrder": hdef["commandOrder"],
            "enabled": hdef["enabled"],
            "runtimes": runtimes,
        }
        registry[handler_type] = entry
    return registry


def get_command(type_name: str) -> dict | None:
    """从 handler 注册表获取指令定义。"""
    h = get_handler(type_name)
    if not h:
        return None

    is_structural = h.get("isContainer") or h.get("isBranch") or h.get("isStructural")
    is_control = h["runtime"] == "control"
    fields = h["params"] if is_structural else h["params"] + GENERIC_PARAMS

    return {
        "type": h["type"], "label": h["label"], "category": h["category"],
        "icon": h["icon"], "iconColor": h["iconColor"], "bgColor": h["bgColor"],
        "isContainer": h["isContainer"], "isBranch": h["isBranch"],
        "isStructural": h["isStructural"], "closesWith": h["closesWith"],
        "fields": fields, "description": h["description"],
        "categoryOrder": h["categoryOrder"], "commandOrder": h["commandOrder"],
        "enabled": h.get("enabled", True), "isBuiltin": True,
        "runtimes": {"extension": {
            "handler": None if is_control else h["type"],
            "local": h["runtime"] == "backend",
            "emitter": is_control,
        }},
    }


def list_categories() -> list[str]:
    """返回所有分类名称（去重且保持注册顺序）"""
    seen = set()
    result = []
    for cmd in _HANDLER_REGISTRY.values():
        cat = cmd.get("category", "其他")
        if cat not in seen:
            seen.add(cat)
            result.append(cat)
    return result


def list_commands_by_category() -> dict[str, list[dict]]:
    """按分类分组返回指令列表"""
    result: dict[str, list[dict]] = {}
    for type_name, cmd in _HANDLER_REGISTRY.items():
        entry = get_command(type_name)
        if not entry:
            continue
        cat = entry.get("category", "其他")
        if cat not in result:
            result[cat] = []
        result[cat].append(entry)
    return result


def get_container_types() -> list[str]:
    return [t for t, h in _HANDLER_REGISTRY.items() if h.get("isContainer")]


def get_structural_types() -> list[str]:
    return [t for t, h in _HANDLER_REGISTRY.items() if h.get("isStructural")]


def get_branch_types() -> list[str]:
    return [t for t, h in _HANDLER_REGISTRY.items() if h.get("isBranch")]


# ─── Migrate existing commands to handler format ──────────────────

def load_builtin_handlers():
    """在 extension_runner 启动时调用，注册所有内置 handler。"""
    from . import handler_definitions  # triggers all @register_handler
