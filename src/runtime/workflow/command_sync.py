"""指令种子同步 — registry → DB（WorkflowCommand）。

从 main.py 抽出，供启动流程与热重载（/api/commands/reload）共用，
避免 commands_router → main 的循环导入。
"""
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent


def read_handler_from_json(type_name: str):
    """读取根目录 commands/<type>.json 的 handler 字段（生成桩/实现指向）。"""
    jp = _ROOT / "commands" / f"{type_name}.json"
    if jp.exists():
        with open(jp, encoding="utf-8") as f:
            return json.load(f).get("handler")
    return None


def seed_commands_to_db(db):
    """将 handler 系统中的内置指令种子同步到数据库。

    - 首次安装：插入所有内置指令。
    - 后续启动/热重载：用代码种子更新已有内置指令（保持自定义指令不变）。
    - 自定义指令（is_builtin=0）永远不会被覆盖。
    """
    from src.repo import models
    from .handlers.registry import build_command_registry

    registry = build_command_registry()
    existing = {row.cmd: row for row in db.query(models.WorkflowCommand).all()}
    for type_name, cmd in registry.items():
        row = existing.get(type_name)
        if row is not None and not row.is_builtin:
            continue

        ext = cmd.get("runtimes", {}).get("extension")
        handler_json = read_handler_from_json(type_name)
        fields = {
            "label": cmd.get("label", type_name),
            "category": cmd.get("category", "其他"),
            "icon": cmd.get("icon", "fa-circle"),
            "icon_color": cmd.get("iconColor", "text-gray-500"),
            "bg_color": cmd.get("bgColor", "bg-gray-50"),
            "is_container": 1 if cmd.get("isContainer") else 0,
            "is_branch": 1 if cmd.get("isBranch") else 0,
            "is_structural": 1 if cmd.get("isStructural") else 0,
            "closes_with": cmd.get("closesWith"),
            "fields": json.dumps(cmd.get("fields", []), ensure_ascii=False),
            "description": cmd.get("description", ""),
            "is_builtin": 1,
            "enabled": 1 if cmd.get("enabled", True) else 0,
            "handler": json.dumps(handler_json) if handler_json else (ext.get("handler") if ext else None),
            "local": 1 if ext and ext.get("local") else 0,
            "category_order": cmd.get("categoryOrder", 0),
            "command_order": cmd.get("commandOrder", 0),
        }
        if row is None:
            db.add(models.WorkflowCommand(cmd=type_name, **fields))
        else:
            for key, value in fields.items():
                setattr(row, key, value)
    db.commit()
