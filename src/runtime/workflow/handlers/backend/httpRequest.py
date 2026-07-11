"""HTTP 请求 + 表格操作 — httpRequest, writeTableRow, readTableCell, writeTableCell, getTableRowCount"""
from ..registry import register_handler, Param
from ..utils import resolve_vars, clean_var_ref
import json, asyncio, logging

logger = logging.getLogger(__name__)

@register_handler(cmd="httpRequest", label="HTTP请求", category="高级", runtime="backend",
    icon="fa-network-wired", icon_color="text-gray-700", bg_color="bg-gray-100", category_order=90, command_order=30)
class HttpRequestHandler:
    params = [
        Param("url", "请求地址", "str-input", required=True, placeholder="https://..."),
        Param("method", "请求方法", "str-dropdown",
              options=["GET", "POST", "PUT", "DELETE", "PATCH"], default="GET"),
        Param("headers", "请求头(JSON)", "any-expr", default="{}", group="advanced"),
        Param("body", "请求体", "any-expr", group="advanced"),
        Param("saveToVar", "保存结果到", "str-var", group="output"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        import aiohttp
        extra = instr.get("extra") or {}
        method = extra.get("method", "GET")
        url = resolve_vars(extra.get("url", ""), runner.vars)
        timeout = extra.get("timeout", 30)
        save_to = clean_var_ref(extra.get("saveToVar") or extra.get("varName", ""))

        headers = {}
        headers_str = extra.get("headers", "{}")
        try:
            headers = json.loads(headers_str) if isinstance(headers_str, str) else headers_str
        except Exception:
            pass

        body = extra.get("body", "")
        try:
            timeout_sec = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=timeout_sec) as session:
                kwargs = {"headers": headers}
                if body and method in ("POST", "PUT", "PATCH"):
                    try:
                        kwargs["json"] = json.loads(body) if isinstance(body, str) else body
                    except Exception:
                        kwargs["data"] = body
                async with session.request(method, url, **kwargs) as resp:
                    text = await resp.text()
                    try:
                        result = json.loads(text)
                    except Exception:
                        result = {"status": resp.status, "body": text[:2000]}
        except Exception as e:
            logger.error(f"[httpRequest] 请求失败: {e}")
            result = {"error": str(e)}

        if save_to:
            runner.vars[save_to] = result
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "success",
            "result": {"httpRequest": str(result)[:200]}})
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"),
            "result": {"httpRequest": True}})
        return True
