"""向后兼容 — 重导出到 handler_registry.py"""
from .handlers.registry import (  # noqa: F401
    Param, GENERIC_PARAMS, register_handler, get_handler, get_all_handlers, build_command_registry
)
