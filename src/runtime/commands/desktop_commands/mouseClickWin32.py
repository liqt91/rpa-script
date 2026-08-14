"""Command: 鼠标点击坐标 — mouseClick (backend)

将鼠标移动到指定坐标并执行点击（OS 级，不依赖目标窗口）。
提供「相对窗口」句柄时，x/y 解释为窗口客户区坐标，自动换算屏幕坐标。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import clean_var_ref
import asyncio


@register_handler(
    cmd="mouseClickWin32", label="鼠标点击",
    category="桌面操作", runtime="backend",
    icon="fa-mouse-pointer", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="移动鼠标到指定坐标并点击（支持相对窗口坐标、双击与右键）",
    category_order=50, command_order=19,
    summary_tpl="({x}, {y}) {clickType}",
)
class MouseClickHandler:
    params = [
        Param("x", "X 坐标", "number", required=True,
              placeholder="屏幕 X；提供「相对窗口」时为窗口客户区 X"),
        Param("y", "Y 坐标", "number", required=True,
              placeholder="屏幕 Y；提供「相对窗口」时为窗口客户区 Y"),
        Param("windowHwnd", "相对窗口 (HWND变量，可选)", "str-var", default="",
              placeholder="提供后 x/y 按窗口客户区坐标解释"),
        Param("clickType", "点击类型", "select", default="single",
              options=[
                  {"label": "单击左键", "value": "single"},
                  {"label": "双击左键", "value": "double"},
                  {"label": "右键单击", "value": "right"},
              ]),
        Param("resultVar", "结果存入变量(坐标)", "str-var", default="",
              placeholder="实际屏幕坐标存入此变量"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import resolve_hwnd, is_windows, window_exists

        extra = instr.get("extra", {})
        try:
            x = int(extra.get("x", 0))
            y = int(extra.get("y", 0))
        except (ValueError, TypeError):
            x = 0
            y = 0
        click_type = extra.get("clickType", "single")
        win_var = clean_var_ref(extra.get("windowHwnd", ""))
        result_var = clean_var_ref(extra.get("resultVar", ""))

        if not is_windows():
            result = {"error": "当前系统非 Windows，不支持桌面鼠标操作"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        if win_var:
            hwnd = resolve_hwnd(runner.vars.get(win_var))
            if not hwnd or not window_exists(hwnd):
                result = {"error": f"相对窗口句柄无效: {win_var} = {hwnd}"}
                runner.completed += 1
                runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                        "status": "error", "result": result})
                await runner._emit({"type": "stepError", "stepId": step_id,
                                    "nodeId": instr.get("nodeId"), "error": result["error"]})
                return False
            pt = wintypes.POINT(x, y)
            user32.ClientToScreen(hwnd, ctypes.byref(pt))
            sx, sy = pt.x, pt.y
        else:
            sx, sy = x, y

        user32.SetCursorPos(sx, sy)
        await asyncio.sleep(0.05)

        if click_type == "right":
            user32.mouse_event(0x0008, 0, 0, 0, 0)  # RIGHTDOWN
            await asyncio.sleep(0.05)
            user32.mouse_event(0x0010, 0, 0, 0, 0)  # RIGHTUP
        elif click_type == "double":
            for _ in range(2):
                user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
                await asyncio.sleep(0.05)
                user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
                await asyncio.sleep(0.05)
        else:
            user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
            await asyncio.sleep(0.05)
            user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP

        if result_var:
            runner.vars[result_var] = {"x": sx, "y": sy}

        result = {"clicked": True, "x": sx, "y": sy, "clickType": click_type,
                  "log": f"鼠标点击 ({sx}, {sy}) {click_type}"}
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
