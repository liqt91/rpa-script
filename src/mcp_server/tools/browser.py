"""P5 浏览器实时代理工具（ADR-0011）。

通用入口 browser_exec 透传任意扩展指令（指令清单与字段见 list_browser_commands），
另提供常用指令的便捷封装。与运行中的工作流互斥（409），allow_during_run 可强制。
"""

from fastmcp import FastMCP

from ..client import get_client


async def _exec(
    type: str,
    locator: str = "",
    selector_family: str = "css",
    action: str | None = None,
    extra: dict | None = None,
    timeout: float = 30.0,
    client_id: str | None = None,
    allow_during_run: bool = False,
) -> dict:
    payload = {
        "type": type,
        "locator": locator,
        "selectorFamily": selector_family,
        "action": action,
        "extra": extra or {},
        "timeout": timeout,
        "clientId": client_id,
        "allowDuringRun": allow_during_run,
    }
    return await get_client().post("/api/extension/exec", json=payload, auth=False)


def register(mcp: FastMCP) -> None:
    @mcp.tool(tags={"browser"})
    async def list_browser_commands() -> dict:
        """列出可在浏览器扩展侧执行的指令目录（type/label/字段定义）。"""
        return await get_client().get("/api/extension/commands", auth=False)

    @mcp.tool(tags={"browser"})
    async def browser_exec(
        type: str,
        locator: str = "",
        selector_family: str = "css",
        action: str | None = None,
        extra: dict | None = None,
        timeout: float = 30.0,
        client_id: str | None = None,
        allow_during_run: bool = False,
    ) -> dict:
        """在已连接的浏览器扩展上执行单条指令并等待结果。

        type: 指令类型（如 clickElement/getText/navigate/getCurrentUrl/
        checkElementExists/inputElement，完整清单见 list_browser_commands）。
        locator/selector_family: 元素定位；extra: 指令参数（如 navigate 的
        {"url": ...}、inputElement 的 {"text": ...}）。
        有工作流正在运行时返回 409，allow_during_run=true 可强制。
        """
        return await _exec(
            type,
            locator=locator,
            selector_family=selector_family,
            action=action,
            extra=extra,
            timeout=timeout,
            client_id=client_id,
            allow_during_run=allow_during_run,
        )

    @mcp.tool(tags={"browser"})
    async def browser_navigate(url: str, timeout: float = 30.0) -> dict:
        """当前标签页导航到指定 URL。"""
        return await _exec("navigate", extra={"url": url}, timeout=timeout)

    @mcp.tool(tags={"browser"})
    async def browser_current_url() -> dict:
        """获取当前标签页 URL。"""
        return await _exec("getCurrentUrl")

    @mcp.tool(tags={"browser"})
    async def browser_click(locator: str, selector_family: str = "css") -> dict:
        """点击元素。locator 为 CSS 选择器或 XPath（selector_family=xpath）。"""
        return await _exec("clickElement", locator=locator, selector_family=selector_family)

    @mcp.tool(tags={"browser"})
    async def browser_get_text(locator: str, selector_family: str = "css") -> dict:
        """获取元素文本内容。"""
        return await _exec("getText", locator=locator, selector_family=selector_family)

    @mcp.tool(tags={"browser"})
    async def browser_input(
        locator: str,
        text: str,
        selector_family: str = "css",
        press_enter: bool = False,
        clear_first: bool = True,
    ) -> dict:
        """向输入框输入文本（默认模拟键盘；clear_first 先清空）。"""
        extra = {"text": text, "pressEnter": press_enter, "clearFirst": clear_first}
        return await _exec(
            "inputElement", locator=locator, selector_family=selector_family, extra=extra
        )

    @mcp.tool(tags={"browser"})
    async def browser_element_exists(
        locator: str, selector_family: str = "css", visible_only: bool = True
    ) -> dict:
        """检查元素是否存在（visible_only=True 时还要求可见）。"""
        return await _exec(
            "checkElementExists",
            locator=locator,
            selector_family=selector_family,
            extra={"visibleOnly": visible_only},
        )
