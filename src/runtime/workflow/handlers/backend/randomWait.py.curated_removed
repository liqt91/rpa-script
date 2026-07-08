"""Backend handler — randomWait"""
from ..registry import register_handler, Param
@register_handler(type="randomWait", label="随机等待", category="等待", runtime="backend",
    icon="fa-random", icon_color="text-yellow-500", bg_color="bg-yellow-50", category_order=20, command_order=20,
    description="随机等待 min~max 秒")
class RandomWaitHandler:
    params = [
        Param("min", "最小秒数", "int-number", default=1),
        Param("max", "最大秒数", "int-number", default=5),
    ]


# ═══════════════════════════════════════════════════════════
# 变量操作
# ═══════════════════════════════════════════════════════════
