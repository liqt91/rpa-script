# Harness 结构 — rpa_script

> 本项目 harness 的完整地图。三层叠加，通过 `config.json`（层序）+ `change-matrix.md`（改动路径）+ `harness-check.mjs`（门禁编排）联动。
> 更新：2026-08-27（harness 收拢 Step 1+2 后）。

## 总览：三层 harness 叠加

```
┌────────────────────────────────────────────────────────────────────────┐
│ ① agent-harness-kit 骨架（.harness/ + .claude/）                        │  ← kit 提供，通用
├────────────────────────────────────────────────────────────────────────┤
│ ② 项目领域 skill（skills/ → ~/.dsh/skills/）                            │  ← 项目自建，RPA 领域
├────────────────────────────────────────────────────────────────────────┤
│ ③ 项目专属门禁脚本（scripts/ + skills/scripts/）                        │  ← 项目自建，收拢中
└────────────────────────────────────────────────────────────────────────┘
        三者通过 ③ 的「统一入口 harness:check」串起来
```

---

## ① agent-harness-kit 骨架 —— `.harness/` + `.claude/`

### `.harness/` 配置文件

| 文件 | 作用 |
|---|---|
| `config.json` | 结构测试权威配置：backend 层序 `dtypes→config→repo→service→runtime→mcp_server` + frontend 独立 domain `ui/workflow-editor`；projectMemory / projectManagement 开关 |
| `feature_list.json` | 特性清单 + 步骤 + `passes` 状态（端到端验收依据） |
| `project/state.json` | phase / risks / decisions（经 Step 1 已填） |
| `skill-registry.json` / `permissions.json` / `installed.json` | kit 侧 skill 注册 / 权限 / 安装清单 |
| `structural-baseline.json` | 存量结构违规基线（golden #9，只能减不能增） |
| `compaction-snapshot.json` | 会话压缩快照（kit 内部） |

### `.harness/docs/` 文档（agent 知识）

| 文件 | 作用 |
|---|---|
| `architecture.md` | 架构层序 + 域职责（事实源） |
| `golden-principles.md` | 11 条黄金原则（每条必须可机械执行） |
| `change-matrix.md` | 改动路径矩阵 + 三目录职责 + 四门禁分工 |
| `adr/` | 12 篇架构决策记录（0001~0012） |
| `agent-failures.md` | agent 踩坑日志 → 每个坑一个永久预防 |
| `tech-debt-tracker.md` | 技术债记录（目前只有模板） |
| `browser-validation.md` / `env-vars.md` / `telemetry-schema.md` / `permission-model.md` / `core-beliefs.md` / `memory-cheatsheet.md` 等 | kit 通用参考文档 |

### `.harness/scripts/` kit 脚本（40+ 个）

大部分是 kit 通用、单人项目用不到的（bench / eval / regression / ab / telemetry / session 钩子 / git hooks）。**本项目用到的关键几个**：

| 脚本 | 作用 |
|---|---|
| `ast_structural_check.py` | backend 层序检查（权威实现），`harness:check` 实际调用它 |
| `check-skill-contracts.mjs` | kit 侧 `.claude/skills` 契约检查 |

### `.harness/runners/`

| 脚本 | 作用 |
|---|---|
| `structural-check.mjs` | 空壳（曾绑定 `harness:check`，现已弃用） |
| `validate_commands.py` | 命令注册表一致性校验（`harness:check` 调用） |

### `.claude/skills/` —— kit 通用技能（33 个）

`inspect-module` / `add-feature` / `deliver-html` / `project-status` / `remember-project` / `propose-harness-improvement` / `garbage-collection` 等。

---

## ② 项目领域 skill —— `skills/` → `~/.dsh/skills/`

本项目自建的 RPA 领域知识。DSH 实际加载 `~/.dsh/skills/`（不是仓库），改动需同步（`npm run skills:sync`）。

| skill | 版本 | 作用 |
|---|---|---|
| `new-command` | 1.13.0 | 指令生成（生成+校验+热重载一条龙，走 `rpa_new_command`） |
| `check-command` | 1.0.0 | 指令定义一致性检查 |
| `pre-generate-workflow` | 1.0.0 | 预生成流程（需求拆解 + 元素库就绪检查） |
| `generate-workflow` | 1.0.0 | 步骤序列 → WorkflowNode[] 写入 DB |

配套：`skills/project-skills.json`（项目 skill registry，与各 skill.json 对齐）。

---

## ③ 项目专属门禁脚本

### `scripts/`（产品工具链，17 个）——指令构建 + 迁移 + 构建

- `command_builder.py` —— 指令构建编排器（`rpa_new_command` 执行体）
- `generate_commands.py` / `build_content_js.py` / `build_background_js.py` —— 指令编译
- `verify_web_handler.mjs` —— Node 桩验证 JS handler
- `migrate_*.py` / `export_commands.py` / `build_extension.py` —— 迁移构建
- `install-dsh-plugin.ps1` / `build-plugin-package.ps1` —— 插件安装
- `native_host.py` / `register_native_host.py` —— 原生宿主
- `harness-check.mjs` —— 门禁统一编排入口

### `skills/scripts/`（skill 门禁，5 个）

- `check_command_quality.py` —— 单指令质量门禁
- `check-project-skills.mjs` —— 仓库内部 skill 契约
- `check-project-skill-sync.mjs` —— 仓库 ↔ `~/.dsh/skills/` 同步
- `run_workflow.py` / `read_run.py` —— skill 运行时辅助

---

## 统一入口

```
npm run harness:check   （scripts/harness-check.mjs）
   ├── L0  python .harness/scripts/ast_structural_check.py     ← backend 层序
   ├── L0  python .harness/runners/validate_commands.py         ← 命令注册表
   ├── L1  node skills/scripts/check-project-skills.mjs         ← skill 契约
   ├── L1  node skills/scripts/check-project-skill-sync.mjs     ← skill 同步
   └── [--with-tests] pytest -q                                ← L2（慢，按需）

npm run skills:check    ← 单独跑 skill 契约
npm run skills:sync     ← 单独跑 skill 同步
```
