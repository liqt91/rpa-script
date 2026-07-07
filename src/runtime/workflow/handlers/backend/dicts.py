"""字典操作 — setDictValue, getDictValue, removeDictKey, stringConcat"""
from ..registry import register_handler, Param
from ..utils import resolve_vars


@register_handler(type="setDictValue", label="设置字典值", category="变量操作", runtime="backend",
    icon="fa-book", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=40)
class SetDictValueHandler:
    params = [
        Param("dictName", "字典变量名", "varName", required=True),
        Param("key", "键名", "text", required=True),
        Param("value", "值", "text"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        name = extra.get("dictName", "")
        key = extra.get("key", "")
        value = resolve_vars(str(extra.get("value", "")), runner.vars)
        if name not in runner.vars or not isinstance(runner.vars[name], dict):
            runner.vars[name] = {}
        runner.vars[name][key] = value
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "success",
            "result": {"setDictValue": name, "key": key}})
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"),
            "result": {"setDictValue": name}})
        return True


@register_handler(type="getDictValue", label="读取字典值", category="变量操作", runtime="backend",
    icon="fa-book-open", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=50)
class GetDictValueHandler:
    params = [
        Param("dictName", "字典变量名", "varName", required=True),
        Param("key", "键名", "text", required=True),
        Param("saveToVar", "保存到变量", "varName", group="output"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        name = extra.get("dictName", "")
        key = extra.get("key", "")
        save_to = extra.get("saveToVar") or extra.get("varName", "")
        val = runner.vars.get(name, {}).get(key)
        if save_to:
            runner.vars[save_to] = val
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "success",
            "result": {"getDictValue": name, "key": key, "value": val}})
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"),
            "result": {"getDictValue": name}})
        return True


@register_handler(type="removeDictKey", label="删除字典键", category="变量操作", runtime="backend",
    icon="fa-trash-alt", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=60)
class RemoveDictKeyHandler:
    params = [
        Param("dictName", "字典变量名", "varName", required=True),
        Param("key", "键名", "text", required=True),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        name = extra.get("dictName", "")
        key = extra.get("key", "")
        if name in runner.vars and isinstance(runner.vars[name], dict):
            runner.vars[name].pop(key, None)
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "success",
            "result": {"removeDictKey": name, "key": key}})
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"),
            "result": {"removeDictKey": name}})
        return True


@register_handler(type="stringConcat", label="字符串拼接", category="变量操作", runtime="backend",
    icon="fa-plus", icon_color="text-green-500", bg_color="bg-green-50", category_order=30, command_order=70)
class StringConcatHandler:
    params = [
        Param("parts", "拼接内容", "text", required=True, placeholder='用 + 连接, 如 "hello" + ${name}'),
        Param("saveToVar", "保存到变量", "varName", group="output"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        parts = extra.get("parts", "")
        save_to = extra.get("saveToVar") or extra.get("varName", "")
        result = resolve_vars(parts, runner.vars)
        if save_to:
            runner.vars[save_to] = result
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "success",
            "result": {"stringConcat": result[:200]}})
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"),
            "result": {"stringConcat": str(result)[:200]}})
        return True
