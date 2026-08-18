"""
导出指令目录到 workflow-editor 静态 JSON（阶段 3：编辑器离线可用）。

生成一个文件（放 src/ui/workflow-editor/public/，vite 构建时拷入产物）：
  - commands-new.json : 与 /api/workflows/commands-new 同构（commands/*.json 新指令体系）

旧指令体系（DB + handler 注册表的 /commands）已移除，不再导出。

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


def export_new_commands() -> dict:
    """复刻 /api/workflows/commands-new（commands/*.json 新指令体系）。"""
    from src.runtime.workflow.new_catalog import load_new_catalog

    return load_new_catalog()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    new = export_new_commands()
    (OUT_DIR / "commands-new.json").write_text(
        json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    new_count = sum(len(v) for v in new["commands"].values())
    print(f"导出完成：commands-new.json（{new_count} 条）")
    print(f"输出目录：{OUT_DIR}")


if __name__ == "__main__":
    main()
