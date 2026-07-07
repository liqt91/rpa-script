"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="navigate", label="打开网页", category="页面导航", runtime="extension",
    icon="fa-globe", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=10, command_order=10,
    description="在指定窗口打开网页")
class NavigateHandler:
    params = [
        Param("windowVar", "窗口变量", "varName", default="browser1", group="input"),
        Param("url", "网址", "text", required=True, placeholder="https://..."),
        Param("waitLoad", "等待加载完成", "bool", default=True),
        Param("saveToVar", "保存网页对象到", "varName", group="output"),
    ]
