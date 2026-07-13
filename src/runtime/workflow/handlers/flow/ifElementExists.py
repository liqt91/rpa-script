"""判断元素存在 — 控制流"""
from ..registry import register_handler, Param
@register_handler(cmd="ifElementExists", label="判断元素存在", category="条件判断", runtime="control",
    is_container=True, closes_with="endIf",
    icon="fa-search", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=20,
    description="判断元素是否存在，决定分支走向")
class IfElementExistsHandler:
    params = [
        Param("element_name", "元素", "str-element", required=True, group="主属性"),
        Param("operator", "判断条件", "str-dropdown",
              options=[{"label": "存在", "value": "exists"}, {"label": "不存在", "value": "notExists"}],
              default="exists"),
        Param("scope", "匹配范围", "str-dropdown",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]

    @staticmethod
    async def evaluate(runner, instr):
        extra = runner._resolve_vars(instr.get("extra") or {}, runner.vars)
        locator = instr.get("locator") or extra.get("locator", "")
        selector_family = instr.get("selectorFamily") or extra.get("selector_family", "css")
        timeout = extra.get("timeout", 3)
        op = extra.get("operator", "exists")
        res = await runner._check_element_exists(locator, selector_family, timeout=timeout, extra=extra)
        met = not res if op == "notExists" else res
        return {"met": met, "elements": [{"locator": locator, "family": selector_family, "exists": res}]}
