"""
Extension Contract Checker — validates consistency between
commands.py registry, extension_emitter, extension_runner, and content.js.

Run: python -m src.runtime.workflow.extension_contract
"""

import re
import sys
from pathlib import Path

from src.runtime.workflow.handlers.registry import build_command_registry

# Paths relative to repo root (run from repo root)
REPO_ROOT = Path.cwd()
EMITTER_PY = REPO_ROOT / "src" / "runtime" / "workflow" / "extension_emitter.py"
RUNNER_PY = REPO_ROOT / "src" / "runtime" / "workflow" / "extension_runner.py"
CONTENT_JS = REPO_ROOT / "extension" / "content.js"


def _load_registry() -> dict:
    """Return COMMAND_REGISTRY from commands.py."""
    return build_command_registry()


def _extract_content_js_handlers() -> set[str]:
    """Find all handler names registered via registerHandler(...) in content.js."""
    text = CONTENT_JS.read_text(encoding="utf-8")
    return set(re.findall(r"registerHandler\(['\"](\w+)['\"]", text))


def _extract_runner_local_handlers() -> set[str]:
    """Find cmd_types handled locally in ExtensionRunner.

    Includes both legacy `if cmd_type == "..."` branches and the
    `@register_local("...")` decorator registry.
    """
    text = RUNNER_PY.read_text(encoding="utf-8")
    legacy = set(re.findall(r'if cmd_type == "(\w+)":', text))
    registered = set(re.findall(r'@register_local\("(\w+)"\)', text))
    return legacy | registered


def check() -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for the extension contract."""
    errors: list[str] = []
    warnings: list[str] = []
    registry = _load_registry()
    js_handlers = _extract_content_js_handlers()
    runner_locals = _extract_runner_local_handlers()

    for cmd_type, meta in registry.items():
        ext = meta.get("runtimes", {}).get("extension")
        if not ext:
            continue
        handler = ext.get("handler")
        is_local = ext.get("local", False)

        if is_local:
            if handler not in runner_locals:
                errors.append(
                    f"LOCAL_HANDLER_MISSING: {cmd_type} -> handler={handler!r} "
                    f"not handled in ExtensionRunner._handle_local"
                )
        else:
            if handler not in js_handlers:
                errors.append(
                    f"JS_HANDLER_MISSING: {cmd_type} -> handler={handler!r} "
                    f"not found in content.js handlers={sorted(js_handlers)}"
                )

    # Reverse check: are there handlers in content.js that have no command pointing to them?
    referenced_handlers = {
        ext["handler"]
        for meta in registry.values()
        if (ext := meta.get("runtimes", {}).get("extension"))
        and not ext.get("local", False)
    }
    orphan_js = js_handlers - referenced_handlers
    if orphan_js:
        warnings.append(f"ORPHAN_JS_HANDLERS: {sorted(orphan_js)} not referenced by any command")

    return errors, warnings


if __name__ == "__main__":
    errs, warns = check()
    if warns:
        print("Extension contract warnings:")
        for w in warns:
            print(f"  - {w}")
    if errs:
        print("Extension contract check FAILED:")
        for e in errs:
            print(f"  - {e}")
        sys.exit(1)
    print("Extension contract check PASSED")
    sys.exit(0)
