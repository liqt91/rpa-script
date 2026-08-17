"""
Command registry consistency validation.
"""

import copy
import re
from pathlib import Path

from .handlers.registry import build_command_registry
from .commands_helpers import _attach_common_advanced

REQUIRED_KEYS = {"label", "category", "icon", "iconColor", "bgColor", "fields"}

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTENT_JS = REPO_ROOT / "dist" / "desktop" / "extension" / "content.js"
BACKGROUND_JS = REPO_ROOT / "dist" / "desktop" / "extension" / "background.js"


def extract_js_handler_names() -> set[str]:
    """Parse content.js + background.js for all registered handler names."""
    names: set[str] = set()
    names.update(_extract_content_handlers())
    names.update(_extract_background_handlers())
    return names


def _extract_content_handlers() -> set[str]:
    """Parse content.js for registerHandler patterns.

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


def _extract_background_handlers() -> set[str]:
    """Parse background.js for registerBackgroundHandler patterns."""
    if not BACKGROUND_JS.exists():
        return set()
    text = BACKGROUND_JS.read_text(encoding="utf-8")
    return set(re.findall(r"registerBackgroundHandler\s*\(\s*['\"]([^'\"]+)['\"]\s*,", text))


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
    """颜色合法性校验：iconColor/bgColor 格式合法且成对同色系。

    注意：不强制同类目内颜色一致 —— 颜色是 per-command 语义（如关闭=红、导航=蓝、
    文本=绿、截图=灰），历史上同类目本就允许不同色。旧版按"类目首个指令颜色"
    作为基准强制统一，会把有意设计的语义色误报为差异（40+ 条）。
    """
    errors = []
    for cmd_type, meta in registry.items():
        color = meta.get("iconColor", "")
        bg = meta.get("bgColor", "")
        if not color and not bg:
            continue
        if color and not re.match(r"^text-[a-z]+-\d{3}$", color):
            errors.append(f"{cmd_type}: iconColor '{color}' 格式非法（应为 text-<色>-<级>，如 text-blue-500）")
        if bg and not re.match(r"^bg-[a-z]+-\d{2,3}$", bg):
            errors.append(f"{cmd_type}: bgColor '{bg}' 格式非法（应为 bg-<色>-<级>，如 bg-blue-50）")
        # 都非空时必须是同一色系（text-xxx-* 配 bg-xxx-*）
        if color and bg:
            mc = re.match(r"^text-([a-z]+)-", color)
            mb = re.match(r"^bg-([a-z]+)-", bg)
            if mc and mb and mc.group(1) != mb.group(1):
                errors.append(
                    f"{cmd_type}: iconColor '{color}' 与 bgColor '{bg}' 不同色系"
                    f"（icon 色系 '{mc.group(1)}' vs bg 色系 '{mb.group(1)}'）"
                )
    return errors


def validate_common_advanced(registry: dict) -> list[str]:
    """Non-container / non-structural commands must have common advanced fields."""
    errors = []
    # 拟人化行为（humanLike）不属于通用参数：由各指令自行声明（clickElement/pressKey 等）
    required_common = {"onError", "retryCount", "timeout"}
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


def validate() -> tuple[bool, list[str]]:
    """Run all validations and return (passed, messages)."""
    js_handlers = extract_js_handler_names()
    all_errors: list[str] = []
    registry = build_command_registry()
    all_errors.extend(validate_schema(registry))
    all_errors.extend(validate_handlers(registry, js_handlers))
    all_errors.extend(validate_category_colors(registry))
    all_errors.extend(validate_common_advanced(registry))
    return len(all_errors) == 0, all_errors
