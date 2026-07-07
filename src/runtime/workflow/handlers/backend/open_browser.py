"""打开浏览器 — openBrowser"""
from ..registry import register_handler, Param


@register_handler(type="openBrowser", label="打开浏览器", category="浏览器", runtime="backend",
    icon="fa-chrome", icon_color="text-blue-500", bg_color="bg-blue-50",
    category_order=1, command_order=10,
    description="启动浏览器并加载RPA扩展")
class OpenBrowserHandler:
    params = [
        Param("browserType", "浏览器", "select",
              options=[{"label": "Chrome", "value": "chrome"}, {"label": "Edge", "value": "edge"}],
              default="chrome"),
        Param("windowState", "窗口状态", "select",
              options=[{"label": "普通", "value": "normal"}, {"label": "最大化", "value": "maximized"}, {"label": "最小化", "value": "minimized"}],
              default="normal", group="advanced"),
        Param("windowVar", "窗口变量", "varName", default="browser1", group="input"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from src.repo.browser_utils import is_browser_running, launch_browser_with_extension
        import asyncio, logging
        logger = logging.getLogger(__name__)
        extra = instr.get("extra") or {}
        browser_type = extra.get("browserType", "chrome")
        url = extra.get("url") or "about:blank"
        state = extra.get("windowState", "normal")

        if not is_browser_running(browser_type):
            logger.info(f"[{browser_type}] 启动浏览器...")
            if not launch_browser_with_extension(browser_type):
                raise RuntimeError(f"无法启动 {browser_type}")

        from src.runtime.workflow.extension_runner import wait_for_extension_connection, ext_manager, DEFAULT_STEP_TIMEOUT
        runner.client_id = await wait_for_extension_connection(browser_type, ext_manager, timeout=10.0)
        if not runner._run_started_sent:
            runner._run_started_sent = True
            await ext_manager.send_to(runner.client_id, "runStarted", {"runId": runner.run_id})

        result = await runner._send_and_wait(step_id, instr, timeout=DEFAULT_STEP_TIMEOUT)

        save_to = extra.get("windowVar") or extra.get("varName") or extra.get("saveToVar")
        if save_to and isinstance(result, dict):
            runner.vars[save_to] = {"windowId": result.get("windowId"), "tabId": result.get("tabId")}

        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "success",
            "result": {"openBrowser": browser_type, "clientId": runner.client_id}})
        runner.completed += 1
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"),
            "result": {"openBrowser": browser_type, "clientId": runner.client_id}})
        return True
