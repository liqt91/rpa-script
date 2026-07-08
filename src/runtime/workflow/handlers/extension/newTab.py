"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="newTab", label="新建标签页", category="页面导航", runtime="extension",
    icon="fa-plus", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=10, command_order=20,
    description="在当前浏览器中新建标签页")
class NewTabHandler:
    params = [
        Param("windowVar", "窗口变量", "str-var", default="browser1", group="input"),
        Param("url", "网址(可选)", "str-input", required=False, placeholder="https://..."),
    ]
