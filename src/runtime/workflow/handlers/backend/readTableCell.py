"""HTTP 请求 + 表格操作 — httpRequest, writeTableRow, readTableCell, writeTableCell, getTableRowCount"""
from ..registry import register_handler, Param
from ..utils import resolve_vars, clean_var_ref
import json, asyncio, logging

logger = logging.getLogger(__name__)

@register_handler(type="readTableCell", label="读取表格单元格", category="数据表格", runtime="backend",
    icon="fa-table", icon_color="text-orange-500", bg_color="bg-orange-50", category_order=70, command_order=20)
class ReadTableCellHandler:
    params = [
        Param("rowIndex", "行号", "int-number", default=0),
        Param("colIndex", "列号/列名", "str-input", default="0"),
        Param("saveToVar", "保存到变量", "str-var", group="output"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        row_idx = int(extra.get("rowIndex", 0))
        col = extra.get("colIndex", "0")
        save_to = clean_var_ref(extra.get("saveToVar") or extra.get("varName", ""))
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
