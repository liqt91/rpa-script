"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="closeBrowser", label="关闭浏览器", category="页面导航", runtime="extension",
    icon="fa-window-close", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=10, command_order=30,
    description="关闭浏览器窗口")
class CloseBrowserHandler:
    params = [
        Param("windowVar", "窗口变量", "str-var", default="browser1", group="input"),
    ]
