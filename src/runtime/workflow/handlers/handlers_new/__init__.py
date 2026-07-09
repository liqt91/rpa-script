"""New-system handlers generated from commands/*.json definitions.

Importing this package auto-discovers all sibling .py files and triggers their
@register_handler decorators, making new commands available to the runtime
without mixing them into the legacy backend/extension/flow directories.
"""
import importlib
import pkgutil
import os

_package_path = os.path.dirname(__file__)
_package_name = __package__

for _, module_name, _ in pkgutil.iter_modules([_package_path]):
    if module_name.startswith("_"):
        continue
    importlib.import_module(f".{module_name}", package=_package_name)
