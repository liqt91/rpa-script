"""HTTP 请求 + 表格操作 — httpRequest, writeTableRow, readTableCell, writeTableCell, getTableRowCount"""
from ..registry import register_handler, Param
from ..utils import resolve_vars
import json, asyncio, logging

logger = logging.getLogger(__name__)

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
