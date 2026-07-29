"""Command: 截图"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="takeScreenshot", label="截图",
    category="浏览器元素操作", runtime="extension",
    icon="fa-camera", icon_color="text-gray-700",
    bg_color="bg-gray-100",
    description="截取页面或元素的截图",
    category_order=20,
    command_order=90,
)
class TakeScreenshotHandler:
    params = [
        Param("elementName", "目标元素(可选)", "element", group="主属性", placeholder="留空则截取整个页面"),
        Param("saveToVar", "保存到变量(base64)", "string", group="output"),
    ]