"""Command: 按键"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="pressKey", label="按键",
    category="页面操作", runtime="extension",
    icon="fa-keyboard", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="向页面发送键盘按键",
    category_order=60,
    command_order=30,
)
class PressKeyHandler:
    params = [
        Param("key", "按键", "string", required=True, default="Enter", placeholder="Enter / Tab / Escape / ..."),
        Param("modifiers", "修饰键", "string", default="", group="advanced", placeholder="如 Ctrl,Alt,Shift", description="逗号分隔的修饰键"),
    ]