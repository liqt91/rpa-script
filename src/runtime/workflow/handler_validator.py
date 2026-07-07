"""
Handler 同步校验器 — 确保 Python 端 handler 声明与 content.js 实现一致。

使用: validate_handler_sync() → (passed, messages)
  启动时自动调用，不匹配时警告（不阻塞启动）。
"""

import re
import os
import logging

logger = logging.getLogger(__name__)


def _parse_content_js_handlers(content_js_path: str) -> set[str]:
    """从 content.js 提取所有 registerHandler('name', ...) 的 name。"""
    if not os.path.exists(content_js_path):
        logger.warning(f"content.js 不存在: {content_js_path}")
        return set()

    with open(content_js_path, 'r', encoding='utf-8') as f:
        source = f.read()

    # 匹配 registerHandler('name', ...) 或 registerHandler("name", ...)
    pattern = re.compile(r"registerHandler\s*\(\s*['\"]([^'\"]+)['\"]")
    return set(pattern.findall(source))


def validate_handler_sync(content_js_path: str | None = None) -> tuple[bool, list[str]]:
    """
    校验 Python handler registry 与 content.js 的 handler 注册是否一致。
    
    返回: (passed, messages)
      - passed: True 表示没有缺失
      - messages: 每条一条说明
    """
    from .handler_registry import get_all_handlers

    if content_js_path is None:
        # 默认路径: extension/content.js
        from pathlib import Path
        content_js_path = str(
            Path(__file__).resolve().parent.parent.parent.parent
            / "extension" / "content.js"
        )

    messages = []
    all_handlers = get_all_handlers()
    js_handlers = _parse_content_js_handlers(content_js_path)

    if not js_handlers:
        messages.append("⚠ 无法解析 content.js handler 注册，跳过校验")
        return True, messages

    # Python 端声明了 extension handler，但 content.js 中缺失
    for htype, hdef in all_handlers.items():
        if hdef["runtime"] != "extension":
            continue
        if htype not in js_handlers:
            messages.append(
                f"❌ {htype}: Python 端已注册 (runtime=extension)，"
                f"但 content.js 中未找到 registerHandler('{htype}')"
            )

    # content.js 中注册了 handler，但 Python 端未声明
    python_extension_types = {
        htype for htype, hdef in all_handlers.items()
        if hdef["runtime"] == "extension"
    }
    for jsh in js_handlers:
        if jsh not in python_extension_types and jsh not in all_handlers:
            messages.append(
                f"⚠ {jsh}: content.js 已注册，但 Python 端未声明 @register_handler"
            )

    passed = not any(m.startswith("❌") for m in messages)

    if messages:
        for m in messages:
            if m.startswith("❌"):
                logger.error(m)
            else:
                logger.warning(m)
    else:
        logger.info("✅ Handler 同步校验通过 (Python ↔ content.js)")

    return passed, messages
