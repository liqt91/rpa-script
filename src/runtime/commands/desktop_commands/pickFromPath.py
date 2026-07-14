"""Command: 按层级取句柄 — pickFromPath (backend)

从元素库中已捕获的桌面元素（win32）内选取层级，返回该层级的 HWND。
自动从数据库读取元素的 attributes.path 数据。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref
import json


@register_handler(
    cmd="pickFromPath", label="按层级取句柄",
    category="桌面操作", runtime="backend",
    icon="fa-sitemap", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="从元素库桌面元素中选取层级，返回该层级的 HWND",
    category_order=60, command_order=15,
    summary_tpl="{elementName} L{levelIndex}",
)
class PickFromPathHandler:
    params = [
        Param("elementName", "桌面元素", "string", required=True,
              placeholder="元素库中 element_kind=win32 的元素名称，如 Edit \"\"",
              group="主属性"),
        Param("levelIndex", "层级序号", "number", default="0",
              placeholder="0=顶层窗口，-1=最后一层(目标控件)"),
        Param("resultVar", "结果存入变量(HWND)", "str-var", default="",
              placeholder="找到的窗口句柄存入此变量"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import (
            find_window, find_child_window, find_sibling_by_class,
            get_window_text, get_class_name, activate_window,
            is_windows, window_exists, find_window_by_title_fuzzy,
        )
        from src.repo import runtime_models as models
        from src.repo.models import SessionLocal

        extra = instr.get("extra", {})
        element_name = convert_value(extra.get("elementName", ""), "string", runner.vars)
        level_index = int(extra.get("levelIndex", 0) or 0)
        result_var = clean_var_ref(extra.get("resultVar", ""))

        if not is_windows():
            result = {"error": "当前系统非 Windows"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        if not element_name:
            result = {"error": "桌面元素名称为空"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        # 从数据库读取元素的 attributes.path
        wf_id = runner.workflow_id
        if not wf_id:
            result = {"error": "无法获取工作流 ID"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        db = SessionLocal()
        try:
            el = db.query(models.WorkflowElement).filter(
                models.WorkflowElement.workflow_id == wf_id,
                models.WorkflowElement.name == element_name,
            ).first()
            if not el:
                result = {"error": f"未找到桌面元素: {element_name}"}
                runner.completed += 1
                runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                        "status": "error", "result": result})
                await runner._emit({"type": "stepError", "stepId": step_id,
                                    "nodeId": instr.get("nodeId"), "error": result["error"]})
                return False

            attrs = el.attributes
            if isinstance(attrs, str):
                attrs = json.loads(attrs)
            path = attrs.get("path", []) if isinstance(attrs, dict) else []
        finally:
            db.close()

        if not path:
            result = {"error": f"元素 {element_name} 没有控件层级数据"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        # 解析层级序号
        if level_index < 0:
            level_index = max(0, len(path) + level_index)
        if level_index >= len(path):
            level_index = len(path) - 1

        hwnd = None

        # 查找顶层窗口：模糊匹配优先（标题可能被修改，如 "*无标题 - 记事本"）
        def _find_top(top):
            title = top.get("title", "")
            cls = top.get("class_name", "")
            if title:
                matches = find_window_by_title_fuzzy(title)
                if matches: return matches[0]["hwnd"]
            h = find_window(title=title)
            if h: return h
            if cls:
                h = find_window(class_name=cls)
                if h: return h
            return None

        if level_index == 0:
            hwnd = _find_top(path[0])
        else:
            parent_hwnd = _find_top(path[0])
            if not parent_hwnd:
                top = path[0]
                result = {"error": f"未找到顶层窗口: {top.get('title', top.get('class_name'))}"}
                runner.completed += 1
                runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                        "status": "error", "result": result})
                await runner._emit({"type": "stepError", "stepId": step_id,
                                    "nodeId": instr.get("nodeId"), "error": result["error"]})
                return False

            for i in range(1, level_index + 1):
                level = path[i]
                cls = level.get("class_name", "")
                title = level.get("title", "")
                # 子控件：类名优先，找不到则尝试弹出窗口（如对话框 #32770）
                child = find_child_window(parent_hwnd, class_name=cls)
                if not child and title:
                    # 可能是弹出对话框，用独立窗口查找
                    child = find_window(title=title)
                if not child and title:
                    # 模糊匹配
                    matches = find_window_by_title_fuzzy(title)
                    if matches:
                        child = matches[0]["hwnd"]
                if not child:
                    result = {
                        "error": f"第 {i} 层未找到: {cls} \"{title}\"",
                        "found_level": i - 1, "partial_hwnd": parent_hwnd,
                    }
                    runner.completed += 1
                    runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                            "status": "error", "result": result})
                    await runner._emit({"type": "stepError", "stepId": step_id,
                                        "nodeId": instr.get("nodeId"), "error": result["error"]})
                    return False

                parent_hwnd = child
                if i == level_index:
                    hwnd = child

        if hwnd and result_var:
            runner.vars[result_var] = hwnd

        if hwnd:
            result = {
                "found": True, "hwnd": hwnd, "level": level_index,
                "title": get_window_text(hwnd), "class_name": get_class_name(hwnd),
                "log": f"层级[{level_index}]: {get_class_name(hwnd)} \"{get_window_text(hwnd)}\"",
            }
        else:
            result = {"error": f"未找到层级 {level_index}", "level": level_index}

        runner.completed += 1
        status = "success" if hwnd else "error"
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": status, "result": result})
        if hwnd:
            await runner._emit({"type": "stepComplete", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "result": result})
        else:
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result.get("error", "")})
        return bool(hwnd)
