"""
内置 handler 定义 — 每个 handler 声明自己的参数。
导入本模块即自动注册所有 handler 到 handler_registry。
"""

from .handler_registry import register_handler, Param

# ═══════════════════════════════════════════════════════════
# 浏览器操作
# ═══════════════════════════════════════════════════════════

@register_handler(type="openBrowser", label="打开浏览器", category="浏览器", runtime="backend",
    icon="fa-chrome", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=1, command_order=10,
    description="启动浏览器并加载RPA扩展，返回窗口变量供后续指令使用")
class OpenBrowserHandler:
    params = [
        Param("browserType", "浏览器", "select",
              options=[{"label": "Chrome", "value": "chrome"}, {"label": "Edge", "value": "edge"}],
              default="chrome"),
        Param("windowState", "窗口状态", "select",
              options=[{"label": "普通", "value": "normal"}, {"label": "最大化", "value": "maximized"}, {"label": "最小化", "value": "minimized"}],
              default="normal", group="advanced"),
        Param("windowVar", "窗口变量", "varName", default="browser1", placeholder="如 browser1", group="input"),
    ]


# ═══════════════════════════════════════════════════════════
# 页面导航
# ═══════════════════════════════════════════════════════════

@register_handler(type="navigate", label="打开网页", category="页面导航", runtime="extension",
    icon="fa-globe", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=10, command_order=10,
    description="导航到指定 URL")
class NavigateHandler:
    params = [
        Param("url", "网址", "text", required=True, placeholder="https://..."),
        Param("waitLoad", "等待加载完成", "bool", default=True),
        Param("saveToVar", "保存网页对象到", "varName", group="output"),
    ]

@register_handler(type="newTab", label="新建标签页", category="页面导航", runtime="extension",
    icon="fa-plus", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=10, command_order=20,
    description="在当前浏览器中新建标签页")
class NewTabHandler:
    params = [
        Param("windowVar", "窗口变量", "varName", default="browser1", group="input"),
        Param("url", "网址(可选)", "text", required=False, placeholder="https://..."),
    ]

@register_handler(type="closeBrowser", label="关闭浏览器", category="页面导航", runtime="extension",
    icon="fa-window-close", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=10, command_order=30,
    description="关闭浏览器窗口")
class CloseBrowserHandler:
    params = [
        Param("windowVar", "窗口变量", "varName", default="browser1", group="input"),
    ]

@register_handler(type="getCurrentUrl", label="获取当前URL", category="页面导航", runtime="extension",
    icon="fa-link", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=10, command_order=40,
    description="获取当前页面 URL，保存到变量")
class GetCurrentUrlHandler:
    params = [
        Param("saveToVar", "保存到变量", "varName", required=True, group="output"),
    ]


# ═══════════════════════════════════════════════════════════
# 等待
# ═══════════════════════════════════════════════════════════

@register_handler(type="sleep", label="等待", category="等待", runtime="backend",
    icon="fa-clock", icon_color="text-yellow-500", bg_color="bg-yellow-50", category_order=20, command_order=10,
    description="等待指定秒数")
class SleepHandler:
    params = [
        Param("seconds", "等待秒数", "number", default=3),
    ]

@register_handler(type="randomWait", label="随机等待", category="等待", runtime="backend",
    icon="fa-random", icon_color="text-yellow-500", bg_color="bg-yellow-50", category_order=20, command_order=20,
    description="随机等待 min~max 秒")
class RandomWaitHandler:
    params = [
        Param("min", "最小秒数", "number", default=1),
        Param("max", "最大秒数", "number", default=5),
    ]


# ═══════════════════════════════════════════════════════════
# 变量操作
# ═══════════════════════════════════════════════════════════

@register_handler(type="setVar", label="设置变量", category="变量操作", runtime="backend",
    icon="fa-equals", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=10,
    description="设置变量值，支持字符串、数字、布尔、列表、字典")
class SetVarHandler:
    params = [
        Param("name", "变量名", "varName", required=True),
        Param("value", "值", "text"),
        Param("valueType", "值类型", "select",
              options=[{"label":"文本","value":"string"},{"label":"数字","value":"number"},
                       {"label":"布尔","value":"bool"},{"label":"列表","value":"list"},
                       {"label":"字典","value":"dict"},{"label":"表达式","value":"expression"}],
              default="string"),
    ]

