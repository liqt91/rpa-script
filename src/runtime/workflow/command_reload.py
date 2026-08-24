"""指令运行时热重载 — 修改 py handler / JSON / 分类后无需重启服务器。

调用 POST /api/commands/reload（或直接调 reload_command_runtime()）即可：
  1. 重新导入全部指令模块（backend/extension/control/desktop 及辅助模块）
     → @register_handler 重新执行，registry 反映新增/修改/删除的指令；
  2. 重建 LOCAL_HANDLERS（extension_runner 的本地指令执行映射）；
  3. 重载 emitters（节点树 → 指令序列的展开逻辑）；
  4. 清 new_catalog 分类缓存（categories.json 的 slug→name 映射）；
  5. 同步 DB（WorkflowCommand 内置指令 upsert，legacy 面板同步更新）。

正在执行的 run 不受影响（持有旧函数引用，本次运行按旧代码跑完）。
"""
import sys


def _drop_command_modules():
    """从 sys.modules 删除全部指令子模块（含辅助模块 _win32/_uia/_desktop_ref 等）。"""
    prefix = "src.runtime.commands."
    for name in list(sys.modules):
        if name.startswith(prefix):
            del sys.modules[name]


def reload_command_runtime(db=None) -> dict:
    """执行指令运行时热重载，返回统计信息。

    Args:
        db: 可选 SQLAlchemy Session；提供时同步 WorkflowCommand 内置指令到数据库。
    """
    # 1. 删除指令子模块（包 __init__ 的 glob 导入会重跑 @register_handler）
    _drop_command_modules()

    # 2. 清空注册表并重新导入全部指令模块（绝对导入 —— auto_register 的相对导入
    #    `from . import xxx` 在模块重载场景（extension_runner 已导入）下会静默失效，
    #    实测 registry 为 0；绝对导入两种前置下均可靠）。
    import importlib
    from src.runtime.workflow.handlers import registry as _reg
    _reg._HANDLER_REGISTRY.clear()
    for _sub in ("backend_commands", "extension_commands", "desktop_commands",
                 "control_commands"):
        importlib.import_module(f"src.runtime.commands.{_sub}")

    # 3. 重建 LOCAL_HANDLERS（先清空，避免残留被删指令的 handler）
    from src.runtime.workflow import extension_runner as _er
    _er.LOCAL_HANDLERS.clear()
    _er._populate_local_handlers()

    # 4. 重载 emitters
    from src.runtime.workflow.emitters import reload_handlers
    reload_handlers()

    # 5. 清 new_catalog 分类缓存与 registry 通用参数缓存（categories.json /
    #    generic_params.json 改动立即生效）
    from src.runtime.workflow import new_catalog as _nc
    _nc._CATEGORY_NAMES.clear()
    _nc._CATEGORY_ORDERS.clear()
    _reg._generic_params_reload()

    # 6. 同步 DB（legacy 面板/运行数据）
    if db is not None:
        from .command_sync import seed_commands_to_db
        seed_commands_to_db(db)

    handlers = _reg.get_all_handlers()
    return {
        "success": True,
        "handlers": len(handlers),
        "local_handlers": len(_er.LOCAL_HANDLERS),
        "db_synced": db is not None,
    }
