"""Command: 关闭浏览器"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="closeBrowser", label="关闭浏览器",
    category="浏览器", runtime="extension",
    icon="fa-window-close", icon_color="text-red-500",
    bg_color="bg-red-50",
    description="关闭指定的浏览器窗口",
    category_order=10,
    command_order=40,
    summary_tpl="{windowVar}",
)
class CloseBrowserHandler:
    params = [
        Param("windowVar", "窗口变量", "string", default="browser1", group="input"),
    ]