@register_handler(type="appendToList", label="追加到列表", category="变量操作", runtime="backend",
    icon="fa-list-ol", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=20,
    description="向列表变量追加元素")
class AppendToListHandler:
    params = [
        Param("listName", "列表变量名", "varName", required=True),
        Param("value", "追加的值", "text"),
    ]

@register_handler(type="increment", label="递增/递减", category="变量操作", runtime="backend",
    icon="fa-sort-numeric-up", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=30,
    description="对数值变量进行加减")
class IncrementHandler:
    params = [
        Param("varName", "变量名", "varName", required=True),
        Param("step", "步长", "number", default=1),
    ]


# ═══════════════════════════════════════════════════════════
# 元素操作 (extension side — 通用 elementAction)
# ═══════════════════════════════════════════════════════════

@register_handler(type="clickElement", label="点击元素", category="元素操作", runtime="extension",
    icon="fa-hand-pointer", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=10,
    description="点击指定元素")
class ClickElementHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
        Param("loopAnchor", "锚点元素", "varName", default="", group="anchor"),
        Param("visibilityMode", "元素可见性", "select",
              options=[{"label": "仅可见", "value": "visible"}, {"label": "所有", "value": "any"}],
              default="visible", group="advanced"),
    ]

@register_handler(type="inputText", label="输入文本", category="元素操作", runtime="extension",
    icon="fa-keyboard", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=20,
    description="在输入框中输入文本")
class InputTextHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("text", "文本内容", "text", required=True),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
        Param("loopAnchor", "锚点元素", "varName", default="", group="anchor"),
        Param("clearFirst", "先清空", "bool", default=True, group="advanced"),
    ]

@register_handler(type="getText", label="获取文本", category="数据提取", runtime="extension",
    icon="fa-font", icon_color="text-green-500", bg_color="bg-green-50", category_order=50, command_order=10,
    description="获取元素的文本内容，保存到变量")
class GetTextHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
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
    icon="fa-code", icon_color="text-green-500", bg_color="bg-green-50", category_order=50, command_order=20,
    description="获取元素的 HTML 属性值")
class GetAttributeHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("attribute", "属性名", "text", required=True, placeholder="如 href、class"),
        Param("varName", "保存到变量", "varName", required=True, group="output"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
        Param("loopAnchor", "锚点元素", "varName", default="", group="anchor"),
    ]

@register_handler(type="scrollIntoView", label="滚动到元素", category="页面操作", runtime="extension",
    icon="fa-arrow-down", icon_color="text-purple-500", bg_color="bg-purple-50", category_order=60, command_order=10,
    description="滚动页面使元素可见")
class ScrollIntoViewHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
        Param("loopAnchor", "锚点元素", "varName", default="", group="anchor"),
    ]


# ═══════════════════════════════════════════════════════════
# 自定义代码
# ═══════════════════════════════════════════════════════════

@register_handler(type="custom", label="自定义代码", category="高级", runtime="backend",
    icon="fa-code", icon_color="text-gray-700", bg_color="bg-gray-100", category_order=90, command_order=10,
    description="执行自定义 Python 代码，可访问 _table, runner.vars 等上下文")
class CustomHandler:
    params = [
        Param("code", "Python 代码", "code", required=True),
        Param("resultVar", "保存结果到", "varName", group="output"),
    ]


# ═══════════════════════════════════════════════════════════
# 日志
# ═══════════════════════════════════════════════════════════

@register_handler(type="log", label="打印日志", category="高级", runtime="backend",
    icon="fa-terminal", icon_color="text-gray-700", bg_color="bg-gray-100", category_order=90, command_order=20,
    description="在运行日志中输出信息")
class LogHandler:
    params = [
        Param("message", "日志内容", "text", required=True, placeholder="支持 ${var} 变量插值"),
        Param("level", "日志级别", "select",
              options=[{"label": "信息", "value": "info"}, {"label": "警告", "value": "warn"}, {"label": "错误", "value": "error"}],
              default="info", group="advanced"),
    ]


