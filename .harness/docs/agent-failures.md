# Agent failures log

This is the running log of agent mistakes that triggered a harness
improvement. Each entry should answer: what happened, what we did to make
sure it never happens again, and where the prevention now lives.

The `/propose-harness-improvement` skill appends entries here automatically.

> "Anytime you find an agent makes a mistake, you take the time to engineer
> a solution such that the agent never makes that mistake again."
> — Mitchell Hashimoto, _My AI Adoption Journey_ (Feb 5, 2026)

## Format

```
### YYYY-MM-DD  <slug>
- **Symptom:** <what went wrong>
- **Classification:** (a) missing context | (b) missing rule | (c) missing tool/skill | (d) wrong layer | (e) wrong instruction in prompt
- **Fix applied:** <what we did>
- **Fix lives in:** path/or/file
```

## Entries

### 2026-08-27  project-skill-sync-drift
- **Symptom:** agent 改了仓库 `skills/new-command/SKILL.md`（加 references/、事实卡、修正「自动重载」），但 DSH 实际加载的是用户级 `~/.dsh/skills/new-command/`（只有旧 230 行 SKILL.md，无 references/、无事实卡），导致新事实与修正从未生效——agent 产出仍按旧 skill 走。
- **Classification:** (b) missing rule — 缺「项目 skill 变更后必须同步到 `~/.dsh/skills/` 并 bump version」的硬性规则 + 机械检查。
- **Fix applied:** ① 手动同步新版 `new-command` 到 `~/.dsh/skills/`（version 1.12.0→1.13.0）；② 新增 `.harness/scripts/check-project-skill-sync.mjs`，机械比较仓库 `skills/` 与 `~/.dsh/skills/` 的 `skill.json` version 与 SKILL.md/references 漂移；③ 本条目登记。
- **Fix lives in:** `.harness/scripts/check-project-skill-sync.mjs` + `.harness/docs/project-skill-sync.md`；同步目标路径由 `.harness/config.json` `projectSkills.sync.target` 声明。
