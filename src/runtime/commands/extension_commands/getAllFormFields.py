"""Command: 获取所有表单字段"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="getAllFormFields", label="获取所有表单字段",
    category="浏览器元素操作", runtime="extension",
    icon="fa-list-ul", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="获取页面上所有表单控件（input/textarea/select），含 name/type/value/placeholder/关联 label",
    category_order=20,
    command_order=57,
)
class GetAllFormFieldsHandler:
    params = [
        Param("includeHidden", "包含隐藏字段", "boolean", default=False, group="advanced"),
        Param("includeSelect", "包含下拉框", "boolean", default=True, group="advanced"),
        Param("resultVar", "保存到变量", "string", default="fields", group="output", description="表单字段列表（数组，含 tag/name/type/value/placeholder/label）将保存到此变量"),
    ]