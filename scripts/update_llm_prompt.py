"""
Update AI prompt scenarios for command handler code review.

Three command types -> three review prompts, stored in the ai_llm_configs.scenarios
JSON column so the frontend can select the right prompt per command type.

Usage: python scripts/update_llm_prompt.py [data.db path]

Note: The prompt template variables {{source_code}}, {{definition_json}}, {{context}}
are replaced by the backend at runtime (see other_routers.py).
"""

import sqlite3
import os
import json


BACKEND_PROMPT = """
你是 RPA 后端代码审查专家。请审查下面的 Python backend handler 代码，逐项检查并返回 JSON 问题清单。

=== Handler 源码 ===
```python
{{source_code}}
```

=== JSON 定义 ===
{{definition_json}}

=== 检查清单 ===
1. @register_handler 的 cmd/label/category/runtime 是否与 JSON 定义一致
2. params 列表是否与 JSON 定义完全匹配（name、type、default、group、valueType）
3. execute() 签名：@staticmethod async def execute(runner, cmd_type, step_id, instr)
4. 参数是否从 instr.get("extra") 读取（不是 instr.get("paramName")）
5. runner.completed 是否递增
6. runner.results 是否 append 了 result_summary（result_summary 必须是 dict）
7. runner._emit 是否正确发送 stepComplete
8. 输出变量是否写入了 runner.vars[键名]
9. 是否编造了不存在的模块或 API
10. 异常处理是否合理（raise RuntimeError 还是 try-except）

=== 返回格式 ===
只返回 JSON 数组：
[
  {"level": "error|warning|info", "line": 行号或null, "check": "检查项名称", "message": "具体问题和建议"}
]
没有问题时返回空数组 []
"""

EXTENSION_JS_PROMPT = """
你是 Chrome 扩展代码审查专家。请审查下面的 JS handler 代码，逐项检查并返回 JSON 问题清单。

=== Handler 源码 ===
```javascript
{{source_code}}
```

=== JSON 定义 ===
{{definition_json}}

=== 检查清单 ===
1. 注册方式是否正确（registerHandler for DOM, registerBackgroundHandler for background）
2. 参数是否从 step.extra 读取，参数名是否与 JSON 定义匹配
3. 返回值是否符合规范：{ ok: true/false, result?: ..., error?: ..., vars?: ... }
4. DOM 操作前是否检查了元素存在性（findElement 返回值检查）
5. chrome API 调用是否有错误处理
6. 是否考虑了 extension context invalidation（Service Worker 生命周期）
7. background handler 是否设置了 agent.workWindowId / agent.workTabId
8. 是否注入了 content script（agent._injectContentScript）
9. 异步操作是否正确使用 await
10. 是否有硬编码的 URL 或 magic string

=== 返回格式 ===
只返回 JSON 数组：
[
  {"level": "error|warning|info", "line": 行号或null, "check": "检查项名称", "message": "具体问题和建议"}
]
没有问题时返回空数组 []
"""

CONTROL_PROMPT = """
你是 RPA 工作流引擎审查专家。请审查下面的 control handler 代码，逐项检查并返回 JSON 问题清单。

=== Handler 源码 ===
```python
{{source_code}}
```

=== JSON 定义 ===
{{definition_json}}

=== 检查清单 ===
1. @register_handler 的 cmd/label/category/runtime 是否与 JSON 定义一致
2. is_container / is_branch / is_structural / closes_with 是否正确声明
3. execute() 签名：@staticmethod async def execute(runner, cmd_type, step_id, instr)
4. 控制流逻辑是否正确处理嵌套场景
5. 变量作用域是否正确（runner.vars vs runner.get_parent_vars()）
6. 条件判断逻辑是否有边界情况遗漏
7. 是否正确处理了空列表/空值/null
8. 结构性指令是否只做标记不执行业务逻辑
9. 异常处理是否合理
10. 是否与 JSON 定义的 closesWith 匹配

=== 返回格式 ===
只返回 JSON 数组：
[
  {"level": "error|warning|info", "line": 行号或null, "check": "检查项名称", "message": "具体问题和建议"}
]
没有问题时返回空数组 []
"""

REVIEW_PROMPT = """
你是 RPA 代码审查专家。请审查下面的 handler 代码，逐项检查以下规则，返回 JSON 格式的问题清单。

=== JSON 定义 ===
{{definition_json}}

=== Handler 源码 ===
{{source_code}}

=== value_types.json ===
{{value_types_json}}

=== 检查清单 ===
1. @register_handler 的 cmd/label/category/runtime 是否与 JSON 定义一致
2. params 列表是否与 JSON 定义完全匹配（name、type、default、group）
3. execute() 签名是否正确：@staticmethod async def execute(runner, cmd_type, step_id, instr)
4. 参数是否从 instr.get("extra") 读取（不是 instr.get("paramName")）
5. group="output" 的参数是否正确跳过预执行解析
6. extension 指令的 execute() 是否没有调用 _send_and_wait（由 Runner 负责）
7. backend 指令的 execute() 是否完成全部工作且有结果上报
8. result_summary 是否是 dict
9. 是否编造了不存在的模块或 API
10. 输出变量是否写入了 runner.vars[键名]

=== 返回格式 ===
只返回 JSON 数组，不要任何其他文字：
[
  {
    "level": "error|warning|info",
    "line": 行号或null,
    "check": "检查项名称",
    "message": "具体问题和建议"
  }
]

没有问题时返回空数组 []
"""

DEFAULT_SCENARIOS = [
    {
        "id": "command_backend",
        "name": "后端指令审查",
        "description": "审查 backend Python handler 代码质量",
        "prompt": BACKEND_PROMPT,
        "enabled": True,
    },
    {
        "id": "command_extension_js",
        "name": "扩展端 JS 审查",
        "description": "审查 extension JS handler 代码质量",
        "prompt": EXTENSION_JS_PROMPT,
        "enabled": True,
    },
    {
        "id": "command_control",
        "name": "控制流指令审查",
        "description": "审查 control Python handler 代码质量",
        "prompt": CONTROL_PROMPT,
        "enabled": True,
    },
    {
        "id": "command_review",
        "name": "通用 handler 审查",
        "description": "通用审查（含 value_types.json 校验）",
        "prompt": REVIEW_PROMPT,
        "enabled": True,
    },
]


def update_prompt(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "UPDATE ai_llm_configs SET scenarios = ?",
        (json.dumps(DEFAULT_SCENARIOS, ensure_ascii=False),),
    )
    conn.commit()
    updated = cur.rowcount
    print(f"Updated {updated} row(s) in ai_llm_configs")
    print(f"  Scenarios: {[s['id'] for s in DEFAULT_SCENARIOS]}")
    conn.close()


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.expandvars(
        r"C:\Users\Administrator\AppData\Roaming\RPA Script\data.db")
    update_prompt(path)
