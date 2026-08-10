---
name: command-test
description: Use this skill whenever the user asks to 测试指令/测试命令/"把 X 指令也测试下"/run an end-to-end test of workflow commands (e.g. "变量及日志的指令也测试下", "浏览器操作指令测试"). Runs the full E2E command-test loop — test-plan doc → build a dedicated test workflow via build_workflow.py → trigger POST /api/workflows/{id}/run/extension with a locally minted JWT via run_workflow.py → verify per-step results from run.log → write 结果 doc + work-log entry — without re-deriving DB storage shape, auth, or endpoints. Enforces 只记录问题不改代码.
allowed-tools: Read, Write, Edit, Glob, Grep, TodoWrite, Bash(python .claude/skills/command-test/scripts/*.py:*)
suggested-turns: 12
---

## When to use

The user asks to end-to-end test workflow commands (指令): "测试 X 指令",
"把 XX 指令也测试下", "run a real test of the log command". This is a real run
against the live backend + Edge extension — not pytest unit tests.

## Fixed reference (verified 2026-08-07 — do not re-derive from source)

**Storage (SQLite `data/data.db`)**
- `workflow_nodes`: column `[type]` = cmd; `element_name` column references
  `workflow_elements.name`; `extra` = JSON params; `[order]` = sequence.
- Elements are per-workflow → a new test workflow must copy the elements it
  uses (`build_workflow.py` `elementsToCopy`).
- Generic params inside extra: `onError`/`retryCount`/`timeout`/`description`
  (plus `humanLike` for extension-runtime commands).

**Run**
- Backend must be dev-mode on :8000 using repo `data/data.db` (NOT the packaged
  desktop app on :8811, which uses the %APPDATA% DB).
- Trigger: `POST /api/workflows/{wf_id}/run/extension` with Bearer JWT minted
  from `.env` SECRET_KEY (HS256, sub=1). The call blocks until the run finishes
  — allow ≥ 480s. `run_workflow.py` handles all of this.
- Per-step log: `<logDir>/run.log` (logDir is in the run response), one SSE
  JSON event per line (stepStart / stepComplete / stepError / done).

**valueType (setVar)** — use handler-registered values, NOT commands/*.json:
`str-input` / `int-number` / `bool-check` / `list-input` / `dict-input` /
`any-expr` / `any-input`. `any-input` = JSON-infer then fall back to string;
`any-expr` with `=expr` prefix evaluates via restricted eval.

**Encoding (hard rule)** — any Chinese in scripts/specs MUST go through a UTF-8
file written with the Write tool, executed as `python <file>`. NEVER inline
Chinese through a PowerShell pipe/here-string stdin — it is silently GBK-
corrupted to `????`.

**Loops / containers (verified 2026-08-10)**
- Nesting = `workflow_nodes.parent_id`; loop containers (forRange/forList/
  whileCondition/forEachElement) sit top-level, body children get `parentOrder`
  in the spec, `endLoop`/`endIf` are top-level (or sibling) structural markers.
- Handler-side param names rule: forList reads `listVar` (NOT `listName` from
  commands/forList.json); forRange reads `start/end/step/itemVar`.
- Counter increment: setVar `valueType=any-expr` + `value="={{n}}+1"`.
- whileCondition: `maxIterations` (default 100) is the anti-hang guard — always
  set it in tests. `executeFirst` default false.
- Browser runs: extension must be ONLINE before the run (runner never launches
  the browser). Extension defaults to :8811 — for the dev backend set port 8000
  in extension options; check `GET /api/extension/status` → `online:true`.
  Legacy cmd `openBrowser` was removed (2026-08-10) — unregistered cmds now
  fail with an explicit stepError. Use `launchBrowser`.

**Known behaviors (standing)**
- P1: run `success` means "not stopped"; stays true even with failed steps.
- P2: `log` result entries are bare `{"log","level"}` — no stepId/nodeId wrapper.
- P3: undefined `{{var}}` is kept verbatim in output (no error).
- P4: empty locator produces a misleading error ("工作标签页已被手动关闭").
- P5: stepStart summary shows unresolved `{{var}}` (execution resolves fine).
- Loop-body stepStart now carries cmdType/cmdLabel; done/counters are
  event-based so completed ≤ total (break/continue steps never emit
  completion, so completed < total is normal).
- Child element missing inside a loop item → contextNotFound soft result:
  onError=continue → empty value + stepWarning; onError=stop → explicit
  stepError "元素在当前循环项中未找到".

**Fixed 2026-08-10 (regression-verified, wf=23/24/25/27/28/29 all green)**
- B1 forList listVar/listName + B2 ifVarEquals compareTo +同类参数对齐、
  B3 if* bool 崩溃、B4 未注册指令显式报错（openBrowser 已删除→launchBrowser）、
  B5 扩展 5 个查询 handler 补齐、M1-M5、B6 findTarget 循环上下文解析。
  Details: docs/循环指令测试结果-20260810.md 第九节。

## Steps

1. **Confirm scope** with the user: which commands, pure-backend vs
   browser-cross, dedicated workflow name.
2. **Write the test-plan doc** `docs/<主题>指令测试方案.md` (template below).
3. **Write the build spec JSON** (UTF-8 via Write tool) and run:
   `python .claude/skills/command-test/scripts/build_workflow.py --spec <spec>`
   It prints the new wf id and echoes back each node — check Chinese survived.
4. **Run:** `python .claude/skills/command-test/scripts/run_workflow.py <wf_id>`.
   For browser steps, watch Edge actually navigate.
5. **Cross-check** each step against the plan's expected column. For deep
   checks: `python .claude/skills/command-test/scripts/read_run.py <logDir>`.
6. **Write** `docs/<主题>指令测试结果-<YYYYMMDD>.md` + the issue list
   (record-only — never fix code inside this loop). Append a section to
   today's work log (`docs/工作日志-<YYYYMMDD>.md`).

## Spec format (build_workflow.py)

```json
{
  "name": "变量及日志测试",
  "description": "…",
  "elementsToCopy": [{"id": 1}, {"workflowId": 2, "name": "搜索框"}],
  "elements": [{"name": "必应结果列表", "selector": "css:li.b_algo"}],
  "nodes": [
    {"order": 1, "cmd": "setVar",
     "extra": {"name": "x", "value": "1", "valueType": "int-number",
               "onError": "stop", "retryCount": 3, "timeout": 10, "description": ""}},
    {"order": 2, "cmd": "forRange",
     "extra": {"start": 0, "end": 4, "step": 1, "itemVar": "i"}},
    {"order": 3, "cmd": "log", "parentOrder": 2,
     "extra": {"level": "info", "message": "iter {{i}}"}},
    {"order": 4, "cmd": "endLoop", "extra": {}}
  ]
}
```

- `parentOrder` = the container node's `order` (loop/if body nesting).
- `elements` = inline element creation (`elementKind` default `plain`).

## Output contract

Test-plan doc (`docs/<主题>指令测试方案.md`): 目标 / 边界 / 指令参数表 /
已知实现点 / 编排表(每步: 指令+参数+预期) / 元素准备 / 运行与记录 / 风险提示。

Result doc (`docs/<主题>指令测试结果-<date>.md`): 总览表(运行次数/结果/耗时) /
分步判定表 / 问题清单(编号+严重级+说明) / 测试过程问题(非产品) / 涉及资产。

## Anti-patterns

- Don't inline Chinese through PowerShell stdin (silent `????` corruption).
- Don't fix source code while testing — record the issue only.
- Don't re-derive storage shapes/auth/endpoints from source files — the
  reference above is verified; re-reading burns turns.
- Don't reuse an old workflow's nodes — create a fresh dedicated workflow per
  command group (build_workflow.py errors on duplicate workflow names).
- Don't blanket-set `onError=continue` — keep `stop` (default) so failures halt
  visibly; only `continue` steps expected to be flaky (e.g. login-gated elements).
