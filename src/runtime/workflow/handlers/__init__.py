"""
Handler system — auto-discovery entry point.

Architecture:
  handlers/
    backend/      — Python handler classes (local execution, @register_handler)
    extension/    — manifest declaring extension-side handlers (content.js)
    flow/         — 流程控制指令声明（容器 / 分支 / 结束标记 / 跳转）
    handlers_new/ — JSON 定义生成的新指令（开发期隔离，逐步迁移）

How it works:
  1. Importing this package auto-scans all three directories for .py files.
  2. Each file's @register_handler decorator self-registers into _HANDLER_REGISTRY.
  3. build_command_registry() collects all registered handlers into COMMAND_REGISTRY format.
  4. The DB seed + API serve this unified registry to the workflow editor.

Mapping conventions (no hardcoded config):
  - Extension handler:  type name in _manifest.py == registerHandler(name, ...) in content.js
  - Backend handler:   type name in backend/*.py == handler class name convention
  - Emitter:           type name in flow/*.py == @register_handler(type=...)
"""
import importlib
import pkgutil
import os


def _auto_import_subpackage(subpackage_name: str):
    """Import all modules in a subpackage to trigger @register_handler decorators."""
    package_path = os.path.join(os.path.dirname(__file__), subpackage_name)
    if not os.path.isdir(package_path):
        return

    package_full = f"{__package__}.{subpackage_name}"
    for _, module_name, _ in pkgutil.iter_modules([package_path]):
        if module_name.startswith('_') and module_name != '_manifest':
            continue  # skip private modules except _manifest
        importlib.import_module(f".{subpackage_name}.{module_name}", package=__package__)


# Auto-discover and register all handlers
_auto_import_subpackage("backend")
_auto_import_subpackage("extension")
_auto_import_subpackage("flow")
_auto_import_subpackage("handlers_new")