# ═══════════════════════════════════════════════════════════
# 更多元素操作（1:1 handler）
# ═══════════════════════════════════════════════════════════

@register_handler(type="getHtml", label="获取HTML", category="数据提取", runtime="extension",
    icon="fa-code", icon_color="text-green-500", bg_color="bg-green-50", category_order=50, command_order=30)
class GetHtmlHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("varName", "保存到变量", "varName", required=True, group="output"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
        Param("loopAnchor", "锚点元素", "varName", default="", group="anchor"),
    ]

@register_handler(type="getValue", label="获取元素值", category="数据提取", runtime="extension",
    icon="fa-font", icon_color="text-green-500", bg_color="bg-green-50", category_order=50, command_order=40)
class GetValueHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("varName", "保存到变量", "varName", required=True, group="output"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]

@register_handler(type="doubleClick", label="双击元素", category="元素操作", runtime="extension",
    icon="fa-hand-pointer", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=11)
class DoubleClickHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]

@register_handler(type="rightClick", label="右键元素", category="元素操作", runtime="extension",
    icon="fa-mouse-pointer", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=12)
class RightClickHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]

@register_handler(type="hover", label="鼠标悬停", category="元素操作", runtime="extension",
    icon="fa-hand-pointer", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=30)
class HoverHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]

@register_handler(type="clearInput", label="清空输入框", category="元素操作", runtime="extension",
    icon="fa-eraser", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=40)
class ClearInputHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]

@register_handler(type="scrollToBottom", label="滚动到底部", category="页面操作", runtime="extension",
    icon="fa-arrow-down", icon_color="text-purple-500", bg_color="bg-purple-50", category_order=60, command_order=20,
    description="滚动页面到底部")
class ScrollToBottomHandler:
    params = [
        Param("scrollContainer", "滚动容器", "elementName", required=False, group="主属性",
              description="留空则滚动整个页面"),
    ]

@register_handler(type="pressKey", label="按键", category="页面操作", runtime="extension",
    icon="fa-keyboard", icon_color="text-purple-500", bg_color="bg-purple-50", category_order=60, command_order=30,
    description="发送键盘按键")
class PressKeyHandler:
    params = [
        Param("key", "按键", "text", required=True, default="Enter", placeholder="Enter / Tab / Escape / ..."),
        Param("modifiers", "修饰键", "text", default="", placeholder="如 Ctrl,Alt,Shift", group="advanced",
              description="逗号分隔的修饰键"),
    ]


# ═══════════════════════════════════════════════════════════
# 数据表格
# ═══════════════════════════════════════════════════════════

@register_handler(type="writeTableRow", label="写入数据行", category="数据表格", runtime="backend",
    icon="fa-table", icon_color="text-orange-500", bg_color="bg-orange-50", category_order=70, command_order=10,
    description="向数据表格追加一行数据")
class WriteTableRowHandler:
    params = [
        Param("rowData", "行数据", "text", required=True, placeholder="[${colA}, ${colB}]"),
        Param("writeMode", "写入模式", "select",
              options=[{"label": "追加", "value": "append"}, {"label": "覆盖指定行", "value": "overwrite"}],
              default="append"),
        Param("rowIndex", "行号", "number", default=0),
    ]

@register_handler(type="httpRequest", label="HTTP请求", category="高级", runtime="backend",
    icon="fa-network-wired", icon_color="text-gray-700", bg_color="bg-gray-100", category_order=90, command_order=30,
    description="发送 HTTP 请求")
class HttpRequestHandler:
    params = [
        Param("url", "请求地址", "text", required=True, placeholder="https://..."),
        Param("method", "请求方法", "select",
              options=["GET","POST","PUT","DELETE","PATCH"], default="GET"),
        Param("headers", "请求头(JSON)", "code", default="{}", group="advanced"),
        Param("body", "请求体", "code", group="advanced"),
        Param("saveToVar", "保存结果到", "varName", group="output"),
    ]


# ═══════════════════════════════════════════════════════════
# 字典操作
# ═══════════════════════════════════════════════════════════

@register_handler(type="setDictValue", label="设置字典值", category="变量操作", runtime="backend",
    icon="fa-book", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=40)
