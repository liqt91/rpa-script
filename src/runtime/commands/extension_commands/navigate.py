"""Command: 页面跳转"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="navigate", label="页面跳转",
    category="浏览器", runtime="extension",
    icon="fa-arrow-right", icon_color="text-blue-500",
    bg_color="bg-blue-50",
    description="在指定浏览器窗口中跳转到新网址",
    category_order=10,
    command_order=30,
)
class NavigateHandler:
    params = [
        Param("windowVar", "浏览器窗口", "string", default="browser1", group="input", placeholder="如 browser1"),
        Param("url", "目标网址", "string", placeholder="如 https://deepseek.com"),
        Param("waitLoad", "等待页面加载完成", "boolean", default=True, group="advanced"),
    ]