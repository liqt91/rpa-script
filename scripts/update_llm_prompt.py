"""
Update AI prompt scenarios for command handler code generation.

Three command types → three prompts, stored in the ai_llm_configs.scenarios JSON
column so the frontend can select the right prompt per command type.

Usage: python scripts/update_llm_prompt.py [data.db path]
"""

import sqlite3
import os
import json


# ─── Iron rules (shared across all three scenarios) ─────────────

_IRON_RULES = """## 铁律（违反则代码无法运行）

1. 参数名必须与 JSON params[].name 完全一致，一字不差。
2. 从 `instr.get("extra")` 读取参数，不是 `instr.get("paramName")`。
3. 不编造不存在的模块或 API。不确定的工具说"需确认"，不要猜。
4. 代码只包含类定义和必要的 import，不要输出 markdown 代码块标记。
5. 结果汇总变量必须是 dict。
6. `class` 名使用大驼峰（如 OpenBrowserHandler、HttpGetHandler）。
7. 不写 pass 或注释占位——必须写出真实可执行的逻辑。
"""

# ─── Shared runner context ──────────────────────────────────────

_RUNNER_CONTEXT = """## Runner 可用上下文

- `runner.vars`: dict — 可读/写流程变量
- `runner.results`: list — 已完成的步骤结果
- `runner._emit(dict)`: 发送步骤事件到前端
- `instr.get("nodeId")`: 当前节点 ID
- `instr.get("extra")`: dict — 用户填写的参数值
"""

# ═══════════════════════════════════════════════════════════════
# 1. Backend handler — 本地执行指令 (backend_commands/)
# ═══════════════════════════════════════════════════════════════

BACKEND_PROMPT = """你是一名 RPA 开发专家。根据下面的 JSON 定义生成 Python handler。

## Handler 注册模板（不可偏离）

```python
from src.runtime.workflow.handlers.registry import register_handler, Param

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

        # ── 业务逻辑 ──

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

""" + _RUNNER_CONTEXT + """

## 项目 API 清单（按需选用，不要编造）

### 浏览器操作
```python
from src.repo.browser_utils import is_browser_running, launch_browser_with_extension
# is_browser_running(browser_type: str) -> bool
# launch_browser_with_extension(browser_type: str) -> bool  # 自动加载扩展启动

from src.runtime.workflow.extension_runner import (
    wait_for_extension_connection, ext_manager, DEFAULT_STEP_TIMEOUT
)
# client_id = await wait_for_extension_connection(browser_type, ext_manager, timeout=10.0)
# 连接建立后必须设置: runner.client_id = client_id
# await ext_manager.send_to(runner.client_id, "runStarted", {"runId": runner.run_id})
# 向扩展端发送消息: result = await runner._send_and_wait(step_id, instr, timeout=10.0)
```

### 工具函数
```python
from src.runtime.workflow.handlers.utils import clean_var_ref, convert_value
# clean_var_ref("${var}") -> "var"  # 去掉 ${} 包装
# convert_value(value, type, runner.vars) -> 转换后的值
```

### HTTP 请求
```python
# 项目已安装 httpx，可直接 import
import httpx
async with httpx.AsyncClient() as client:
    resp = await client.get(url, headers={...})
    data = resp.json()
```

## 参数读取规范

所有参数从 `instr.get("extra")` 读取。参数名与 JSON params[].name 完全一致。
```python
extra = instr.get("extra") or {}
var_name = extra.get("varName", "default_value")
```

## 输出变量规范

若 param 的 `group` 为 `"output"` 且 `type` 为 `"str-var"`，其值代表"写入 runner.vars 的键名"。
执行成功后将结果写入 `runner.vars[键名]`。
窗口变量须写入 `{"windowId": ..., "tabId": ...}` 格式。

## 参考实现

项目中的 launchBrowser.py（extension 前置工作）和 setVar.py（变量操作）。
遵循同样的 import 方式、参数读取和结果上报模式。

""" + _IRON_RULES + """

JSON 定义：
{{definition}}
"""

