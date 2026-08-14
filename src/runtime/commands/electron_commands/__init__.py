"""Electron 应用指令 — 通过 CDP 驱动（Playwright Python 无 electron 支持，走裸 CDP）。"""
import os as _os
import importlib as _importlib

_dir = _os.path.dirname(__file__)
for _f in sorted(_os.listdir(_dir)):
    if _f.endswith(".py") and not _f.startswith("_"):
        _importlib.import_module(f".{_f[:-3]}", __package__)
