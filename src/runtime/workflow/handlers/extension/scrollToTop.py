"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="scrollToTop", label="滚动到顶部", category="页面操作", runtime="extension",
    icon="fa-arrow-up", icon_color="text-purple-500", bg_color="bg-purple-50", category_order=60, command_order=40)
class ScrollToTopHandler:
    params = [
        Param("scrollContainer", "滚动容器", "elementName", required=False, group="主属性"),
    ]
