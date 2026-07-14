"""Command: 发送按键 — sendKey (backend)

通过 Win32 keybd_event 发送 OS 级键盘按键，不依赖浏览器。
适用于桌面自动化场景（对话框、窗口操作等）。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value
import asyncio


@register_handler(
    cmd="sendKey", label="发送按键",
    category="桌面操作", runtime="backend",
    icon="fa-keyboard", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="通过 OS 级键盘事件发送按键（不依赖浏览器，适用于桌面操作）",
    category_order=60, command_order=45,
    summary_tpl="{key}",
)
class SendKeyHandler:
    params = [
        Param("key", "按键", "select", required=True, default="Enter",
              options=[
                  {"label": "Enter 回车", "value": "Enter"},
                  {"label": "Tab 制表", "value": "Tab"},
                  {"label": "Escape 取消", "value": "Escape"},
                  {"label": "Backspace 退格", "value": "Backspace"},
                  {"label": "Delete 删除", "value": "Delete"},
                  {"label": "Space 空格", "value": "Space"},
                  {"label": "ArrowUp ↑", "value": "ArrowUp"},
                  {"label": "ArrowDown ↓", "value": "ArrowDown"},
                  {"label": "ArrowLeft ←", "value": "ArrowLeft"},
                  {"label": "ArrowRight →", "value": "ArrowRight"},
                  {"label": "PageUp 上翻", "value": "PageUp"},
                  {"label": "PageDown 下翻", "value": "PageDown"},
                  {"label": "Home", "value": "Home"},
                  {"label": "End", "value": "End"},
                  {"label": "F1", "value": "F1"},
                  {"label": "F5 刷新", "value": "F5"},
                  {"label": "F12", "value": "F12"},
                  {"label": "Ctrl+C 复制", "value": "c", "modifiers": "Ctrl"},
                  {"label": "Ctrl+V 粘贴", "value": "v", "modifiers": "Ctrl"},
                  {"label": "Ctrl+A 全选", "value": "a", "modifiers": "Ctrl"},
                  {"label": "Ctrl+Z 撤销", "value": "z", "modifiers": "Ctrl"},
                  {"label": "Ctrl+S 保存", "value": "s", "modifiers": "Ctrl"},
                  {"label": "Alt+F4 关闭", "value": "F4", "modifiers": "Alt"},
                  {"label": "Alt+Tab 切换窗口", "value": "Tab", "modifiers": "Alt"},
                  {"label": "字母 a-z", "value": "a"},
                  {"label": "数字 0-9", "value": "0"},
              ]),
        Param("keyCustom", "自定义按键", "string", default="",
              placeholder="输入按键名如 Enter、a、F5 等，支持所有 VK 码对应按键",
              group="advanced"),
        Param("modifiers", "修饰键", "string", default="",
              placeholder="Ctrl, Alt, Shift, Win，可多个逗号分隔如 Ctrl,Shift",
              group="advanced"),
        Param("pressCount", "重复次数", "int-number", default="1",
              placeholder="连续按几次，如需要多次 Tab 跳转",
              group="advanced"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import send_key, is_windows

        # 快捷键自动修饰键
        _AUTO_MODIFIER = {
            "c": "Ctrl", "v": "Ctrl", "a": "Ctrl", "z": "Ctrl",
            "s": "Ctrl", "x": "Ctrl", "y": "Ctrl",
        }

        extra = instr.get("extra", {})
        key = extra.get("key", "Enter")
        key_custom = convert_value(extra.get("keyCustom", ""), "string", runner.vars)
        modifiers = extra.get("modifiers", "")
        press_count = int(extra.get("pressCount", 1) or 1)

        if key_custom:
            key = key_custom

        # 自动检测快捷键修饰键（如选 Ctrl+C 时自动补 Ctrl）
        if not modifiers and key in _AUTO_MODIFIER:
            modifiers = _AUTO_MODIFIER[key]

        if not is_windows():
            result = {"error": "当前系统非 Windows，sendKey 仅支持 Windows"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        for i in range(press_count):
            ok = send_key(key, modifiers)
            if not ok:
                result = {"error": f"按键发送失败: {key}", "key": key, "modifiers": modifiers}
                runner.completed += 1
                runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                        "status": "error", "result": result})
                await runner._emit({"type": "stepError", "stepId": step_id,
                                    "nodeId": instr.get("nodeId"), "error": result["error"]})
                return False
            if press_count > 1 and i < press_count - 1:
                await asyncio.sleep(0.1)

        result = {
            "pressed": key,
            "modifiers": modifiers,
            "count": press_count,
            "log": f"按键: {key}" + (f"+{modifiers}" if modifiers else "") + (f" x{press_count}" if press_count > 1 else ""),
        }
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
