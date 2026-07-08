"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="getElementCount", label="获取元素数量", category="数据提取", runtime="extension",
    icon="fa-hashtag", icon_color="text-green-500", bg_color="bg-green-50", category_order=50, command_order=50)
class GetElementCountHandler:
    params = [
        Param("element_name", "元素", "str-element", required=True, group="主属性"),
        Param("varName", "保存到变量", "str-var", required=True, group="output"),
        Param("scope", "匹配范围", "str-dropdown",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]
