"""
Handler system — auto-discovery entry point.

Registration now happens in src/runtime/commands/ (auto_register imports
backend_commands / extension_commands / control_commands / desktop_commands),
which all self-register into _HANDLER_REGISTRY. Legacy handler subpackages
(backend / extension / flow) were removed.
"""
