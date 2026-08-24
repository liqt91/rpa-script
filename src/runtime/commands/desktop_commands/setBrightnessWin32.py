"""
设置屏幕亮度 — setBrightnessWin32 (backend)

通过 WMI（root\\WMI / WmiMonitorBrightnessMethods）或 Dxva2 Physical Monitor API
（DDC/CI）将显示器/屏幕亮度调整到指定百分比（0-100，0 为最暗），
不依赖浏览器，适用于桌面自动化。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value


@register_handler(cmd="setBrightnessWin32", label="设置屏幕亮度",
    category="桌面操作", runtime="backend",
    icon="fa-sun", icon_color="text-yellow-500",
    bg_color="bg-yellow-50",
    description="将显示器/屏幕亮度调整到指定大小（0-100，0 为最暗），不依赖浏览器，适用于桌面自动化（笔记本内屏 + DDC/CI 外接显示器）。",
    category_order=50,
    command_order=20,
)
class SetBrightnessWin32Handler:
    params = [
        Param("brightness", "目标亮度", "number", required=True, default=50, placeholder="0-100，支持 {{变量}} 引用；0=最暗，100=最亮"),
        Param("applyTo", "应用范围", "select", default="all", options=[{"label": "所有显示器", "value": "all"}, {"label": "主显示器", "value": "primary"}], placeholder="选择要调节的显示器范围"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import set_brightness, get_brightness, is_windows

        extra = instr.get("extra", {})

        # 读取目标亮度（支持 {{变量}} 引用），容错回退默认值
        raw = extra.get("brightness", 50)
        try:
            brightness = convert_value(raw, "number", runner.vars)
            brightness = int(brightness)
        except (ValueError, TypeError):
            brightness = 50
        brightness = max(0, min(100, brightness))

        # 应用范围：all / primary，非法值回退 all
        scope = str(extra.get("applyTo", "all") or "all").strip()
        if scope not in ("all", "primary"):
            scope = "all"

        if not is_windows():
            result = {"error": "当前系统非 Windows，设置亮度仅支持 Windows",
                      "brightness": brightness, "scope": scope}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                   "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        res = set_brightness(brightness, scope)
        if not res.get("ok"):
            error = res.get("error", f"设置亮度失败: {brightness}")
            result = {"error": error, "brightness": brightness,
                      "scope": scope, "source": res.get("source")}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                   "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": error})
            return False

        # 设置后回读当前亮度，用于校验/展示
        current = get_brightness() or {}
        cur_val = current.get("current")
        log = f"亮度已设置为 {brightness}%（通道：{res.get('source')}）"
        if cur_val is not None:
            log += f"，当前读数 {cur_val}%"
        result = {
            "brightness": brightness,
            "scope": scope,
            "source": res.get("source"),
            "current": cur_val,
            "log": log,
        }
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                               "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
