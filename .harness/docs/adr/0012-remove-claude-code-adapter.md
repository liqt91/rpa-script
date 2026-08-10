# ADR 0012 — 移除 Claude Code 适配层，保留 kit 核心与技能

- **Status:** accepted
- **Date:** 2026-08-10
- **Deciders:** project owner

## Context

项目当前主要在 opencode 中开发，不再使用 Claude Code。agent-harness-kit
（ADR-0001 引入）包含两类资产：

1. **kit 核心**（`.harness/`）：docs/scripts/eval/feature_list/config，不绑定任何
   特定 agent 工具，opencode 正在消费。
2. **Claude Code 适配层**（`.claude/` 非技能部分 + `CLAUDE.md`）：仅 Claude Code
   消费的子代理定义、hooks 接线、settings/keybindings/output-styles/memory/plans。

同时，`.claude/skills/`（33 个技能）虽位于 `.claude/` 下，但 opencode 实际读取
该目录加载技能（本会话证实），且 kit 的 skill-registry、orchestrate 脚本、
permission-model 文档均指向它——它是 kit 技能的家，非 Claude Code 专属。

约束：

1. 删除范围经用户确认：只删 Claude Code 专属，保留 `.claude/skills/` 与
   `.harness/` 核心；全局 `~/.claude/` 不动。
2. AGENTS.md 引用的 9 个 reviewer 子代理（`.claude/agents/*.md`）删除后，
   自审要求需改写为内联形式。
3. `.claude/plans/extension-backlog.md` 含未完成的扩展 backlog（Alt 组合键冲突
   等），有保留价值，不可直接删除。
4. `installed.json` 跟踪了被删文件的哈希，需同步清理，否则漂移。

## Decision

- 删除（git rm）：`CLAUDE.md`、`.claude/agents/`（9 文件）、`.claude/hooks/hooks.json`、
  `.claude/settings.json`、`.claude/settings.local.json`、`.claude/keybindings.json.example`、
  `.claude/output-styles/harness-terse.md`、`.claude/memory/`（2 文件）。
- 迁移：`.claude/plans/extension-backlog.md` → `docs/extension-backlog.md`（git mv）。
- 保留：`.harness/` 全部、`.claude/skills/` 全部。
- 改写 `AGENTS.md`：@-imports 段落去掉「Claude Code 2.1+」措辞；Subagents 一节
  改为「Self-review（no reviewer subagents）」内联自审要求；`CLAUDE.md`/Stop hook/
  HumanLayer 引用改为 `AGENTS.md` + 200 指令软上限。
- kit 元数据对齐：`installed.json` 移除 15 个已删条目；`golden-principles.md`、
  `memory-cheatsheet.md`、`skill-registry.json`、3 个 skill 的 `SKILL.md`/`skill.json`、
  `doc-drift-scan/scripts/scan-paths.mjs`、`propose-harness-improvement` 技能与脚本中
  的 `CLAUDE.md` 引用机械替换为 `AGENTS.md`；golden principle #8/#10 中已失效的
  Stop-hook 强制表述改为软上限/自审说明。
- `.harness/scripts/` 下引用 `CLAUDE_PROJECT_DIR`/CLAUDE.md 的脚本不动——其 hook
  触发链已随 hooks.json 删除成为惰性代码，属 kit 管理文件，避免与上游漂移。

## Consequences

Positive: 移除失效适配层，减少认知噪音；AGENTS.md 成为唯一的 agent 入口文件；
自审要求显式化（此前本会话对 exec 端点的内联自审即发现 1 个真 bug——
CancelledError 未捕获致 future 泄漏，已随本 ADR 修复）。

Negative: `.harness/scripts/` 留有惰性 Claude 引用（env 变量回退，无害）；若日后
恢复 Claude Code，需重新安装 kit 适配层；golden principle #8 失去机械强制
（200 指令上限变为软约定）。

## Alternatives considered

- 全删 `.claude/`（含 skills）并迁移技能到 `.opencode/skills/`：opencode 当前直接
  读 `.claude/skills/`，迁移增加无谓风险与 kit registry 漂移。拒绝。
- 全删不迁移技能：直接丢失 33 个 harness 技能。拒绝。
- 连全局 `~/.claude/` 一起清理：在仓库外，会影响其他项目的全局技能。拒绝。
