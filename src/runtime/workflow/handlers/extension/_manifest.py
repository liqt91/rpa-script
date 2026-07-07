"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param


@register_handler(type="clickElement", label="点击元素", category="元素操作", runtime="extension",
    icon="fa-hand-pointer", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=10)
class ClickElementHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
        Param("loopAnchor", "锚点元素", "varName", default="", group="anchor"),
        Param("visibilityMode", "元素可见性", "select",
              options=[{"label": "仅可见", "value": "visible"}, {"label": "所有", "value": "any"}],
              default="visible", group="advanced"),
    ]


@register_handler(type="inputText", label="输入文本", category="元素操作", runtime="extension",
    icon="fa-keyboard", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=20)
class InputTextHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True),
        Param("text", "文本内容", "text", required=True),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
        Param("loopAnchor", "锚点元素", "varName", default="", group="anchor"),
        Param("clearFirst", "先清空", "bool", default=True, group="advanced"),
    ]


@register_handler(type="getText", label="获取文本", category="数据提取", runtime="extension",
    icon="fa-font", icon_color="text-green-500", bg_color="bg-green-50", category_order=50, command_order=10)
class GetTextHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True),
        Param("varName", "保存到变量", "varName", required=True, group="output"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
        Param("loopAnchor", "锚点元素", "varName", default="", group="anchor"),
        Param("visibilityMode", "元素可见性", "select",
              options=[{"label": "仅可见", "value": "visible"}, {"label": "所有", "value": "any"}],
              default="visible", group="advanced"),
    ]


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


@register_handler(type="scrollIntoView", label="滚动到元素", category="页面操作", runtime="extension",
    icon="fa-arrow-down", icon_color="text-purple-500", bg_color="bg-purple-50", category_order=60, command_order=10)
class ScrollIntoViewHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
        Param("loopAnchor", "锚点元素", "varName", default="", group="anchor"),
    ]


@register_handler(type="navigate", label="打开网页", category="页面导航", runtime="extension",
    icon="fa-globe", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=10, command_order=10,
    description="导航到指定 URL")
class NavigateHandler:
    params = [
        Param("url", "网址", "text", required=True, placeholder="https://..."),
        Param("waitLoad", "等待加载完成", "bool", default=True),
        Param("saveToVar", "保存网页对象到", "varName", group="output"),
    ]
