"""Command: 查找兄弟控件 — findSibling (backend)

从参考控件出发，按方向查找匹配类名的兄弟控件。
常用于从 Static 标签定位到旁边的 Edit/ComboBox 输入框。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import clean_var_ref


@register_handler(
    cmd="findSibling", label="查找兄弟控件",
    category="桌面操作", runtime="backend",
    icon="fa-arrow-right", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="从参考控件出发，按方向查找匹配类名的兄弟控件（如标签→输入框）",
    category_order=60, command_order=13,
    summary_tpl="{direction} {classFilter}",
)
class FindSiblingHandler:
    params = [
        Param("refWindow", "参考控件 (HWND变量)", "str-var", required=True,
              placeholder="引用已知的控件句柄变量，如标签 Static"),
        Param("direction", "查找方向", "select", default="next",
              options=[
                  {"label": "下一个 (→)", "value": "next"},
                  {"label": "上一个 (←)", "value": "prev"},
              ]),
        Param("classFilter", "目标类名", "select", default="Edit",
              options=[
                  {"label": "Edit (输入框)", "value": "Edit"},
                  {"label": "Button (按钮)", "value": "Button"},
                  {"label": "ComboBox (下拉框)", "value": "ComboBox"},
                  {"label": "ComboBoxEx32", "value": "ComboBoxEx32"},
                  {"label": "Static (标签)", "value": "Static"},
                  {"label": "ListBox (列表框)", "value": "ListBox"},
                  {"label": "不筛选", "value": ""},
              ]),
        Param("skip", "跳过几个", "int-number", default="0",
              placeholder="跳过前N个匹配项，0=第一个"),
        Param("resultVar", "结果存入变量", "str-var", default="",
              placeholder="找到的控件句柄存入此变量"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import find_sibling_by_class, get_window_text, get_class_name, is_windows, window_exists

        extra = instr.get("extra", {})
        ref_var = clean_var_ref(extra.get("refWindow", ""))
        direction = extra.get("direction", "next")
        class_filter = extra.get("classFilter", "Edit") or ""
        skip = int(extra.get("skip", 0) or 0)
        result_var = clean_var_ref(extra.get("resultVar", ""))

        if not is_windows():
            result = {"error": "当前系统非 Windows"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        ref_hwnd = runner.vars.get(ref_var)
        if not ref_hwnd or not window_exists(ref_hwnd):
            result = {"error": f"参考控件句柄无效: {ref_var} = {ref_hwnd}"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        sibling = find_sibling_by_class(ref_hwnd, class_filter, direction, skip)
        if not sibling:
            result = {
                "found": False,
                "error": f"未找到兄弟控件: {direction} class={class_filter} skip={skip}",
            }
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        if result_var:
            runner.vars[result_var] = sibling

        result = {
            "found": True,
            "hwnd": sibling,
            "title": get_window_text(sibling),
            "class_name": get_class_name(sibling),
            "log": f"兄弟控件: {get_class_name(sibling)} \"{get_window_text(sibling)}\"",
        }
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
