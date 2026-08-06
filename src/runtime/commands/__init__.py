"""
指令命令包 — 新指令体系。

子目录自注册：
- backend_commands:   本地端操作指令 (Python handler)
- extension_commands: 扩展端执行指令 (Python 注册桩)
- control_commands:   本地端控制指令 (容器/流程控制)
- tools:              代码生成工具
"""


_registered = False


def auto_register():
    """导入所有子包，触发 @register_handler 装饰器自注册。幂等：重复调用无副作用。

    注意：desktop_commands 必须在 control_commands 之前导入 —— control 指令
    （如 forEachElement）会导入 extension_runner，后者在构建 LOCAL_HANDLERS 时
    读取注册表，需要桌面/扩展/后端指令已全部注册。
    """
    global _registered
    if _registered:
        return
    from . import backend_commands  # noqa: F401
    from . import extension_commands  # noqa: F401
    from . import desktop_commands  # noqa: F401
    from . import control_commands  # noqa: F401
    _registered = True
