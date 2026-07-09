"""
指令命令包 — 新指令体系。

子目录自注册：
- backend_commands:   本地端操作指令 (Python handler)
- extension_commands: 扩展端执行指令 (Python 注册桩)
- control_commands:   本地端控制指令 (容器/流程控制)
- tools:              代码生成工具
"""


def auto_register():
    """导入所有子包，触发 @register_handler 装饰器自注册。"""
    from . import backend_commands
    from . import extension_commands
    from . import control_commands
