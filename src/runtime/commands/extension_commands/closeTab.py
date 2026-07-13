"""Command: 关闭标签页"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="closeTab", label="关闭标签页",
    category="浏览器", runtime="extension",
    icon="fa-times", icon_color="text-orange-500",
    bg_color="bg-orange-50",
    description="关闭当前或指定的标签页",
    category_order=10,
    command_order=50,
)
class CloseTabHandler:
    params = [
        Param("windowVar", "浏览器窗口", "string", default="browser1", group="input", placeholder="如 browser1"),
        Param("tabIndex", "标签页序号(可选)", "number", group="advanced", placeholder="留空关闭当前标签页"),
    ]