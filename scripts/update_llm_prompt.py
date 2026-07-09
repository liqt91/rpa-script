import sqlite3
import os
import json

NEW_PROMPT = """你是一名 RPA 开发专家。请根据下面的指令 JSON 定义，生成一个后端 Python handler 实现。

项目中的 handler 注册和运行方式如下，请严格遵循：

```python
from ..registry import register_handler, Param

@register_handler(
    type="{{type}}",
    label="{{label}}",
    category="{{category}}",
    runtime="backend",
    icon="fa-circle",
    icon_color="text-gray-500",
    bg_color="bg-gray-50",
)
class {{ClassName}}Handler:
    params = [
        # 每个 Param(name, label, type, required=False, default=None, group="主属性", options=None)
        # type 可选：str-input, str-textarea, str-var, str-dropdown, str-element, int-number, bool-check, list-input, dict-input, any-expr, any-input
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        # 读取参数：value = extra.get("paramName", default)

        # 执行业务逻辑...

        # 成功后必须更新 runner 状态
        runner.completed += 1
        runner.results.append({
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "status": "success",
            "result": {"{{type}}": value_or_summary},
        })
        await runner._emit({
            "type": "stepComplete",
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "result": {"{{type}}": value_or_summary},
        })
        return True
```

可用上下文：
- runner.vars: dict，可读/写流程变量
- runner.results: list，已完成的步骤结果
- runner._emit(dict): 发送步骤事件
- instr.get("nodeId"): 当前节点 ID
- instr.get("extra"): dict，用户填写的参数值
- 如需浏览器通信，使用 await runner._send_and_wait(step_id, instr, timeout=10.0)

要求：
1. 使用 `from ..registry import register_handler, Param` 注册，不要使用虚构模块。
2. `@register_handler` 的 type、label、category 必须和 JSON 定义一致。
3. `class` 名使用大驼峰（如 OpenBrowserHandler）。
4. `params` 列表必须与 JSON 定义中的 params 完全一致（name、label、type、required、default、options）。
5. `execute` 必须是 `@staticmethod async def execute(runner, cmd_type, step_id, instr)`。
6. 从 `instr.get("extra")` 读取参数，不要用 instr.get("paramName") 直接读。
7. 代码只包含类定义和必要的 import，不要输出 markdown 代码块标记，不要额外说明文字。
8. 业务逻辑不要写占位代码，要根据指令用途写出真实可执行的逻辑。

JSON 定义：
{{definition}}
"""

DEFAULT_SCENARIOS = [
    {
        "id": "command_code_gen",
        "name": "指令代码生成",
        "prompt": NEW_PROMPT,
        "enabled": True,
    }
]


def update_prompt(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("UPDATE ai_llm_configs SET scenarios = ?",
                (json.dumps(DEFAULT_SCENARIOS, ensure_ascii=False),))
    conn.commit()
    print(f"Updated {cur.rowcount} row(s)")
    conn.close()


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.expandvars(
        r"C:\Users\Administrator\AppData\Roaming\RPA Script\data.db")
    update_prompt(path)
