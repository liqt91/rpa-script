"""Command: 切换标签页"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="switchTab", label="切换标签页",
    category="浏览器", runtime="extension",
    icon="fa-exchange-alt", icon_color="text-blue-500",
    bg_color="bg-blue-50",
    description="切换到指定浏览器窗口的活跃标签页",
    category_order=10,
    command_order=40,
)
class SwitchTabHandler:
    params = [
        Param("windowVar", "浏览器窗口", "string", default="browser1", group="input", placeholder="如 browser1"),
    ]