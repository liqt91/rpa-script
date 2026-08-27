# 质量标准（硬性 · 生成时对照）

**JSON**：`cmd` 非空小驼峰=文件名 · `runtime∈{extension,backend,control}`（desktop 用 backend）·
`handler.kind==runtime` · `source` 指向对应目录 · `category`(中文)+`categories`(slug)均填 ·
`params[].name` 与 Python `Param` 一一对应。

**Python handler**（backend/desktop/control）：
- 含 `@register_handler`（与 JSON 一致）
- `Param` 与 JSON params 一一对应
- `async def execute(runner, cmd_type, step_id, instr)`（control 用 `evaluate()`）
- 读参用 `extra.get("paramName")`（str-var 用 `clean_var_ref` 剥 {{}}）
- 成功路径 `runner.completed += 1` + `runner.results.append({...})` + `await runner._emit({"type":"stepComplete",...})`
- 失败路径 `await runner._emit({"type":"stepError",...})` + `return False`
- 提供 `summary_tpl`
- 不残留 AUTO-GENERATED 哨兵
- 变量已由 runner 统一 resolve（execute 内勿再调 resolve_vars）

**JS handler**（extension）：`registerHandler(cmd, async ({locator, selectorFamily, extra}) => {...})`（DOM）或 `registerBackgroundHandler(cmd, async (step, agent) => {...})`（后台）；返回 dict 带 `value`/`extracted` 供写回变量。

> 验证信号：`command_builder.py` 返回 `quality_pass:true`（实现合规）+ `reload_pass:true`（已热加载）。
> 不过时用 `python skills/scripts/check_command_quality.py <cmd>` 看哪条。extension 指令另需 `verify.success:true`（Node 桩跑通）。
