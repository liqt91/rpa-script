"""
导出指令目录到 workflow-editor 静态 JSON（阶段 3：编辑器离线可用）。

生成两个文件（放 src/ui/workflow-editor/public/，vite 构建时拷入产物）：
  - commands.json      : 与 /api/workflows/commands 同构（DB 覆盖 + handler 注册表）
  - commands-new.json  : 与 /api/workflows/commands-new 同构（commands/*.json 新目录）

用法（仓库 venv 运行）：
  python -m scripts.export_commands
或：
  .venv/Scripts/python.exe scripts/export_commands.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "src" / "ui" / "workflow-editor" / "public"


def export_legacy_commands() -> dict:
    """复刻 workflows_router.list_commands 的合并逻辑（DB 为空时纯 handler 注册表）。"""
    # 先触发 handler 注册（auto_register 会 import 各 commands 子包并自注册）
    from src.runtime.commands import auto_register
    auto_register()
    from src.runtime.workflow.handlers.registry import get_command, get_all_handlers

    all_handlers = get_all_handlers()
    # DB 不可用/为空时：用 handler 注册表全量（order 按注册顺序）
    enabled = [(cmd, idx) for idx, cmd in enumerate(all_handlers)]

    categories: list[str] = []
    commands_by_cat: dict[str, list] = {}
    enabled_types: set[str] = set()

    for cmd, _order in enabled:
        enabled_types.add(cmd)
        reg_cmd = get_command(cmd)
        if not reg_cmd:
            continue
        cat = reg_cmd.get("category", "其他")
        handler_fields = reg_cmd.get("fields", [])
        cmd_obj = {
            **reg_cmd,
            "id": None,  # 静态导出无 DB id；前端不依赖
            "cmd": cmd,
            "label": reg_cmd.get("label", cmd),
            "category": cat,
            "icon": reg_cmd.get("icon", "fa-circle"),
            "iconColor": reg_cmd.get("iconColor", "text-gray-500"),
            "bgColor": reg_cmd.get("bgColor", "bg-gray-50"),
            "description": reg_cmd.get("description", ""),
            "isBuiltin": True,
            "fields": handler_fields,
        }
        h = get_command(cmd)
        cmd_obj["handler"] = h["runtimes"]["extension"]["handler"] if h else None
        cmd_obj["local"] = h["runtimes"]["extension"]["local"] if h else False
        cmd_obj["hasRuntime"] = h["runtimes"]["extension"]["handler"] is not None if h else False

        if cat not in commands_by_cat:
            commands_by_cat[cat] = []
            categories.append(cat)
        commands_by_cat[cat].append(cmd_obj)

    container_types = [t for t in enabled_types if all_handlers.get(t, {}).get("isContainer")]
    branch_types = [t for t in enabled_types if all_handlers.get(t, {}).get("isBranch")]
    return {
        "categories": categories,
        "commands": commands_by_cat,
        "containerTypes": container_types,
        "branchTypes": branch_types,
    }


def export_new_commands() -> dict:
    """复刻 /api/workflows/commands-new（commands/*.json 新目录）。"""
    from src.runtime.workflow.new_catalog import load_new_catalog

    return load_new_catalog()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    legacy = export_legacy_commands()
    new = export_new_commands()
    (OUT_DIR / "commands.json").write_text(
        json.dumps(legacy, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "commands-new.json").write_text(
        json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    legacy_count = sum(len(v) for v in legacy["commands"].values())
    new_count = sum(len(v) for v in new["commands"].values())
    print(f"✅ 导出完成：commands.json（{legacy_count} 条）、commands-new.json（{new_count} 条）")
    print(f"   输出目录：{OUT_DIR}")


if __name__ == "__main__":
    main()
