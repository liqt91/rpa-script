"""
Update AI prompt scenarios for command handler code generation.

Three command types -> three prompts, stored in the ai_llm_configs.scenarios JSON
column so the frontend can select the right prompt per command type.

Usage: python scripts/update_llm_prompt.py [data.db path]

Note: The prompt template variables {{scaffold}}, {{definition_json}}, {{context}}
are replaced by the backend at runtime (see other_routers.py generate_with_scenario).
"""

import sqlite3
import os
import json


BACKEND_PROMPT = """
你是 RPA 后端开发专家。下面是一份已经写好的 Python handler 代码，import、注册、参数读取、结果上报都已正确。
你只需要把 `# TODO: 业务逻辑` 区域替换成真实可执行的业务代码，然后输出完整文件。

=== 当前代码（你只能修改 # TODO 区域）===

```python
{{scaffold}}
```

=== 项目 API 清单（按需选用，不要编造）===

浏览器操作：
  from src.repo.browser_utils import is_browser_running, launch_browser_with_extension
  # launch_browser_with_extension(browser_type) -> bool  自动加载 RPA 扩展启动浏览器

  from src.runtime.workflow.extension_runner import wait_for_extension_connection, ext_manager
  # client_id = await wait_for_extension_connection(browser_type, ext_manager, timeout=10.0)
  # 连接建立后必须设置: runner.client_id = client_id

工具函数：
  from src.runtime.workflow.handlers.utils import clean_var_ref, convert_value
  # clean_var_ref("${var}") -> "var"
  # convert_value(value, type, runner.vars) -> 转换后的值

HTTP 请求：
  import httpx  # 项目已安装
  async with httpx.AsyncClient() as client:
      resp = await client.get(url, headers={...})

=== 架构规则 ===
- backend 指令: execute() 完成全部工作，不涉及浏览器扩展
- extension 指令: execute() 只做前置工作（启动浏览器、建立 WebSocket 连接）。扩展通信和窗口管理由 Runner 负责，不要在 execute() 里调用 _send_and_wait
- 输出变量：如果参数 group="output" 且 type="str-var"，其值代表写入 runner.vars 的键名，执行后写入 runner.vars[键名]

=== 硬性要求 ===
1. 只能改 # TODO 之后、result_summary 之前的代码，其他地方一个字符都不准动
2. 保留 result_summary、runner.completed、runner.results、runner._emit 结果上报代码
3. 不要重写整个文件，不要改 import/register/params/extra 读取
4. result_summary 必须是 dict
5. 不确定的 API 不要编造，说明"需确认"
6. 直接输出完整文件，不要代码块包裹，不要说明文字
"""

EXTENSION_JS_PROMPT = """
你是 Chrome 扩展开发专家。请根据下面的指令定义，编写浏览器扩展的 JS handler。

=== 指令定义 ===
{{definition_json}}

=== Handler 上下文 ===
{{context}}

=== 可用 API ===
注册方式（根据上下文选择其一）：
  registerHandler(name, handler)          — DOM handler（content script 中运行）
  registerBackgroundHandler(name, handler) — background handler（Service Worker 中运行）

DOM handler 可用工具（content.js 中已定义）：
  findElement(elementDef, scope, visibilityMode) -> DOM Element | null
    elementDef: args.elements[elementName]
    scope: "local" | "global"
    visibilityMode: "visible" | "any"
  resolveSelector(selectors) -> 最佳选择器字符串
  sleep(ms) -> Promise

参数读取：
  args.extra — 用户填写的参数 {paramName: value}，参数名与 JSON 定义一致
  args.elements — 元素选择器 {elementName: {selectors: [...]}}

Background handler 可用：
  chrome.windows / chrome.tabs — 扩展后台 API
  agent.workWindowId / agent.workTabId — 当前工作窗口/标签
  agent._injectContentScript(tabId) — 注入 content script
  agent._send(type, payload) — 通过 WebSocket 发送消息到后端

=== 返回值规范 ===
  { ok: true }                           — 成功
  { ok: true, result: {...} }            — 带结果
  { ok: true, vars: {key: val} }         — 写变量
  { ok: false, error: "原因" }            — 失败

=== 要求 ===
1. 根据上下文选择正确的注册方式（registerHandler 或 registerBackgroundHandler）
2. 代码必须真实可执行，正确处理错误情况
3. DOM 操作前检查元素是否存在（findElement 可能返回 null）
4. 直接输出完整 JS 代码，不要 markdown 代码块，不要说明文字
"""

CONTROL_PROMPT = """
你是 RPA 工作流引擎开发专家。请填充控制流 handler 的 # TODO 区域。

=== 当前代码 ===

```python
{{scaffold}}
```

=== 控制流语义 ===
- is_container=True — 容器指令（for/if/try），子节点由 emitter 展开执行
- is_structural=True — 结束标记（endFor/endIf），仅语法闭合
- is_branch=True — 分支路径（else/catch）
- 控制流 handler 的 execute() 只做条件判断/状态更新，不需要 I/O 或浏览器通信

=== Runner 可用 API ===
- runner.vars: dict — 工作流变量空间
- runner.current_loop_index: int | None — 循环索引
- runner.get_parent_vars() -> dict: 父级变量
- instr.get("extra"): dict — 用户填写的参数值

=== 要求 ===
1. 只能改 # TODO 区域，不能改其他地方
2. 控制流逻辑必须正确处理嵌套场景
3. 不写 pass 或占位代码
4. 直接输出完整代码，不要代码块，不要说明文字
"""

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
