"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param

@register_handler(type="checkElementExists", label="检查元素存在", category="数据提取", runtime="extension",
    icon="fa-circle-check", icon_color="text-green-500", bg_color="bg-green-50", category_order=50, command_order=60)
class CheckElementExistsHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
        Param("varName", "保存到变量", "varName", required=True, group="output"),
    ]
