"""Command: 获取所有标签页"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="getAllTabs", label="获取所有标签页",
    category="浏览器操作", runtime="extension",
    icon="fa-clone", icon_color="text-blue-500",
    bg_color="bg-blue-50",
    description="获取指定浏览器窗口（或所有窗口）中打开的全部标签页列表，可保存到变量",
    category_order=10,
    command_order=45,
)
class GetAllTabsHandler:
    params = [
        Param("windowVar", "浏览器窗口", "string", group="input", placeholder="如 browser1，留空使用当前工作窗口"),
        Param("onlyWebPages", "仅网页", "boolean", default=True, group="advanced", description="过滤 chrome://、edge://、扩展页、file://、about: 等受限页面"),
        Param("resultVar", "保存到变量", "string", default="tabs", group="output", description="标签页列表（数组，每项含 index/url/title/active/id/windowId）将保存到此变量"),
    ]