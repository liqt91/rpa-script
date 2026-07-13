"""
Emitter handler definitions — container/structural commands.
These are expanded by the Python emitter, not executed by a handler.
"""
from ..registry import register_handler, Param
@register_handler(cmd="ifElementVisible", label="如果元素可见", category="条件判断", runtime="control",
    is_container=True, closes_with="endIf",
    icon="fa-eye", icon_color="text-cyan-500", bg_color="bg-cyan-50", category_order=85, command_order=10,
    description="根据元素是否可见决定执行分支")
class IfElementVisibleHandler:
    params = [
        Param("element_name", "元素", "str-element", required=True, group="主属性"),
        Param("operator", "判断条件", "str-dropdown",
              options=[{"label": "可见", "value": "visible"}, {"label": "不可见", "value": "notVisible"}],
              default="visible"),
        Param("scope", "匹配范围", "str-dropdown",
              options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}],
              default="local", group="advanced"),
    ]
    @staticmethod
    async def evaluate(runner, instr):
        import logging
        logger = logging.getLogger(__name__)
        extra = runner._resolve_vars(instr.get("extra") or {}, runner.vars)
        locator = instr.get("locator") or extra.get("locator", "")
        selector_family = instr.get("selectorFamily") or extra.get("selector_family", "css")
        timeout = extra.get("timeout", 3)
        op = extra.get("operator", "visible")
        locators = [(locator, selector_family)]
        for alt in instr.get("altLocators") or []:
            locators.append((alt.get("locator"), alt.get("selectorFamily") or selector_family))
        logger.info(f"evaluating ifElementVisible locators={locators} timeout={timeout} operator={op}")
        elements, results = [], []
        for loc, fam in locators:
            res = await runner._check_element_visible(loc, fam, timeout=timeout, extra=extra)
            results.append(res)
            elements.append({"locator": loc, "family": fam, "visible": res})
        logger.info(f"ifElementVisible results={results}")
        met = not any(results) if op == "notVisible" else any(results)
        return {"met": met, "cmdType": "ifElementVisible", "operator": op, "elements": elements}

