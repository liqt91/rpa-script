"""HTTP 请求 + 表格操作 — httpRequest, writeTableRow, readTableCell, writeTableCell, getTableRowCount"""
from ..registry import register_handler, Param
from ..utils import resolve_vars
import json, asyncio, logging

logger = logging.getLogger(__name__)

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
