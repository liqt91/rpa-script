"""Command: 获取网页输入框"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="getInputBoxes", label="获取网页输入框",
    category="浏览器元素操作", runtime="extension",
    icon="fa-edit", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="获取网页上所有输入框（input/textarea），含 name/type/value/placeholder/关联 label，结果保存到变量",
    category_order=20,
    command_order=58,
)
class GetInputBoxesHandler:
    params = [
        Param("includeTextarea", "包含多行文本框", "boolean", default=True, group="advanced"),
        Param("includeHidden", "包含隐藏字段", "boolean", default=False, group="advanced"),
        Param("resultVar", "保存到变量", "string", default="inputs", group="output", description="输入框列表（数组，含 tag/name/type/value/placeholder/label/id）将保存到此变量"),
    ]