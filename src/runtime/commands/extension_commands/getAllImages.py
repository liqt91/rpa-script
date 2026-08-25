"""Command: 获取页面所有图片"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="getAllImages", label="获取页面所有图片",
    category="浏览器元素操作", runtime="extension",
    icon="fa-images", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="获取页面上所有图片的链接地址（含懒加载、srcset 多尺寸、可选 CSS 背景图），结果保存到变量",
    category_order=20,
    command_order=56,
)
class GetAllImagesHandler:
    params = [
        Param("onlyVisible", "仅可见图片", "boolean", default=False, group="advanced"),
        Param("deduplicate", "去重", "boolean", default=True, group="advanced"),
        Param("includeSrcset", "解析 srcset 多尺寸", "boolean", default=True, group="advanced"),
        Param("includeCssBackground", "包含 CSS 背景图", "boolean", default=False, group="advanced"),
        Param("resultVar", "保存到变量", "string", default="images", group="output", description="匹配到的图片列表（数组，含 src/alt/尺寸）将保存到此变量"),
    ]