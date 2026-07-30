"""Command: 打开浏览器 — launchBrowser

Extension instruction.  The local execute() only does pre-work (launch the
browser process + wait for the extension WebSocket); the runner then dispatches
the instruction to the extension normally, where content.js opens a new tab.
"""
from src.runtime.workflow.handlers.registry import register_handler, Param


@register_handler(cmd="launchBrowser", label="打开浏览器",
    category="浏览器操作", runtime="extension",
    icon="fa-globe", icon_color="text-blue-500",
    bg_color="bg-blue-50",
    description="启动浏览器并加载RPA扩展",
    category_order=10,
    command_order=10,
)
class LaunchBrowserHandler:
    params = [
        Param("browserType", "浏览器", "select", default="chrome", options=[{"label": "Chrome", "value": "chrome"}, {"label": "Edge", "value": "edge"}]),
        Param("url", "启动后打开网址", "string", default="about:blank", placeholder="留空则打开 about:blank"),
        Param("windowState", "窗口状态", "select", default="normal", options=[{"label": "普通", "value": "normal"}, {"label": "最大化", "value": "maximized"}, {"label": "最小化", "value": "minimized"}], group="advanced"),
        Param("windowVar", "保存窗口对象到", "str-var", default="browser1", group="output"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        """Pre-work only: launch browser process + wait for extension connection.

        The runner continues to dispatch the instruction to the extension
        after this returns, so we must NOT call _send_and_wait / _emit /
        append results / increment completed here.
        """
        from src.repo.browser_utils import is_browser_running, launch_browser_with_extension
        import logging
        logger = logging.getLogger(__name__)
        extra = instr.get("extra") or {}
        browser_type = extra.get("browserType", "chrome")
        logger.info(f"[launchBrowser] browserType from extra: {browser_type!r}, full extra: {extra!r}")
        print(f"[DEBUG launchBrowser] browserType={browser_type!r}, extra={extra!r}")

        if not is_browser_running(browser_type):
            logger.info(f"[{browser_type}] 启动浏览器...")
            if not launch_browser_with_extension(browser_type):
                raise RuntimeError(f"无法启动 {browser_type}")

        from src.runtime.workflow.extension_runner import wait_for_extension_connection, ext_manager
        runner.client_id = await wait_for_extension_connection(browser_type, ext_manager, timeout=10.0)
        if not runner._run_started_sent:
            runner._run_started_sent = True
            await ext_manager.send_to(runner.client_id, "runStarted", {"runId": runner.run_id})

        return True