class SetDictValueHandler:
    params = [
        Param("dictName", "字典变量名", "varName", required=True),
        Param("key", "键名", "text", required=True),
        Param("value", "值", "text"),
    ]

@register_handler(type="getDictValue", label="读取字典值", category="变量操作", runtime="backend",
    icon="fa-book-open", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=50)
class GetDictValueHandler:
    params = [
        Param("dictName", "字典变量名", "varName", required=True),
        Param("key", "键名", "text", required=True),
        Param("saveToVar", "保存到变量", "varName", group="output"),
    ]

@register_handler(type="removeDictKey", label="删除字典键", category="变量操作", runtime="backend",
    icon="fa-trash-alt", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=60)
class RemoveDictKeyHandler:
    params = [
        Param("dictName", "字典变量名", "varName", required=True),
        Param("key", "键名", "text", required=True),
    ]

@register_handler(type="stringConcat", label="字符串拼接", category="变量操作", runtime="backend",
    icon="fa-plus", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=70)
class StringConcatHandler:
    params = [
        Param("parts", "拼接内容", "text", required=True, placeholder='用 + 连接, 如 "hello" + ${name}'),
        Param("saveToVar", "保存到变量", "varName", group="output"),
    ]


# ═══════════════════════════════════════════════════════════
# 等待类
# ═══════════════════════════════════════════════════════════

@register_handler(type="randomSleep", label="随机等待", category="等待", runtime="backend",
    icon="fa-random", icon_color="text-yellow-500", bg_color="bg-yellow-50", category_order=20, command_order=30)
class RandomSleepHandler:
    params = [
        Param("minSeconds", "最小秒数", "number", default=1),
        Param("maxSeconds", "最大秒数", "number", default=5),
    ]

@register_handler(type="waitForElement", label="等待元素出现", category="等待", runtime="extension",
    icon="fa-eye", icon_color="text-yellow-500", bg_color="bg-yellow-50", category_order=20, command_order=40)
class WaitForElementHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True),
        Param("visibilityMode", "元素可见性", "select",
              options=[{"label": "仅可见", "value": "visible"}, {"label": "所有", "value": "any"}], default="visible"),
    ]

@register_handler(type="waitForElementHide", label="等待元素消失", category="等待", runtime="extension",
    icon="fa-eye-slash", icon_color="text-yellow-500", bg_color="bg-yellow-50", category_order=20, command_order=50)
class WaitForElementHideHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True),
    ]

@register_handler(type="waitForLoad", label="等待页面加载", category="等待", runtime="extension",
    icon="fa-spinner", icon_color="text-yellow-500", bg_color="bg-yellow-50", category_order=20, command_order=60)
class WaitForLoadHandler:
    params = []

@register_handler(type="waitForUrl", label="等待URL变化", category="等待", runtime="extension",
    icon="fa-link", icon_color="text-yellow-500", bg_color="bg-yellow-50", category_order=20, command_order=70)
class WaitForUrlHandler:
    params = [
        Param("expectedUrl", "目标URL包含", "text", placeholder="留空则等待任何变化"),
    ]

@register_handler(type="waitForText", label="等待文本出现", category="等待", runtime="extension",
    icon="fa-font", icon_color="text-yellow-500", bg_color="bg-yellow-50", category_order=20, command_order=80)
class WaitForTextHandler:
    params = [
        Param("text", "文本内容", "text", required=True),
    ]


# ═══════════════════════════════════════════════════════════
# 页面操作
# ═══════════════════════════════════════════════════════════

@register_handler(type="scrollToTop", label="滚动到顶部", category="页面操作", runtime="extension",
    icon="fa-arrow-up", icon_color="text-purple-500", bg_color="bg-purple-50", category_order=60, command_order=40)
class ScrollToTopHandler:
    params = [
        Param("scrollContainer", "滚动容器", "elementName", required=False, group="主属性"),
    ]

@register_handler(type="scrollOneScreen", label="滚动一屏", category="页面操作", runtime="extension",
    icon="fa-arrows-alt-v", icon_color="text-purple-500", bg_color="bg-purple-50", category_order=60, command_order=50)
class ScrollOneScreenHandler:
    params = [
        Param("scrollContainer", "滚动容器", "elementName", required=False, group="主属性"),
        Param("direction", "方向", "select",
              options=[{"label": "向下", "value": "down"}, {"label": "向上", "value": "up"}], default="down"),
    ]

