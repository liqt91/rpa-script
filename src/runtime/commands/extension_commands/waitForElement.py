"""Command: 等待元素出现"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="waitForElement", label="等待元素出现",
    category="页面操作", runtime="extension",
    icon="fa-eye", icon_color="text-yellow-500",
    bg_color="bg-yellow-50",
    description="等待页面上的元素出现，轮询检测直到出现或超时",
    category_order=20,
    command_order=40,
)
class WaitForElementHandler:
    params = [
        Param("elementName", "目标元素", "element", group="主属性", placeholder="选择一个已捕获的元素"),
        Param("timeout", "超时时间（秒）", "number", default=10, group="advanced", description="超过此时间元素未出现则失败"),
        Param("visibilityMode", "可见性", "select", default="visible", options=[{"label": "仅可见", "value": "visible"}, {"label": "所有", "value": "any"}], group="advanced"),
    ]