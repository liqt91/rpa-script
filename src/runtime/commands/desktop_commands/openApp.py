"""Command: 打开软件 — openApp (backend)

启动 Windows 自带软件或常用程序。
使用 subprocess.Popen 启动，不阻塞工作流执行。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref
import subprocess
import asyncio
import os


# 常用 Windows 软件映射
_APP_MAP = {
    "notepad":      {"label": "记事本",      "cmd": "notepad.exe"},
    "calc":         {"label": "计算器",      "cmd": "calc.exe"},
    "mspaint":      {"label": "画图",       "cmd": "mspaint.exe"},
    "snippingtool": {"label": "截图工具",    "cmd": "snippingtool.exe"},
    "explorer":     {"label": "文件资源管理器", "cmd": "explorer.exe"},
    "cmd":          {"label": "命令提示符",   "cmd": "cmd.exe"},
    "powershell":   {"label": "PowerShell", "cmd": "powershell.exe"},
    "taskmgr":      {"label": "任务管理器",   "cmd": "taskmgr.exe"},
    "control":      {"label": "控制面板",    "cmd": "control.exe"},
    "write":        {"label": "写字板",      "cmd": "write.exe"},
    "charmap":      {"label": "字符映射表",   "cmd": "charmap.exe"},
    "winver":       {"label": "关于Windows", "cmd": "winver.exe"},
    "dxdiag":       {"label": "DirectX诊断", "cmd": "dxdiag.exe"},
    "regedit":      {"label": "注册表编辑器",  "cmd": "regedit.exe"},
    "devmgmt":      {"label": "设备管理器",   "cmd": "devmgmt.msc"},
    "diskmgmt":     {"label": "磁盘管理",    "cmd": "diskmgmt.msc"},
    "services":     {"label": "服务",       "cmd": "services.msc"},
    "__custom__":   {"label": "自定义程序",   "cmd": ""},
}


@register_handler(
    cmd="openApp", label="打开软件",
    category="桌面操作", runtime="backend",
    icon="fa-rocket", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="启动 Windows 自带软件或常用程序",
    category_order=60, command_order=5,
    summary_tpl="{app}",
)
class OpenAppHandler:
    params = [
        Param("app", "选择软件", "select", default="notepad",
              options=[{"label": v["label"], "value": k} for k, v in _APP_MAP.items()]),
        Param("appCustom", "自定义程序路径", "string", default="",
              placeholder="选择「自定义程序」时填写，如 C:\\Tools\\app.exe"),
        Param("arguments", "启动参数", "string", default="",
              placeholder="如文件路径或命令行参数，支持 {{变量}} 引用",
              group="advanced"),
        Param("resultVar", "窗口句柄存入变量", "str-var", default="",
              placeholder="将打开窗口的句柄(HWND)存入变量，供后续 clickControl/inputControl 使用",
              group="output"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra", {})
        app_key = extra.get("app", "notepad")
        app_custom = convert_value(extra.get("appCustom", ""), "string", runner.vars)
        arguments = convert_value(extra.get("arguments", ""), "string", runner.vars)
        result_var = clean_var_ref(extra.get("resultVar", ""))

        if app_key == "__custom__":
            exe = app_custom
            if not exe:
                result = {"error": "自定义程序路径为空", "hint": "请在「自定义程序路径」中填写程序路径"}
                runner.completed += 1
                runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                        "status": "error", "result": result})
                await runner._emit({"type": "stepError", "stepId": step_id,
                                    "nodeId": instr.get("nodeId"), "error": result["error"]})
                return False
            app_label = exe
        else:
            app_info = _APP_MAP.get(app_key, {})
            exe = app_info.get("cmd", "")
            app_label = app_info.get("label", app_key)
            if not exe:
                result = {"error": f"未知软件: {app_key}"}
                runner.completed += 1
                runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                        "status": "error", "result": result})
                await runner._emit({"type": "stepError", "stepId": step_id,
                                    "nodeId": instr.get("nodeId"), "error": result["error"]})
                return False

        if os.name != "nt" and app_key != "__custom__":
            result = {"error": "当前系统非 Windows，不支持打开 Windows 自带软件",
                      "hint": "请使用「自定义程序」指定系统对应的程序路径"}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False

        try:
            cmd_line = [exe]
            if arguments:
                cmd_line.append(arguments)
            proc = subprocess.Popen(cmd_line, shell=True)

            # 等窗口出现后尝试获取句柄
            hwnd = None
            if os.name == "nt" and result_var:
                await asyncio.sleep(0.5)
                from ._win32 import find_window_by_title_fuzzy
                matches = find_window_by_title_fuzzy(app_label)
                if matches:
                    hwnd = matches[0]["hwnd"]
                    runner.vars[result_var] = hwnd

            result = {
                "launched": True,
                "app": app_label,
                "pid": proc.pid,
                "hwnd": hwnd,
                "log": f"已启动: {app_label}" + (f" (hwnd={hwnd})" if hwnd else ""),
            }
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "success", "result": result})
            await runner._emit({"type": "stepComplete", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "result": result})
            return True
        except Exception as e:
            result = {"error": f"启动失败: {e}", "app": app_label}
            runner.completed += 1
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                    "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return False
