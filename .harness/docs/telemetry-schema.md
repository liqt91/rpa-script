# Telemetry Schema

`.harness/telemetry.jsonl` is append-only JSONL. New writers emit
`schemaVersion: 1`; readers keep accepting older rows when the shape is
unambiguous.

## Event Taxonomy

| Event | Required fields | Writer |
| --- | --- | --- |
| `skill_invoked` | `ts`, `event`, `skill`, `sha` | `telemetry-on-skill.sh` |
| `notification` | `ts`, `event`, `hook`, `type`, `title`, `body` | `notify-on-block.sh` |
| `subagent_stop` | `ts`, `event`, `subagent`, `sha` | `subagent-stop.sh` |
| `session_rollup` | `ts`, `event`, `reason`, `session_id`, `sha` | `session-rollup.mjs` |
| `provider_call` | `ts`, `event`, `provider` | provider/middleware telemetry |
| `tool_execution` | `ts`, `event`, `tool_name` | tool execution telemetry |
| `eval_run` | `ts`, `event`, `taskId`, `passed` | eval telemetry |
| `orchestration_summary` | `ts`, `event`, `session_id`, `skill`, `task_id`, `summaryPath` | `/orchestrate --run` |
| `structural_test_fail` | `ts`, `event`, `source` | structural failure telemetry |

## Reader Rules

- Ignore malformed JSONL rows.
- Ignore unknown events unless the reader explicitly handles generic events.
- Attribute provider calls by `skill` and `task_id` when present. If a provider
  call omits `skill`, readers may attribute it to the most recent
  `skill_invoked` row in the same `session_id`.
- Treat orchestration `session_id` as the run id so replay, cost, and OTLP
  export can join task, skill, provider call, cache bucket, cost, transcript,
  and summary rows without a secondary lookup.
- Treat `cache_creation_input_tokens` as cache-write tokens and
  `cache_read_input_tokens` as cache-read tokens. Cost readers should use
  explicit cost fields first, then fall back to model pricing estimates.
- Treat legacy skill rows with `{ "skill": "..." }` and no `event` as
  `skill_invoked`.
- Treat legacy notification rows with `{ "hook": "Notification" }` and no
  `event` as `notification`.

The source of truth for event names and lightweight validation helpers is
`.harness/scripts/_lib/telemetry-schema.mjs`.
