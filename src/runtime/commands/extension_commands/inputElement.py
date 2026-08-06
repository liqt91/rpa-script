"""Command: 输入文本"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="inputElement", label="输入文本",
    category="浏览器元素操作", runtime="extension",
    icon="fa-keyboard", icon_color="text-blue-500",
    bg_color="bg-blue-50",
    description="在页面输入框中输入文本，可选输入完成后按回车",
    category_order=20,
    command_order=30,
)
class InputElementHandler:
    params = [
        Param("elementName", "元素", "element", required=True),
        Param("text", "输入内容", "string", required=True),
        Param("simulateKeyboard", "模拟键盘输入", "boolean", default=True, description="勾选后使用操作系统真实键盘逐字输入（事件可信、抗反检测）；输入前需元素已获焦点，请在前面添加「点击元素」指令获取焦点。不勾选则用 DOM 合成输入（快速）。"),
        Param("pressEnter", "输入后按回车", "boolean", default=False),
        Param("scope", "匹配范围", "select", default="local", options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}], group="advanced"),
        Param("loopAnchor", "锚点元素", "string", default="", group="anchor"),
        Param("visibilityMode", "元素可见性", "select", default="visible", options=[{"label": "仅可见", "value": "visible"}, {"label": "所有", "value": "any"}], group="advanced"),
    ]