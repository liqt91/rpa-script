"""saveJsonFile — 保存JSON文件 (backend)

把变量/表达式的数据写成 JSON 文件（UTF-8，带缩进）。data 支持 {{var}} 引用
（变量由 runner 统一 resolve，列表/字典直接以对象写入）；append 模式下若目标
文件已存在且根为数组，则将新数据并入该数组。
"""
import ast
import json
import os

from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value


def _to_jsonable(data):
    """把 data 归一为可 JSON 序列化的值。

    - 已是 list/dict/int/float/bool/None → 原样返回
    - str → 依次尝试 json.loads（标准 JSON 文本）、ast.literal_eval（runner 把
      {{var}} 列表/字典解析成了 Python repr，如 [{'a': 1}]）；都失败按纯文本返回
    """
    if isinstance(data, (list, dict, int, float, bool)) or data is None:
        return data
    if isinstance(data, str):
        s = data.strip()
        if s and s[0] in "[{\"" or s in ("true", "false", "null"):
            try:
                return json.loads(s)
            except Exception:
                pass
            try:
                val = ast.literal_eval(s)
                if isinstance(val, (list, dict, int, float, bool)):
                    return val
            except Exception:
                pass
        return data
    return str(data)


@register_handler(cmd="saveJsonFile", label="保存JSON文件",
    category="文件处理", runtime="backend",
    icon="fa-file-export", icon_color="text-amber-500",
    bg_color="bg-amber-50",
    description="把变量/表达式的数据写成 JSON 文件（UTF-8，带缩进）；可选追加模式：目标文件已存在且根是数组时，将新数据并入数组",
    category_order=47,
    command_order=20,
    summary_tpl="{data} → {filePath}",
)
class SaveJsonFileHandler:
    params = [
        Param("data", "要保存的数据", "text", required=True),
        Param("filePath", "文件路径", "string", required=True),
        Param("append", "追加到已有数组", "boolean", required=False, default=False),
        Param("resultVar", "保存结果到变量", "str-var", required=False, default=""),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra", {})

        # backend 指令的 extra 不经 runner._resolve_vars（extension_runner.py:1544
        # 只对 extension 指令 resolve），须自行经 convert_value 解析 {{var}}。
        raw = convert_value(extra.get("data", ""), "any-input", runner.vars)
        file_path = str(convert_value(extra.get("filePath", ""), "string", runner.vars)).strip()
        append = extra.get("append") in (True, "true", "True", 1, "1")
        result_var = (extra.get("resultVar") or "").strip()

        if not file_path:
            raise ValueError("saveJsonFile: filePath 为空（必填：输出 JSON 文件的绝对路径）")

        data = _to_jsonable(raw)

        # append 模式：已有文件根为数组时并入
        merged_count = None
        if append and os.path.isfile(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if isinstance(existing, list):
                    if isinstance(data, list):
                        existing.extend(data)
                        merged_count = len(data)
                    else:
                        existing.append(data)
                        merged_count = 1
                    data = existing
            except Exception:
                # 旧文件解析失败：回退为覆盖，不阻断流程
                merged_count = None

        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        payload = json.dumps(data, ensure_ascii=False, indent=2)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(payload)

        item_count = len(data) if isinstance(data, (list, dict)) else 1
        result = {
            "cmd": "saveJsonFile",
            "path": file_path,
            "bytes": len(payload.encode("utf-8")),
            "itemCount": item_count,
            "appended": merged_count,
            "value": file_path,
        }
        if result_var:
            runner.vars[result_var] = {
                "path": file_path,
                "itemCount": item_count,
                "bytes": result["bytes"],
            }

        runner.completed += 1
        runner.results.append({
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "status": "success",
            "result": result,
        })
        await runner._emit({
            "type": "stepComplete",
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "result": result,
        })
        return True
