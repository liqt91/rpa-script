"""Command: 打开浏览器"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="launchBrowser", label="打开浏览器",
    category="浏览器", runtime="extension",
    icon="fa-globe", icon_color="text-blue-500",
    bg_color="bg-blue-50",
    description="启动浏览器并加载RPA扩展",
    category_order=10,
    command_order=10,
    summary_tpl="{browserType} {url}",
)
class LaunchBrowserHandler:
    params = [
        Param("browserType", "浏览器", "select", default="chrome", options=[{"label": "Chrome", "value": "chrome"}, {"label": "Edge", "value": "edge"}]),
        Param("url", "启动后打开网址", "string", default="about:blank", placeholder="留空则打开 about:blank"),
        Param("windowState", "窗口状态", "select", default="normal", options=[{"label": "普通", "value": "normal"}, {"label": "最大化", "value": "maximized"}, {"label": "最小化", "value": "minimized"}], group="advanced"),
        Param("windowVar", "保存窗口对象到", "string", default="browser1", group="output"),
    ]