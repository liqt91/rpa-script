"""Command: 新建标签页"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="newTab", label="新建标签页",
    category="浏览器", runtime="extension",
    icon="fa-plus-square", icon_color="text-blue-500",
    bg_color="bg-blue-50",
    description="在指定浏览器窗口中新建标签页",
    category_order=10,
    command_order=20,
)
class NewTabHandler:
    params = [
        Param("windowVar", "浏览器窗口", "string", default="browser1", group="input", placeholder="如 browser1"),
        Param("url", "打开网址", "string", placeholder="如 https://deepseek.com"),
        Param("active", "激活新标签页", "boolean", default=True, group="advanced"),
    ]