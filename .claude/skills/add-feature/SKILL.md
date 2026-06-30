---
name: add-feature
description: Use this skill whenever the user asks to add, implement, or build a new feature, capability, endpoint, page, command, or anything user-visible. Enforces the Anthropic two-fold harness pattern — read .harness/feature_list.json, pick exactly one feature, implement incrementally, run the structural test on every save, and never declare "done" without updating the JSON. Always invoke this skill instead of writing new feature code freehand.
allowed-tools: Read, Edit, Write, Bash(npm run:*), Bash(pytest:*), Bash(ruff:*), Bash(git:*), Glob, Grep
suggested-turns: 25
---

## Steps

1. **Read `.harness/feature_list.json`.** Confirm the feature exists and `passes:
   false`. If the user described a feature not in the list, **stop**: ask
   whether to add it via `/add-adr` first.
2. **Read `.harness/docs/architecture.md`** for the affected domain. Identify which
   layers will change.
3. **Run `/inspect-module`** on each affected module. Do this even if you
   think you know the area — verify, don't assume.
4. **Plan first.** Write a one-paragraph plan to `.harness/PLAN.md` *before
   any code change*. (Anthropic Claude 4 prompt-guide pattern.)
5. **Implement smallest first.** Make the smallest change that turns one
   `steps[]` item from failing → passing.
6. **Run the structural test.** `npm run harness:check`.
   If it fails, fix the violation before continuing — never disable the test.
7. **Smoke test.** Run the relevant smoke test from `.harness/scripts/dev-up.sh`.
8. **Update `.harness/feature_list.json` ONLY** by changing the `passes` field of one
   item. Never delete or rewrite items. (Anthropic JSON-over-Markdown rule:
   "the model is less likely to inappropriately change or overwrite JSON
   files compared to Markdown files.")
9. **Append to PROGRESS.** One line in `.harness/PROGRESS.md`:
   `YYYY-MM-DD HH:MM | <feature_id> | done`.
10. **Commit.** Message: `feat(<domain>): <feature_id> - <short>`.

## Failure modes to avoid (each line below corresponds to a real observed failure)

- Don't claim a feature is done without running the smoke test.
- Don't mark `passes: true` if the structural test is failing.
- Don't add a new feature to `.harness/feature_list.json` mid-session — propose it
  for the next session via ADR instead.
- Don't refactor unrelated code in the same commit.

## Output contract

After implementation, summarize:

```
### Feature: <id>
### Files changed: <list>
### Structural test: PASS|FAIL
### Smoke test: PASS|FAIL
### Reviewer subagents to invoke: architecture-reviewer, security-reviewer (if auth/IO touched), reliability-reviewer (if retries/timeouts touched)
```