@register_handler(type="scrollBy", label="滚动指定距离", category="页面操作", runtime="extension",
    icon="fa-arrows-alt-v", icon_color="text-purple-500", bg_color="bg-purple-50", category_order=60, command_order=60)
class ScrollByHandler:
    params = [
        Param("scrollContainer", "滚动容器", "elementName", required=False, group="主属性"),
        Param("x", "X像素", "number", default=0),
        Param("y", "Y像素", "number", default=300),
    ]

@register_handler(type="getPageTitle", label="获取页面标题", category="页面导航", runtime="extension",
    icon="fa-heading", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=10, command_order=50)
class GetPageTitleHandler:
    params = [
        Param("saveToVar", "保存到变量", "varName", required=True, group="output"),
    ]

@register_handler(type="getElementCount", label="获取元素数量", category="数据提取", runtime="extension",
    icon="fa-hashtag", icon_color="text-green-500", bg_color="bg-green-50", category_order=50, command_order=50)
class GetElementCountHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("varName", "保存到变量", "varName", required=True, group="output"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]

@register_handler(type="clickIfExists", label="点击元素(如果存在)", category="元素操作", runtime="extension",
    icon="fa-hand-pointer", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=13)
class ClickIfExistsHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]

@register_handler(type="unhover", label="取消悬停", category="元素操作", runtime="extension",
    icon="fa-hand-pointer", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=31)
class UnhoverHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
    ]

@register_handler(type="selectOption", label="选择下拉选项", category="元素操作", runtime="extension",
    icon="fa-list", icon_color="text-blue-500", bg_color="bg-blue-50", category_order=40, command_order=50)
class SelectOptionHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("value", "选项值", "text", required=True, placeholder="按 value 或文本匹配"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]

@register_handler(type="takeScreenshot", label="截图", category="高级", runtime="extension",
    icon="fa-camera", icon_color="text-gray-700", bg_color="bg-gray-100", category_order=90, command_order=40)
class TakeScreenshotHandler:
    params = [
        Param("element_name", "目标元素(可选)", "elementName", required=False, group="主属性"),
        Param("saveToVar", "保存到变量(base64)", "varName", group="output"),
    ]

@register_handler(type="keyCombo", label="组合键", category="页面操作", runtime="extension",
    icon="fa-keyboard", icon_color="text-purple-500", bg_color="bg-purple-50", category_order=60, command_order=35)
class KeyComboHandler:
    params = [
        Param("keys", "按键序列", "text", required=True, placeholder="Ctrl+C / Alt+Tab"),
    ]


# ═══════════════════════════════════════════════════════════
# 数据表格
# ═══════════════════════════════════════════════════════════

@register_handler(type="readTableCell", label="读取表格单元格", category="数据表格", runtime="backend",
    icon="fa-table", icon_color="text-orange-500", bg_color="bg-orange-50", category_order=70, command_order=20)
class ReadTableCellHandler:
    params = [
        Param("rowIndex", "行号", "number", default=0),
        Param("colIndex", "列号/列名", "text", default="0"),
        Param("saveToVar", "保存到变量", "varName", group="output"),
    ]

@register_handler(type="writeTableCell", label="写入表格单元格", category="数据表格", runtime="backend",
    icon="fa-table", icon_color="text-orange-500", bg_color="bg-orange-50", category_order=70, command_order=30)
class WriteTableCellHandler:
    params = [
        Param("rowIndex", "行号", "number", required=True),
        Param("colIndex", "列号/列名", "text", required=True),
        Param("value", "值", "text"),
    ]

@register_handler(type="getTableRowCount", label="获取表格行数", category="数据表格", runtime="backend",
    icon="fa-table", icon_color="text-orange-500", bg_color="bg-orange-50", category_order=70, command_order=40)
class GetTableRowCountHandler:
    params = [
        Param("saveToVar", "保存到变量", "varName", group="output"),
    ]

@register_handler(type="executeJs", label="执行JavaScript", category="高级", runtime="extension",
    icon="fa-code", icon_color="text-gray-700", bg_color="bg-gray-100", category_order=90, command_order=50)
