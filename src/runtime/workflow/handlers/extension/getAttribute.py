"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="getAttribute", label="获取属性", category="数据提取", runtime="extension",
    icon="fa-code", icon_color="text-green-500", bg_color="bg-green-50", category_order=50, command_order=20)
class GetAttributeHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True),
        Param("attribute", "属性名", "text", required=True, placeholder="如 href、class"),
        Param("varName", "保存到变量", "varName", required=True, group="output"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
        Param("loopAnchor", "锚点元素", "varName", default="", group="anchor"),
    ]
