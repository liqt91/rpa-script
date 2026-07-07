"""HTTP 请求 + 表格操作 — httpRequest, writeTableRow, readTableCell, writeTableCell, getTableRowCount"""
from ..registry import register_handler, Param
from ..utils import resolve_vars
import json, asyncio, logging

logger = logging.getLogger(__name__)


@register_handler(type="httpRequest", label="HTTP请求", category="高级", runtime="backend",
    icon="fa-network-wired", icon_color="text-gray-700", bg_color="bg-gray-100", category_order=90, command_order=30)
class HttpRequestHandler:
    params = [
        Param("url", "请求地址", "text", required=True, placeholder="https://..."),
        Param("method", "请求方法", "select",
              options=["GET", "POST", "PUT", "DELETE", "PATCH"], default="GET"),
        Param("headers", "请求头(JSON)", "code", default="{}", group="advanced"),
        Param("body", "请求体", "code", group="advanced"),
        Param("saveToVar", "保存结果到", "varName", group="output"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        import aiohttp
        extra = instr.get("extra") or {}
        method = extra.get("method", "GET")
        url = resolve_vars(extra.get("url", ""), runner.vars)
        timeout = extra.get("timeout", 30)
        save_to = extra.get("saveToVar") or extra.get("varName", "")

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


@register_handler(type="writeTableRow", label="写入数据行", category="数据表格", runtime="backend",
    icon="fa-table", icon_color="text-orange-500", bg_color="bg-orange-50", category_order=70, command_order=10)
class WriteTableRowHandler:
    params = [
        Param("rowData", "行数据", "text", required=True, placeholder="[${colA}, ${colB}]"),
        Param("writeMode", "写入模式", "select",
              options=[{"label": "追加", "value": "append"}, {"label": "覆盖指定行", "value": "overwrite"}],
              default="append"),
        Param("rowIndex", "行号", "number", default=0),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        row_data = resolve_vars(extra.get("rowData", "[]"), runner.vars)
        write_mode = extra.get("writeMode", "append")
        row_index = int(extra.get("rowIndex", 0))

        if isinstance(row_data, str):
            try:
                row_data = json.loads(row_data)
            except Exception:
                row_data = [row_data]

        table = runner._ensure_table_data()
        rows = table.setdefault("rows", [])
        if write_mode == "append":
            row_dict = {}
            columns = table.get("columns", [])
            for i, val in enumerate(row_data if isinstance(row_data, list) else [row_data]):
                col_name = columns[i]["name"] if i < len(columns) else chr(65 + i)
                row_dict[col_name] = val
            rows.append(row_dict)
        else:
            row_dict = {}
            columns = table.get("columns", [])
            for i, val in enumerate(row_data if isinstance(row_data, list) else [row_data]):
                col_name = columns[i]["name"] if i < len(columns) else chr(65 + i)
                row_dict[col_name] = val
            while len(rows) <= row_index:
                rows.append({})
            rows[row_index] = row_dict

        runner.completed += 1
        await runner._emit({"type": "stepComplete", "stepId": step_id, "nodeId": instr.get("nodeId"),
            "result": {"writeTableRow": True}})
        return True


@register_handler(type="readTableCell", label="读取表格单元格", category="数据表格", runtime="backend",
    icon="fa-table", icon_color="text-orange-500", bg_color="bg-orange-50", category_order=70, command_order=20)
class ReadTableCellHandler:
    params = [
        Param("rowIndex", "行号", "number", default=0),
        Param("colIndex", "列号/列名", "text", default="0"),
        Param("saveToVar", "保存到变量", "varName", group="output"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        row_idx = int(extra.get("rowIndex", 0))
        col = extra.get("colIndex", "0")
        save_to = extra.get("saveToVar") or extra.get("varName", "")
        table = runner._ensure_table_data()
        rows = table.get("rows", [])
        columns = table.get("columns", [])

        if not isinstance(col, int):
            try:
                col = int(col)
            except ValueError:
                for ci, cdef in enumerate(columns):
                    if cdef["name"] == col:
                        col = ci
                        break

        val = None
        if row_idx < len(rows) and isinstance(col, int) and col < len(columns):
            val = rows[row_idx].get(columns[col]["name"])

        if save_to:
            runner.vars[save_to] = val
        runner.completed += 1
        return True


@register_handler(type="writeTableCell", label="写入表格单元格", category="数据表格", runtime="backend",
    icon="fa-table", icon_color="text-orange-500", bg_color="bg-orange-50", category_order=70, command_order=30)
class WriteTableCellHandler:
    params = [
        Param("rowIndex", "行号", "number", required=True),
        Param("colIndex", "列号/列名", "text", required=True),
        Param("value", "值", "text"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        row_idx = int(extra.get("rowIndex", 0))
        col = extra.get("colIndex", "0")
        value = resolve_vars(str(extra.get("value", "")), runner.vars)
        table = runner._ensure_table_data()
        rows = table.setdefault("rows", [])
        columns = table.setdefault("columns", [])

        if not isinstance(col, int):
            try:
                col = int(col)
            except ValueError:
                for ci, cdef in enumerate(columns):
                    if cdef["name"] == col:
                        col = ci
                        break

        while len(rows) <= row_idx:
            rows.append({})

        if isinstance(col, int):
            if col < len(columns):
                rows[row_idx][columns[col]["name"]] = value
            else:
                col_name = chr(65 + col) if col < 26 else f"Col{col}"
                rows[row_idx][col_name] = value

        runner.completed += 1
        return True


@register_handler(type="getTableRowCount", label="获取表格行数", category="数据表格", runtime="backend",
    icon="fa-table", icon_color="text-orange-500", bg_color="bg-orange-50", category_order=70, command_order=40)
class GetTableRowCountHandler:
    params = [
        Param("saveToVar", "保存到变量", "varName", group="output"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        save_to = extra.get("saveToVar") or extra.get("varName", "")
        table = getattr(runner, '_table_data', {})
        count = len(table.get("rows", []))
        if save_to:
            runner.vars[save_to] = count
        runner.completed += 1
        return True
