"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="scrollToBottom", label="滚动到底部", category="页面操作", runtime="extension",
    icon="fa-arrow-down", icon_color="text-purple-500", bg_color="bg-purple-50", category_order=60, command_order=20,
    description="滚动页面到底部")
class ScrollToBottomHandler:
    params = [
        Param("scrollContainer", "滚动容器", "str-element", required=False, group="主属性",
              description="留空则滚动整个页面"),
    ]
