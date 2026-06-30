---
name: orchestrate
description: Select and run a multi-agent workflow pattern for work that exceeds one agent's reliable scope. Use for parallel research, independent reviews, cross-domain changes, or high-risk implementation planning.
allowed-tools: Read, Write, Bash(node .claude/skills/orchestrate/orchestrate.mjs:*)
suggested-turns: 10
---

# Multi-Agent Orchestration

Chooses one of six team patterns. By default it produces an agent execution packet; with `--run` it runs the pattern as an MVP orchestration runtime and records transcripts, cost, token, and cache metrics.

## Patterns

1. `pipeline` — sequential handoff: explore → plan → implement → review.
2. `fanout` — parallel independent investigation, then synthesize.
3. `fanin` — collect outputs from several agents into one decision.
4. `expert-pool` — ask specialized reviewers for second opinions.
5. `red-team` — adversarial review for security/reliability risks.
6. `supervisor` — one coordinator tracks subtask completion.

## Steps

```bash
node .claude/skills/orchestrate/orchestrate.mjs "task description" --pattern=fanout
node .claude/skills/orchestrate/orchestrate.mjs "task description" --pattern=fanout --run --max-concurrency=3
node .claude/skills/orchestrate/orchestrate.mjs "task description" --pattern=fanout --run --transport=mock
node .claude/skills/orchestrate/orchestrate.mjs --resume=<run-id-or-dir>
node .claude/skills/orchestrate/orchestrate.mjs --validate-run=<run-id-or-dir>
```

Packet mode writes `.harness/docs/orchestration/<timestamp>-<pattern>.md`.

Runtime mode writes `.harness/orchestration/<run-id>/manifest.json`, per-agent transcripts, `summary.json`, and `summary.md`. It also appends orchestrate telemetry to `.harness/telemetry.jsonl` so cost/replay/export tools can trace `task -> skill -> provider call -> cache bucket -> cost`. Use `--no-fail-fast` when you need every lane to finish even after a failure.

Hardening flags:

- `--timeout-ms=N` kills a stalled lane and records a timeout result.
- `--retries=N` retries failed lanes before marking them failed.
- `--resume=<run-id-or-dir>` skips previously passed lanes and reruns missing/failed lanes.
- `--cancel=<run-id-or-dir>` writes a cancellation marker consumed by resume/running lanes.
- `--validate-run=<run-id-or-dir>` checks manifest, summary, and JSONL transcript schema.

## Output contract

```markdown
### Orchestration: <pattern>
### Agents: <count>
### Packet: .harness/docs/orchestration/<timestamp>-<pattern>.md
### Synthesis owner: main agent
```
