"""
Update AI prompt scenarios for command handler code generation.

Three command types → three prompts, stored in the ai_llm_configs.scenarios JSON
column so the frontend can select the right prompt per command type.

Usage: python scripts/update_llm_prompt.py [data.db path]
"""

import sqlite3
import os
import json


# ─── Shared context: what the runner provides ──────────────────

_SHARED_CONTEXT = """可用上下文：
- runner.vars: dict，可读/写流程变量
- runner.results: list，已完成的步骤结果
- runner._emit(dict): 发送步骤事件到前端
- runner._send_and_wait(step_id, instr, timeout): 发送消息给浏览器扩展并等待响应
- instr.get("nodeId"): 当前节点 ID
- instr.get("extra"): dict，用户填写的参数值
"""

# ═══════════════════════════════════════════════════════════════
# 1. Backend handler — 本地执行指令 (backend_commands/)
# ═══════════════════════════════════════════════════════════════

BACKEND_PROMPT = """你是一名 RPA 开发专家。请根据下面的指令 JSON 定义，生成一个后端 Python handler 实现。

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
        # Param(name, label, type, required=False, default=None, group="主属性", options=None)
        # type 可选：str-input, str-textarea, str-var, str-dropdown, str-element,
        #           int-number, bool-check, list-input, dict-input, any-expr, any-input
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

""" + _SHARED_CONTEXT + """

要求：
1. 使用 `from ..registry import register_handler, Param` 注册，不要使用虚构模块。
2. `@register_handler` 的 type、label、category 必须和 JSON 定义一致。
3. `class` 名使用大驼峰（如 OpenBrowserHandler、HttpGetHandler）。
4. `params` 列表必须与 JSON 定义中的 params 完全一致（name、label、type、required、default、options、group）。
5. `execute` 必须是 `@staticmethod async def execute(runner, cmd_type, step_id, instr)`。
6. 从 `instr.get("extra")` 读取参数，不要用 instr.get("paramName") 直接读。
7. 代码只包含类定义和必要的 import，不要输出 markdown 代码块标记，不要额外说明文字。
8. 业务逻辑不要写占位代码，要根据指令用途写出真实可执行的逻辑。
9. 如果参数有 output 分组且是 str-var 类型，执行成功后把结果写入 runner.vars。

JSON 定义：
{{definition}}
"""

# ═══════════════════════════════════════════════════════════════
# 2. Extension JS handler — 扩展端执行指令 (extension_commands/)
# ═══════════════════════════════════════════════════════════════

EXTENSION_JS_PROMPT = """你是一名浏览器扩展开发专家。请根据下面的指令 JSON 定义，生成一个 content.js handler 函数。

项目中的 JS handler 注册方式：

```js
// extension/handlers/{{type}}.js

registerHandler('{{type}}', async function handler(args) {
  // args 结构：
  //   args.extra       — 用户填写的参数键值对
  //   args.elements    — 元素选择器映射 { elementName: { selectors: [...] } }
  //   args.vars        — 当前工作流变量（只读引用）
  //   args.stepId      — 当前步骤 ID

  // 解析元素选择器
  // const el = await findElement(args.elements['element_name'], args.extra.scope);
  
  // 执行业务逻辑...

  // 返回值（可选字段）：
  return {
    ok: true,
    // 以下字段根据需要返回：
    // result: { ... },     // 步骤结果数据
    // vars: { ... },       // 要更新的变量（会合并到 runner.vars）
    // windowId, tabId,     // 浏览器窗口信息
  };
});
```

常用工具函数（content.js 中已定义）：
- `findElement(elementDef, scope)` — 根据元素定义查找 DOM 元素
- `resolveSelector(selectors)` — 解析选择器优先级
- `sleep(ms)` — 等待

要求：
1. handler 函数签名必须是 `async function handler(args)`。
2. 从 `args.extra` 读取参数，参数名必须与 JSON 定义一致。
3. 使用 `findElement()` 查找元素，传入 args.elements[elementName]。
4. 代码只包含函数定义 + registerHandler 调用，不要输出 markdown 代码块标记。
5. 业务逻辑不要写占位代码，要根据指令用途写出真实可执行的逻辑。
6. 操作 DOM 时考虑元素可能不可见/不存在的情况。

JSON 定义：
{{definition}}
"""

# ═══════════════════════════════════════════════════════════════
# 3. Control handler — 控制流指令 (control_commands/)
# ═══════════════════════════════════════════════════════════════

CONTROL_PROMPT = """你是一名 RPA 开发专家。请根据下面的指令 JSON 定义，生成一个控制流 Python handler 实现。

控制流指令（容器/分支/结构标记）不直接执行业务逻辑，而是控制工作流的执行路径。
它们通过 emitter 展开为实际的执行步骤。

项目中的 handler 注册方式：

```python
from ..registry import register_handler, Param

@register_handler(
    type="{{type}}",
    label="{{label}}",
    category="{{category}}",
    runtime="control",
    icon="fa-code-branch",
    icon_color="text-gray-500",
    bg_color="bg-gray-50",
    is_container=True,        # 容器指令
    # is_branch=True,         # 分支指令
    # is_structural=True,     # 结构标记（结束标记）
    # closes_with="endXxx",   # 哪个标记闭合此容器
)
class {{ClassName}}Handler:
    params = [
        # Param(name, label, type, required=False, default=None, group="主属性")
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        # 控制流逻辑：计算条件、决定跳转等
        
        # 通知 emitter 展开子节点或跳转
        runner.completed += 1
        return True
```

""" + _SHARED_CONTEXT + """

要求：
1. 使用 `from ..registry import register_handler, Param` 注册。
2. `@register_handler` 必须正确设置 is_container / is_branch / is_structural / closes_with。
3. `class` 名使用大驼峰。
4. `params` 列表与 JSON 定义一致。
5. `execute` 为 `@staticmethod async def execute(runner, cmd_type, step_id, instr)`。
6. 代码只包含类定义和必要的 import，不要输出 markdown 代码块标记。
7. 控制流逻辑要完整可用，不写占位代码。

JSON 定义：
{{definition}}
"""

# ─── Default scenarios ────────────────────────────────────────

DEFAULT_SCENARIOS = [
    {
        "id": "command_backend",
        "name": "后端指令代码生成",
        "description": "生成 backend_commands Python handler，含 execute 实现",
        "prompt": BACKEND_PROMPT,
        "enabled": True,
    },
    {
        "id": "command_extension_js",
        "name": "扩展端 JS 代码生成",
        "description": "生成 extension_commands 的 content.js handler 函数",
        "prompt": EXTENSION_JS_PROMPT,
        "enabled": True,
    },
    {
        "id": "command_control",
        "name": "控制流指令代码生成",
        "description": "生成 control_commands Python handler，含流程控制逻辑",
        "prompt": CONTROL_PROMPT,
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
