"""桌面端执行指令 — Python 注册桩，声明参数 schema + handler 指向。"""
import os as _os
import importlib as _importlib

_dir = _os.path.dirname(__file__)
for _f in sorted(_os.listdir(_dir)):
    if _f.endswith(".py") and not _f.startswith("_"):
        _importlib.import_module(f".{_f[:-3]}", __package__)
