"""Command: 检测加载失败图片"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="findBrokenImages", label="检测加载失败图片",
    category="浏览器元素操作", runtime="extension",
    icon="fa-image", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="检测页面上加载失败的图片（naturalWidth===0 或加载出错），返回 src/alt",
    category_order=20,
    command_order=60,
)
class FindBrokenImagesHandler:
    params = [
        Param("deduplicate", "去重", "boolean", default=True, group="advanced"),
        Param("resultVar", "保存到变量", "string", default="brokenImages", group="output", description="加载失败的图片列表（数组，含 src/alt）将保存到此变量"),
    ]