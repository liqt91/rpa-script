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
        "name": "onError", "label": "执行失败时", "type": "select",
        "options": [{"label": "停止", "value": "stop"}, {"label": "继续", "value": "continue"}, {"label": "重试", "value": "retry"}],
        "default": "stop", "group": "advanced",
    },
    {
        "name": "retryCount", "label": "重试次数", "type": "number",
        "default": 3, "group": "advanced",
    },
    {
        "name": "timeout", "label": "超时(秒)", "type": "number",
        "default": 10, "group": "advanced",
    },
    {
        "name": "humanLike", "label": "模拟人工操作", "type": "bool",
        "default": True, "group": "advanced",
    },
    {
        "name": "description", "label": "步骤说明", "type": "textarea",
        "default": "", "group": "advanced",
    },
]


@dataclass
class Param:
    """Handler 参数声明。handler 内部通过 `params["name"]` 读取。"""
    name: str                                    # 参数名，handler 代码中读取的 key
    label: str = ""                              # 编辑器显示标签
    type: str = "text"                           # text | number | bool | select | varName | elementName | textarea | code
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
    runtime: str = "extension",  # "extension" | "backend" | "emitter"
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
      - "emitter": 由 emitter 展开，不经过 handler 执行（容器/结构指令）
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
        runtime_cfg = {}
        if hdef["runtime"] == "backend":
            runtime_cfg = {"handler": handler_type, "local": True}
        else:
            runtime_cfg = {"handler": hdef["runtime_handler"] if "runtime_handler" in hdef else handler_type, "local": False}

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
            "fields": hdef["params"],  # handler params = command fields
            "description": hdef["description"],
            "categoryOrder": hdef["categoryOrder"],
            "commandOrder": hdef["commandOrder"],
            "enabled": hdef["enabled"],
            "runtimes": {"extension": runtime_cfg},
        }
        registry[handler_type] = entry
    return registry


# ─── Migrate existing commands to handler format ──────────────────

def load_builtin_handlers():
    """在 extension_runner 启动时调用，注册所有内置 handler。"""
    from . import handler_definitions  # triggers all @register_handler