class ExecuteJsHandler:
    params = [
        Param("code", "JS代码", "code", required=True),
        Param("saveToVar", "保存返回值到", "varName", group="output"),
    ]


# ═══════════════════════════════════════════════════════════
# 容器/结构指令 — runtime="emitter"
# ═══════════════════════════════════════════════════════════

@register_handler(type="forList", label="循环列表", category="循环", runtime="emitter",
    is_container=True, closes_with="endFor",
    icon="fa-list-ol", icon_color="text-indigo-500", bg_color="bg-indigo-50", category_order=80, command_order=10,
    description="遍历列表变量中的每个元素")
class ForListHandler:
    params = [
        Param("listVar", "列表变量", "varName", required=True, group="主属性"),
        Param("itemVar", "当前项变量", "text", required=True, default="item", group="output"),
        Param("indexVar", "索引变量", "text", default="index", group="output"),
    ]

@register_handler(type="forRange", label="循环次数", category="循环", runtime="emitter",
    is_container=True, closes_with="endFor",
    icon="fa-redo", icon_color="text-indigo-500", bg_color="bg-indigo-50", category_order=80, command_order=20,
    description="按指定次数循环执行")
class ForRangeHandler:
    params = [
        Param("start", "起始值", "number", default=0),
        Param("end", "结束值", "number", default=10),
        Param("step", "步长", "number", default=1),
        Param("varName", "循环变量", "text", default="i", group="output"),
    ]

@register_handler(type="forEachElement", label="循环元素列表", category="循环", runtime="emitter",
    is_container=True, closes_with="endFor",
    icon="fa-crosshairs", icon_color="text-indigo-500", bg_color="bg-indigo-50", category_order=80, command_order=30,
    description="遍历匹配到的所有元素")
class ForEachElementHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("itemVar", "当前项变量", "text", required=True, default="item", group="output"),
        Param("indexVar", "索引变量", "text", default="index", group="output"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "全局", "value": "global"}], default="global", group="advanced"),
        Param("visibilityMode", "元素可见性", "select",
              options=[{"label": "仅可见", "value": "visible"}, {"label": "所有", "value": "any"}],
              default="visible", group="advanced"),
    ]

@register_handler(type="forEachTableRow", label="循环表格行", category="循环", runtime="emitter",
    is_container=True, closes_with="endFor",
    icon="fa-table", icon_color="text-indigo-500", bg_color="bg-indigo-50", category_order=80, command_order=40,
    description="遍历数据表格的每一行")
class ForEachTableRowHandler:
    params = [
        Param("itemVar", "当前行变量", "text", required=True, default="row", group="output"),
        Param("indexVar", "索引变量", "text", default="index", group="output"),
    ]

@register_handler(type="whileCondition", label="条件循环", category="循环", runtime="emitter",
    is_container=True, closes_with="endFor",
    icon="fa-infinity", icon_color="text-indigo-500", bg_color="bg-indigo-50", category_order=80, command_order=50,
    description="当条件满足时持续循环")
class WhileConditionHandler:
    params = [
        Param("condition", "条件表达式", "code", required=True, placeholder="如 ${i} < 10"),
    ]


# ─── 条件判断 ────────────────────────────────────────────────

@register_handler(type="ifElementVisible", label="如果元素可见", category="条件判断", runtime="emitter",
    is_container=True, closes_with="endIf",
    icon="fa-eye", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=10,
    description="根据元素是否可见决定执行分支")