# ═══════════════════════════════════════════════════════════════
# 2. Extension JS handler — 扩展端执行指令 (extension_commands/)
# ═══════════════════════════════════════════════════════════════

EXTENSION_JS_PROMPT = """你是一名浏览器扩展开发专家。根据下面的 JSON 定义生成 content.js handler。

## Handler 注册模板

```js
// extension/dom_handlers/{{type}}.js

registerHandler('{{type}}', async function handler(args) {
  // args 结构：
  //   args.extra       — 用户填写的参数，{paramName: value}
  //   args.elements    — 元素选择器 {elementName: {selectors: [...]}}
  //   args.vars        — 当前工作流变量（只读）
  //   args.stepId      — 当前步骤 ID

  // ── 业务逻辑 ──

  return {
    ok: true,
    result: { ... },   // 步骤结果（可选）
    vars: { ... },     // 要更新的变量（可选，合并到 runner.vars）
  };
});
```

## content.js 可用工具（已定义，可直接调用）

- `findElement(elementDef, scope, visibilityMode)` → DOM Element | null
  elementDef: args.elements[elementName]
  scope: "local"（当前循环项内）| "global"（全页面）
  visibilityMode: "visible"（仅可见）| "any"（所有）
- `resolveSelector(selectors)` → 最佳选择器字符串
- `sleep(ms)` → Promise

## 参数读取

从 `args.extra` 读取，参数名与 JSON params[].name 完全一致：
```js
const elementName = args.extra.element_name;
const text = args.extra.text || '';
```

## 返回值规范

```js
return { ok: true };                          // 最简
return { ok: true, result: {value: 123} };    // 带结果
return { ok: true, vars: {myVar: "hello"} };  // 写变量
return { ok: false, error: "原因" };           // 失败
```

## 参考实现

extension/dom_handlers/clickElement.js 和 waitForElement.js。

## 注意事项

- DOM 操作前检查元素是否存在（findElement 可能返回 null）
- 操作可能不可见元素前先确保可见性或返回友好错误

""" + _IRON_RULES + """

JSON 定义：
{{definition}}
"""

# ═══════════════════════════════════════════════════════════════
# 3. Control handler — 控制流指令 (control_commands/)
# ═══════════════════════════════════════════════════════════════

CONTROL_PROMPT = """你是一名 RPA 开发专家。根据下面的 JSON 定义生成控制流 Python handler。

控制流指令（容器/分支/结构标记）不执行业务逻辑，而是控制工作流的执行路径。
它们通过 emitter 系统展开子节点。

## Handler 注册模板

```python
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(
    type="{{type}}",
    label="{{label}}",
    category="{{category}}",
    runtime="control",
    icon="fa-code-branch",
    icon_color="text-gray-500",
    bg_color="bg-gray-50",
    is_container=True,        # 容器指令（if/for/try 等）
    # is_branch=True,         # 分支指令（else/catch 等）
    # is_structural=True,     # 结构标记（endIf/endFor 等结束标记）
    # closes_with="endXxx",   # 哪个结束标记闭合此容器
)
class {{ClassName}}Handler:
    params = [
        # Param(name, label, type, required=False, default=None, group="主属性")
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        # 控制流逻辑：计算条件、决定跳转等

        runner.completed += 1
        runner.results.append({
            "stepId": step_id, "nodeId": instr.get("nodeId"),
            "status": "success", "result": {"{{type}}": True},
        })
        return True
```

""" + _RUNNER_CONTEXT + """

## 控制流语义

- `is_container=True` — 容器指令（如 forEachElement），子节点由 emitter 展开执行
- `is_structural=True` — 结束标记（如 endFor），仅用于语法闭合，不参与执行
- `is_branch=True` — 容器内的分支路径（如 else）
- `closes_with` — 指定闭合此容器的结束标记 type 名
- 控制流 handler 的 execute() 只做条件判断/状态更新，不需要 I/O 或浏览器通信

""" + _IRON_RULES + """

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
