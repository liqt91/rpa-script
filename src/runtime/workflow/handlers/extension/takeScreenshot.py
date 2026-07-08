"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="takeScreenshot", label="截图", category="高级", runtime="extension",
    icon="fa-camera", icon_color="text-gray-700", bg_color="bg-gray-100", category_order=90, command_order=40)
class TakeScreenshotHandler:
    params = [
        Param("element_name", "目标元素(可选)", "str-element", required=False, group="主属性"),
        Param("saveToVar", "保存到变量(base64)", "str-var", group="output"),
    ]