class IfElementVisibleHandler:
    params = [
        Param("element_name", "元素", "elementName", required=True, group="主属性"),
        Param("operator", "判断条件", "select",
              options=[{"label": "可见", "value": "visible"}, {"label": "不可见", "value": "notVisible"}],
              default="visible"),
        Param("scope", "匹配范围", "select",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]

@register_handler(type="ifTextContains", label="如果文本包含", category="条件判断", runtime="emitter",
    is_container=True, closes_with="endIf",
    icon="fa-font", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=20)
class IfTextContainsHandler:
    params = [
        Param("text", "源文本", "text", required=True, placeholder="支持 ${var} 变量"),
        Param("substring", "包含文本", "text", required=True),
    ]

@register_handler(type="ifTextEquals", label="如果文本相等", category="条件判断", runtime="emitter",
    is_container=True, closes_with="endIf",
    icon="fa-equals", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=30)
class IfTextEqualsHandler:
    params = [
        Param("text", "文本A", "text", required=True),
        Param("compareTo", "文本B", "text", required=True),
    ]

@register_handler(type="ifVarEquals", label="如果变量相等", category="条件判断", runtime="emitter",
    is_container=True, closes_with="endIf",
    icon="fa-equals", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=40)
class IfVarEqualsHandler:
    params = [
        Param("varName", "变量名", "varName", required=True),
        Param("compareTo", "比较值", "text", required=True),
    ]

@register_handler(type="ifVarContains", label="如果变量包含", category="条件判断", runtime="emitter",
    is_container=True, closes_with="endIf",
    icon="fa-search", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=50)
class IfVarContainsHandler:
    params = [
        Param("varName", "变量名", "varName", required=True),
        Param("substring", "包含文本", "text", required=True),
    ]

@register_handler(type="ifListContains", label="如果列表包含", category="条件判断", runtime="emitter",
    is_container=True, closes_with="endIf",
    icon="fa-list", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=60)
class IfListContainsHandler:
    params = [
        Param("listVar", "列表变量", "varName", required=True),
        Param("value", "查找值", "text", required=True),
    ]

@register_handler(type="ifDictContains", label="如果字典包含键", category="条件判断", runtime="emitter",
    is_container=True, closes_with="endIf",
    icon="fa-book", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=70)
class IfDictContainsHandler:
    params = [
        Param("dictVar", "字典变量", "varName", required=True),
        Param("key", "键名", "text", required=True),
    ]


# ─── 异常处理 ────────────────────────────────────────────────

@register_handler(type="try", label="尝试执行", category="异常处理", runtime="emitter",
    is_container=True, closes_with="endTry",
    icon="fa-shield-alt", icon_color="text-red-500", bg_color="bg-red-50", category_order=87, command_order=10,
    description="尝试执行内部指令，出错时跳到 catch 分支")
class TryHandler:
    params = []

@register_handler(type="catch", label="捕获异常", category="异常处理", runtime="emitter",
    is_container=True, is_branch=True,
    icon="fa-exclamation-triangle", icon_color="text-red-500", bg_color="bg-red-50", category_order=87, command_order=20)
class CatchHandler:
    params = [
        Param("errorVar", "错误信息保存到", "varName", default="error", group="output"),
    ]


# ─── 分支 ─────────────────────────────────────────────────────

@register_handler(type="else", label="否则", category="条件判断", runtime="emitter",
    is_container=True, is_branch=True,
    icon="fa-code-branch", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=15)
class ElseHandler:
    params = []


# ─── 结构标记（闭合标签）────────────────────────────────────

@register_handler(type="endFor", label="结束循环", category="循环", runtime="emitter",
    is_structural=True,
    icon="fa-level-up-alt", icon_color="text-gray-400", bg_color="bg-gray-50", category_order=80, command_order=99)
class EndForHandler:
    params = []

@register_handler(type="endIf", label="结束判断", category="条件判断", runtime="emitter",
    is_structural=True,
    icon="fa-level-up-alt", icon_color="text-gray-400", bg_color="bg-gray-50", category_order=85, command_order=99)
class EndIfHandler:
    params = []

@register_handler(type="endTry", label="结束异常处理", category="异常处理", runtime="emitter",
    is_structural=True,
    icon="fa-level-up-alt", icon_color="text-gray-400", bg_color="bg-gray-50", category_order=87, command_order=99)
class EndTryHandler:
    params = []

@register_handler(type="break", label="跳出循环", category="循环", runtime="emitter",
    is_branch=True,
    icon="fa-eject", icon_color="text-gray-400", bg_color="bg-gray-50", category_order=80, command_order=95)
class BreakHandler:
    params = []

@register_handler(type="continue", label="继续下一轮", category="循环", runtime="emitter",
    is_branch=True,
    icon="fa-forward", icon_color="text-gray-400", bg_color="bg-gray-50", category_order=80, command_order=96)
class ContinueHandler:
    params = []
