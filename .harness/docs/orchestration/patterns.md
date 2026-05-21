# Multi-Agent Orchestration Patterns

- Pipeline: sequential handoff when each step depends on the prior result.
- Fan-out/Fan-in: parallel exploration when work can be split safely.
- Expert Pool: independent specialist reviews before a risky change.
- Red Team: adversarial failure-mode search.
- Supervisor: coordinator tracks multiple subtasks and blockers.
- Pair Review: implementer plus reviewer on one narrow change.

## Runtime MVP

`/orchestrate` still supports packet-only planning, but it can also run a bounded
runtime:

```bash
node .claude/skills/orchestrate/orchestrate.mjs "task" --pattern=fanout --run --max-concurrency=3
node .claude/skills/orchestrate/orchestrate.mjs "task" --pattern=red-team --run --transport=mock
node .claude/skills/orchestrate/orchestrate.mjs --resume=<run-id-or-dir>
node .claude/skills/orchestrate/orchestrate.mjs --validate-run=<run-id-or-dir>
```

Runtime output lands in `.harness/orchestration/<run-id>/`:

- `manifest.json` — task, pattern, prompts, concurrency, fail-fast policy
- `transcripts/*.jsonl` — one transcript per agent lane
- `summary.json` — pass/fail, cost, token, and cache bucket totals
- `summary.md` — human-readable synthesis input

Runtime hardening:

- `--timeout-ms=N` records stalled lanes as timeout failures.
- `--retries=N` retries failed lanes before final failure.
- `--cancel=<run-id-or-dir>` writes a cancellation marker.
- `--resume=<run-id-or-dir>` restores the manifest/summary and reruns only
  failed or missing lanes.
- `--validate-run=<run-id-or-dir>` validates manifest, summary, and transcript
  JSONL schema.

Use `--no-fail-fast` when every lane should finish even after one lane fails.
Every runtime appends trace rows to `.harness/telemetry.jsonl`, which lets
`session-replay`, `cost-tracker`, and `telemetry-export` close the chain from
orchestration task to skill, provider call, cache buckets, cost, transcript, and
report.
