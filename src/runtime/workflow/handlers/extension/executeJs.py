"""Extension handler 声明 — 参数定义，实现在 content.js"""
from ..registry import register_handler, Param
@register_handler(type="executeJs", label="执行JavaScript", category="高级", runtime="extension",
    icon="fa-code", icon_color="text-gray-700", bg_color="bg-gray-100", category_order=90, command_order=50)
class ExecuteJsHandler:
    params = [
        Param("code", "JS代码", "code", required=True),
        Param("saveToVar", "保存返回值到", "varName", group="output"),
    ]


# ═══════════════════════════════════════════════════════════
# 容器/结构指令 — runtime="emitter"
# ═══════════════════════════════════════════════════════════
