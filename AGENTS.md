# rpa_script — Agent Working Notes

rpa_script — solo-dev browser/desktop RPA 自动化平台。主线 = DSH 原生工具交付可视化
RPA（一个流程 = 一个目录）。本文件是**目录**，不是百科全书；细节按需 @-import。

## Build & Run（真实命令表）

本项目不是 npm 项目，无 `npm run dev`/`npm test`/`npm run lint`。

- 后端：`python -m src.runtime.main`
- 测试：`pytest -q`（全量 186+）
- Lint：`ruff check src tests`
- 结构检查：`npm run harness:check`（统一门禁：AST 层序 + 命令注册表 + skill 契约 + skill 同步；`--with-tests` 追加 pytest）
- skill 契约：`npm run skills:check`
- 新建/改指令：调用 DSH 工具 `rpa_new_command`（唯一入口，勿手跑脚本）

## Architecture（六域，前向依赖）

```text
backend    src/                        dtypes → config → repo → service → runtime → mcp_server
frontend   src/ui/workflow-editor/     （独立 domain）
extension  extension/ → dist/desktop/extension/   （源 → 构建产物，两者都要管）
commands   commands/*.json             （唯一定义源；handler/注册表/content.js 是产物）
plugin     rpa-dsh-plugin/             （DSH 工具面；服务端改动 = 高危）
skills     skills/ → ~/.dsh/skills/    （源 → 同步目标，两者都要管）
```

结构测试只管 backend 层序（`config.json` `domains[].layers`）。完整职责表：
`@.harness/docs/architecture.md`。

## 改动路径速查（本项目最高频决策点）

| 改了什么 | 必须做 |
|---|---|
| `commands/*.json` / handler | `rpa_new_command` 复跑（生成→构建→门禁→热重载一条龙） |
| `extension/` JS 源 | 重建 dist → 自动重载扩展（勿手改 `dist/**` 产物） |
| `src/runtime` 核心（runner/emitter） | **重启后端** + pytest（热重载不覆盖已在内存的模块） |
| `skills/` | bump version + 同步 `~/.dsh/skills/`（`skills/scripts/check-project-skill-sync.mjs` 兜底，即 `npm run skills:sync`） |
| workflow-editor 前端 | rebuild + 同步两处 profile 副本 |

完整矩阵 + 机械兜底：`@.harness/docs/change-matrix.md`。

## Golden principles（节选，全文见 `.harness/docs/golden-principles.md`）

1. 边界校验，不 YOLO 探测数据形状。
2. 每个坑变成一个机械预防（脚本/检查/hook），而不是一句"请注意"。
3. Agent 失败 → `agent-failures.md` + 一个永久预防。
4. AGENTS.md ≤ 200 行，细节全部 @-import。

## Where to look（按需 @-import）

- `@.harness/docs/architecture.md` — 加模块/移动代码。
- `@.harness/docs/change-matrix.md` — 改了什么 → 必做什么 → 谁兜底。
- `@.harness/docs/harness-structure.md` — harness 三层结构地图（三层/目录/门禁/入口）。
- `@.harness/docs/adr/` — 改公共 API。
- `@.harness/docs/golden-principles.md` — 重构前。
- `@.harness/feature_list.json` — 声称特性完成前。
- `@.harness/project/state.json` — 改 phase/MVP/风险/清单前。
- `.harness/memory/current-summary.md` — 共享项目记忆（SessionStart 注入）。
- `.harness/PROGRESS.md` — 会话开始读、结束追加一行。

## Skills

- `/inspect-module <path>` — 理解现有代码。
- `/add-feature <description>` — 加新能力。
- `/deliver-html` — 分析/审计/计划/决策文档（人类阅读 → HTML；agent 文件 → MD）。
- `/remember-project` — 决策/风险/范围变更必须落地。
- `/project-status` — phase/MVP/清单/风险/状态看板。

## Self-review（无 reviewer 子代理）

- 跨层改动 → 核对架构层序 + harness:check 的 layer-spanning 报告。
- auth/输入/密钥 → 边界校验。
- 新错误路径/重试/异步边界 → 追踪失败 + 取消路径。

在提交信息或结果里声明已自审。

## Workflow contract

1. 会话开始：读 `.harness/PROGRESS.md`，对齐 `state.json`。
2. 从 `feature_list.json` 选一个 `passes: false` 的特性。
3. 实现 → 跑结构测试，失败先修。
4. 自审（见上）。
5. 提交（描述性 message）+ 追加一行 `.harness/PROGRESS.md`。
6. **只在端到端测试通过后**把 `feature_list.json` 的 `passes` 置 true。

## What NOT to do

- 不加新层/新架构域而不写 ADR。
- 不引入 native binding 依赖而不写 ADR。
- 不禁用结构测试来过关。
- 不写结构测试无法推理的动态跨层 import。
- 不改 `extension/`（MV3 CSP 禁 eval/new Function）、不改 `dist/**` 产物、
  不手跑 `generate_commands.py`/`build_*_js.py`。
- 不改 AGENTS.md 而不走 `/propose-harness-improvement`。
- 不让 AGENTS.md 超 200 行。

## 环境不变量（来自日志踩坑，必守）

- 浏览器加载 `dist/desktop/extension/`，不是 `extension/` — 改了源不重建 = 改了空气。
- DSH 加载 `~/.dsh/skills/`，不是仓库 `skills/` — 不同步 = 新事实永不生效。
- 改 `src/runtime` 核心必须重启后端；`skills/scripts/check-project-skill-sync.mjs`（`npm run skills:sync`）兜底 skill 同步。
- 静默失败是最大敌人：每步补验证节点、0 匹配报错、回读校验。
- 项目跑在本机（DSH GUI 与浏览器同机），多窗口共存无焦点仍会绑错窗口，需程序化绑定 `workWindowId`。
- 沙箱默认仅写工作区，可提权 full access；RPA 后端需提权后启动（写 RPA_HOME、驻留、spawn 浏览器）。
