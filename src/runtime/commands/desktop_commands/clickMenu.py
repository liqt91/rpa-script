"""Command: 点击菜单 — clickMenu (backend)

按菜单路径查找并点击 Windows 窗口菜单项。
通过 Win32 菜单 API (GetMenu/GetSubMenu/GetMenuItemID) 定位菜单项，
发送 WM_COMMAND 消息触发点击。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref


@register_handler(
    cmd="clickMenu", label="点击菜单",
    category="桌面操作", runtime="backend",
    icon="fa-bars", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="按菜单路径查找并点击 Windows 窗口菜单项（如 文件->另存为）",
    category_order=60, command_order=25,
    summary_tpl="{menuPath}",
)
class ClickMenuHandler:
    params = [
        Param("parentWindow", "父窗口 (HWND变量)", "str-var", required=True,
              placeholder="引用 findWindow 或 openApp 存入的窗口句柄变量"),
        Param("menuPath", "菜单路径", "string", required=True,
              placeholder="用 -> 分隔，如 文件->另存为 或 编辑->查找->查找下一个"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import (
            find_menu_item, click_menu, activate_window,
            is_windows, window_exists,
        )

        extra = instr.get("extra", {})
        parent_var = clean_var_ref(extra.get("parentWindow", ""))
        menu_path_str = convert_value(extra.get("menuPath", ""), "string", runner.vars)

        if not menu_path_str:
            result = {"error": "菜单路径为空", "hint": "请填写菜单路径，如 文件→另存为"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        if not is_windows():
            result = {"error": "当前系统非 Windows，不支持桌面菜单操作"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        parent_hwnd = runner.vars.get(parent_var)
        if not parent_hwnd or not window_exists(parent_hwnd):
            result = {"error": f"父窗口句柄无效: {parent_var} = {parent_hwnd}",
                      "hint": "请先使用 findWindow 或 openApp 获取窗口句柄"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        # 解析菜单路径
        path = [p.strip() for p in menu_path_str.split("->") if p.strip()]
        activate_window(parent_hwnd)

        item_id = find_menu_item(parent_hwnd, path)

        if item_id is None:
            result = {
                "found": False,
                "menu_path": menu_path_str,
                "error": f"未找到菜单: {menu_path_str}",
            }
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        if item_id == -1:
            # 子菜单本身没有 ID（如"文件"菜单），无法直接点击
            result = {
                "found": True,
                "clicked": False,
                "menu_path": menu_path_str,
                "error": f"「{path[-1]}」是一个子菜单，请指定完整路径到具体菜单项",
            }
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        ok = click_menu(parent_hwnd, item_id)
        result = {
            "found": True,
            "clicked": ok,
            "menu_path": menu_path_str,
            "item_id": item_id,
            "log": f"点击菜单: {menu_path_str}" if ok else f"菜单点击失败: {menu_path_str}",
        }
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success" if ok else "error", "result": result})
        if ok:
            await runner._emit({"type": "stepComplete", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "result": result})
        else:
            result["error"] = f"菜单点击失败: {menu_path_str}"
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
        return ok
