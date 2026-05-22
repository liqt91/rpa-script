"""Workflow command emitters — auto-discovered by category."""

import importlib
import pkgutil

__path__ = __path__  # type: ignore

for _, module_name, _ in pkgutil.iter_modules(__path__):
    if module_name.startswith("_"):
        continue
    importlib.import_module(f"{__name__}.{module_name}")


def reload_handlers():
    """Runtime reload of all emit handlers without server restart."""
    import sys
    from ._registry import _EMIT_HANDLERS

    _EMIT_HANDLERS.clear()

    for name in list(sys.modules.keys()):
        if name.startswith(__name__ + ".") and not name.endswith("._registry"):
            del sys.modules[name]

    for _, module_name, _ in pkgutil.iter_modules(__path__):
        if module_name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{module_name}")
