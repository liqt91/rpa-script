"""HTTP 请求 + 表格操作 — httpRequest, writeTableRow, readTableCell, writeTableCell, getTableRowCount"""
from ..registry import register_handler, Param
from ..utils import resolve_vars
import json, asyncio, logging

logger = logging.getLogger(__name__)

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
