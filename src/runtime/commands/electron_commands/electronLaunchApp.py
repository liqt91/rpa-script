"""启动 Electron 应用 — electronLaunchApp"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value, clean_var_ref


@register_handler(
    cmd="electronLaunchApp", label="启动 Electron 应用",
    category="Electron 应用", runtime="backend",
    icon="fa-window-restore", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="启动 Electron 应用（如咚咚），Playwright/CDP 驱动，返回页面列表",
    category_order=55, command_order=1,
    summary_tpl="{exe}",
)
class ElectronLaunchHandler:
    params = [
        Param("exe", "程序路径", "string", required=True,
              placeholder="如 D:\\apps\\咚咚.exe，支持 {{变量}}"),
        Param("args", "启动参数", "string", default="",
              placeholder="空格分隔，如 --debug（CDP 端口由系统自动分配）"),
        Param("resultVar", "结果存入变量", "str-var", default="",
              placeholder="页面列表等结果存入此变量"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from src.runtime.workflow.electron_manager import electron_manager
        from ._utils import emit_error

        extra = instr.get("extra", {})
        exe = convert_value(extra.get("exe", ""), "string", runner.vars)
        args_str = convert_value(extra.get("args", ""), "string", runner.vars)
        result_var = clean_var_ref(extra.get("resultVar", ""))

        if not exe:
            return emit_error(runner, step_id, instr, "程序路径为空")

        args = [a for a in args_str.split() if a.strip()] if args_str else None
        result = await electron_manager.launch(exe, args)
        if result.get("error"):
            return emit_error(runner, step_id, instr, result["error"])

        if result_var:
            runner.vars[result_var] = result

        result["log"] = f"已启动: {exe}（{len(result.get('pages', []))} 个页面）"
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
