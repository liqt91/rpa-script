"""本地端操作指令 — backend Python handlers。每个文件通过 @register_handler 自注册。"""
import os as _os, importlib as _importlib

_dir = _os.path.dirname(__file__)
for _f in sorted(_os.listdir(_dir)):
    if _f.endswith(".py") and not _f.startswith("_"):
        _importlib.import_module(f".{_f[:-3]}", __package__)
