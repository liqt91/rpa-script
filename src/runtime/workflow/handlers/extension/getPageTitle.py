"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="getPageTitle", label="获取页面标题", category="页面导航", runtime="extension",
    icon="fa-heading", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=10, command_order=50)
class GetPageTitleHandler:
    params = [
        Param("saveToVar", "保存到变量", "varName", required=True, group="output"),
    ]
