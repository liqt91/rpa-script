"""
设置音量 — setVolumeWin32 (backend)

通过 Win32 winmm.waveOutSetVolume 将系统主音量调整到指定百分比（0-100，0 为静音），
不依赖浏览器，适用于桌面自动化。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value
import asyncio


@register_handler(cmd="setVolumeWin32", label="设置音量",
    category="桌面操作", runtime="backend",
    icon="fa-volume-up", icon_color="text-amber-500",
    bg_color="bg-amber-50",
    description="将系统主音量调整到指定大小（0-100，0 为静音），不依赖浏览器，适用于桌面自动化",
    category_order=50,
    command_order=19,
)
class SetVolumeWin32Handler:
    params = [
        Param("volume", "目标音量", "number", required=True, default=50, placeholder="0-100，支持 {{变量}} 引用；0=静音，100=最大"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import set_volume, get_volume, is_windows

        extra = instr.get("extra", {})

        # 读取目标音量（支持 {{变量}} 引用），容错回退默认值
        raw_volume = extra.get("volume", 50)
        try:
            volume = convert_value(raw_volume, "number", runner.vars)
            volume = int(volume)
        except (ValueError, TypeError):
            volume = 50
        volume = max(0, min(100, volume))

        if not is_windows():
            result = {"error": "当前系统非 Windows，设置音量仅支持 Windows", "volume": volume}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                   "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        ok = set_volume(volume)
        if not ok:
            result = {"error": f"设置音量失败: {volume}", "volume": volume}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                   "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        # 设置后回读当前音量，用于校验/展示
        current = get_volume()
        result = {
            "volume": volume,
            "current": current,
            "log": f"音量已设置为 {volume}%" + (f"（当前读数 {current}%）" if current != volume else ""),
        }
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                               "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
