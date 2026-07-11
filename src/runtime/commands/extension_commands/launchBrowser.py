"""打开浏览器 — launchBrowser (extension)"""
from src.runtime.workflow.handlers.registry import register_handler, Param


@register_handler(
    cmd="launchBrowser", label="打开浏览器", category="浏览器", runtime="extension",
    icon="fa-chrome", icon_color="text-blue-500", bg_color="bg-blue-50",
    category_order=10, command_order=10,
    description="启动浏览器并加载RPA扩展")
class LaunchBrowserHandler:
    params = [
        Param("browserType", "浏览器", "str-dropdown",
              options=[{"label": "Chrome", "value": "chrome"}, {"label": "Edge", "value": "edge"}],
              default="chrome"),
        Param("url", "启动后打开网址", "str-input", placeholder="留空则打开 about:blank"),
        Param("windowState", "窗口状态", "str-dropdown",
              options=[{"label": "普通", "value": "normal"}, {"label": "最大化", "value": "maximized"}, {"label": "最小化", "value": "minimized"}],
              default="normal", group="advanced"),
        Param("windowVar", "保存窗口对象到", "str-var", default="browser1", group="输出变量"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        """前置工作：启动浏览器 + 建立扩展 WebSocket 连接。
        
        窗口创建由 Runner 将指令发给扩展端的 background handler 完成。
        Runner 的 extension dispatch 路径负责发送指令、等待结果、写入输出变量。
        """
        from src.repo.browser_utils import is_browser_running, launch_browser_with_extension
        import logging
        logger = logging.getLogger(__name__)
        extra = instr.get("extra") or {}
        browser_type = extra.get("browserType", "chrome")

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
