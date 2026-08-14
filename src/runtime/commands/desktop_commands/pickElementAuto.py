"""Command: 从元素库取控件（自动选择）— pickElementAuto

按元素库中已捕获的桌面元素取指定层级控件，自动按元素类型路由：
  - 元素 element_type=uia   → UIA 通道（_uia.pick_from_path）
  - 元素 element_type=win32 → Win32 通道（层级句柄查找）
结果以统一控件引用存入 resultVar，可直接交给「点击控件/输入文字」自动指令消费。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref
import json


@register_handler(
    cmd="pickElementAuto", label="从元素库取控件",
    category="桌面操作", runtime="backend",
    icon="fa-sitemap", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="按元素库中已捕获的桌面元素取指定层级控件，自动选择 UIA/Win32 通道，结果可直接用于点击/输入",
    category_order=50, command_order=9,
    summary_tpl="{elementName} L{levelIndex}",
)
class PickElementAutoHandler:
    params = [
        Param("elementName", "桌面元素", "string", required=True,
              placeholder="元素库中 element_type=win32/uia 的元素名称"),
        Param("levelIndex", "层级序号", "number", default="-1",
              placeholder="0=顶层，-1=最后一层(目标控件)"),
        Param("resultVar", "结果存入变量", "str-var", default="",
              placeholder="统一控件引用存入此变量"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._desktop_ref import make_win32_ref, make_uia_ref
        from ._win32 import (
            find_window, find_window_by_title_fuzzy, find_child_window,
            get_window_text, get_class_name, is_windows,
        )

        extra = instr.get("extra", {})
        element_name = convert_value(extra.get("elementName", ""), "string", runner.vars)
        try:
            level_index = int(extra.get("levelIndex", -1) or -1)
        except (ValueError, TypeError):
            level_index = -1
        result_var = clean_var_ref(extra.get("resultVar", ""))

        if not is_windows():
            result = {"error": "当前系统非 Windows，不支持桌面窗口操作"}
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

        from src.repo import runtime_models as models
        from src.repo.models import SessionLocal

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
                result = {"error": f"未找到元素: {element_name}"}
                runner.completed += 1
                runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                        "status": "error", "result": result})
                await runner._emit({"type": "stepError", "stepId": step_id,
                                    "nodeId": instr.get("nodeId"), "error": result["error"]})
                return False
            attrs = el.attributes
            if isinstance(attrs, str):
                attrs = json.loads(attrs)
            attrs = attrs if isinstance(attrs, dict) else {}
            element_type = el.element_type or attrs.get("element_type", "win32")
            path = attrs.get("path", []) or []
            target_index = attrs.get("uia_target_index")
            if not isinstance(target_index, int):
                target_index = None
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

        if level_index < 0:
            level_index = max(0, len(path) + level_index)

        ref = None
        via = None
        if element_type == "uia":
            from ._uia import is_uia_available, pick_from_path
            if not is_uia_available():
                result = {"error": "UIAutomation 不可用"}
                runner.completed += 1
                runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                        "status": "error", "result": result})
                await runner._emit({"type": "stepError", "stepId": step_id,
                                    "nodeId": instr.get("nodeId"), "error": result["error"]})
                return False
            target = pick_from_path(path, level_index, target_index=target_index)
            if target:
                ref = make_uia_ref(target)
                via = "uia"
        else:
            # Win32 层级查找（与 pickFromPathWin32 同逻辑）
            def _find_top(top):
                title = top.get("title", "")
                cls = top.get("class_name", "")
                if title:
                    matches = find_window_by_title_fuzzy(title)
                    if matches:
                        return matches[0]["hwnd"]
                h = find_window(title=title)
                if h:
                    return h
                if cls:
                    h = find_window(class_name=cls)
                    if h:
                        return h
                return None

            parent_hwnd = _find_top(path[0])
            if parent_hwnd and level_index > 0:
                for i in range(1, min(level_index + 1, len(path))):
                    level = path[i]
                    cls = level.get("class_name", "")
                    title = level.get("title", "")
                    idx = level.get("index")
                    if not isinstance(idx, int) or idx < 0:
                        idx = 0
                    child = find_child_window(parent_hwnd, class_name=cls, index=idx)
                    if not child:
                        child = find_child_window(parent_hwnd, class_name=cls)
                    if not child and title:
                        child = find_window(title=title)
                    if not child and title:
                        matches = find_window_by_title_fuzzy(title)
                        if matches:
                            child = matches[0]["hwnd"]
                    if not child:
                        parent_hwnd = None
                        break
                    parent_hwnd = child
            if parent_hwnd:
                ref = make_win32_ref(parent_hwnd,
                                     title=get_window_text(parent_hwnd),
                                     class_name=get_class_name(parent_hwnd))
                via = "win32"

        if not ref:
            result = {"error": f"元素 {element_name} 层级 {level_index} 未找到",
                      "level": level_index}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        if result_var:
            runner.vars[result_var] = ref

        result = {"found": True, "via": via, "level": level_index,
                  "name": ref.get("name") or ref.get("title", ""),
                  "class_name": ref.get("class_name", ""),
                  "control_type": ref.get("control_type", ""),
                  "log": f"层级[{level_index}]({via}): {ref.get('name') or ref.get('title')}"}
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
