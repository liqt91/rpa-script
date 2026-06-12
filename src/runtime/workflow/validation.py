"""
Command registry consistency validation.
"""

import copy
import re
from pathlib import Path

from .commands import COMMAND_REGISTRY, _attach_common_advanced

REQUIRED_KEYS = {"label", "category", "icon", "iconColor", "bgColor", "fields"}

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTENT_JS = REPO_ROOT / "extension" / "content.js"
COMMANDS_TABLE_MD = REPO_ROOT / "commands_table.md"


def extract_js_handler_names() -> set[str]:
    """Parse extension/content.js for registered handler names.

    Supports both the current registerHandler('name', fn) pattern and the
    legacy ``const handlers = {...}`` object for backwards compatibility.
    """
    if not CONTENT_JS.exists():
        return set()

    text = CONTENT_JS.read_text(encoding="utf-8")
    names: set[str] = set()

    # Current pattern: registerHandler('name', ...)
    names.update(re.findall(r"registerHandler\s*\(\s*['\"]([^'\"]+)['\"]\s*,", text))

    # Legacy pattern: const handlers = { async name(args) { ... }, ... }
    start_marker = "const handlers = {"
    start_idx = text.find(start_marker)
    if start_idx == -1:
        start_marker = "handlers = {"
        start_idx = text.find(start_marker)
    if start_idx != -1:
        brace_idx = text.find("{", start_idx)
        if brace_idx != -1:
            depth = 1
            i = brace_idx + 1
            while i < len(text) and depth > 0:
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                i += 1

            body = text[brace_idx + 1 : i - 1]
            js_keywords = {"if", "while", "for", "switch", "catch", "with"}
            for line in body.splitlines():
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                mm = re.match(r"(?:async\s+)?(\w+)\s*\([^)]*\)\s*{", line)
                if mm:
                    name = mm.group(1)
                    if name not in js_keywords:
                        names.add(name)
    return names


def validate_schema(registry: dict) -> list[str]:
    errors = []
    for cmd_type, meta in registry.items():
        missing = REQUIRED_KEYS - set(meta.keys())
        if missing:
            errors.append(f"{cmd_type}: missing required keys {sorted(missing)}")
    return errors


def validate_handlers(registry: dict, js_handlers: set) -> list[str]:
    errors = []
    for cmd_type, meta in registry.items():
        ext = meta.get("runtimes", {}).get("extension")
        if not ext:
            continue
        if ext.get("local"):
            continue
        handler = ext.get("handler")
        if not handler:
            errors.append(f"{cmd_type}: runtimes.extension.handler is empty")
            continue
        if handler not in js_handlers:
            errors.append(
                f"{cmd_type}: handler '{handler}' not found in extension/content.js "
                f"(available: {sorted(js_handlers)})"
            )
    return errors


def validate_category_colors(registry: dict) -> list[str]:
    errors = []
    category_styles: dict[str, tuple] = {}
    for cmd_type, meta in registry.items():
        cat = meta.get("category", "")
        color = meta.get("iconColor", "")
        bg = meta.get("bgColor", "")
        if cat in category_styles:
            expected_color, expected_bg = category_styles[cat]
            if color != expected_color:
                errors.append(
                    f"{cmd_type}: category '{cat}' iconColor '{color}' != "
                    f"expected '{expected_color}'"
                )
            if bg != expected_bg:
                errors.append(
                    f"{cmd_type}: category '{cat}' bgColor '{bg}' != "
                    f"expected '{expected_bg}'"
                )
        else:
            category_styles[cat] = (color, bg)
    return errors


def validate_common_advanced(registry: dict) -> list[str]:
    """Non-container / non-structural commands must have common advanced fields."""
    errors = []
    required_common = {"onError", "retryCount", "timeout", "humanLike"}
    for cmd_type, meta in registry.items():
        if meta.get("isContainer") or meta.get("isStructural"):
            continue
        enriched = copy.deepcopy(meta)
        enriched["fields"] = _attach_common_advanced(meta.get("fields", []))
        names = {f.get("name") for f in enriched["fields"]}
        missing = required_common - names
        if missing:
            errors.append(f"{cmd_type}: missing common advanced fields {sorted(missing)}")
    return errors


def validate_commands_table(registry: dict) -> list[str]:
    """commands_table.md must list every command that has an extension runtime."""
    errors = []
    if not COMMANDS_TABLE_MD.exists():
        errors.append(f"{COMMANDS_TABLE_MD.name} not found")
        return errors

    text = COMMANDS_TABLE_MD.read_text(encoding="utf-8")
    listed = set()
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("|") and not line.startswith("| 命令类型") and not line.startswith("|---"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) > 1 and parts[1]:
                listed.add(parts[1])

    for cmd_type, meta in registry.items():
        ext = meta.get("runtimes", {}).get("extension")
        if ext and cmd_type not in listed:
            errors.append(f"{cmd_type}: has extension runtime but missing from {COMMANDS_TABLE_MD.name}")

    return errors


def validate() -> tuple[bool, list[str]]:
    """Run all validations and return (passed, messages)."""
    js_handlers = extract_js_handler_names()
    all_errors: list[str] = []
    all_errors.extend(validate_schema(COMMAND_REGISTRY))
    all_errors.extend(validate_handlers(COMMAND_REGISTRY, js_handlers))
    all_errors.extend(validate_category_colors(COMMAND_REGISTRY))
    all_errors.extend(validate_common_advanced(COMMAND_REGISTRY))
    return len(all_errors) == 0, all_errors
