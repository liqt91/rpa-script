# Environment variables

Every kit hook and side-car honors one or more `AHK_*` env vars for opt-out,
debugging, or non-default behavior. Defaults are tuned for "just works" —
override only when you have a specific reason.

## Opt-out

| Var | Default | Effect |
| --- | --- | --- |
| `AHK_DISABLE_TELEMETRY` | unset | When `1`, the `telemetry-on-skill` and `subagent-stop` hooks exit before reading stdin — no `.harness/telemetry.jsonl` is created. Use when you do not want per-skill activity recorded. |
| `AHK_DISABLE_MEMORY` | unset | When `1`, `SessionEnd`, `/remember-project`, and project-memory side-cars skip writes to `.harness/memory/ledger.jsonl` and `.harness/memory/current-summary.md`. Use for sensitive sessions. |
| `AHK_DISABLE_NOTIFY` | unset | When `1`, the `notify-on-block` hook skips the OS-native notification (osascript / notify-send). The telemetry row still logs the notification event. |
| `AHK_DISABLE_HTML_OPEN` | unset | When `1`, `/deliver-html` writes the HTML file but does not auto-open it in the browser. Also implied when `CI=true`. |
| `AHK_DISABLE_HTML_NUDGE` | unset | When `1`, suppresses the inline reminder that `/deliver-html` is available for analysis-style tasks. |
| `AHK_DISABLE_JQ` | unset | When `1`, hooks pretend `jq` is not on `$PATH` and use the Node fallback (`.harness/scripts/_lib/json-pick.mjs`). Used by tests to exercise the fallback path. |

## Bypass (audited)

| Var | Default | Effect |
| --- | --- | --- |
| `AHK_ALLOW_BYPASS` | unset | When `1`, `userprompt-guard`, `pretooluse-bash-guard`, and `pretooluse-edit-guard` allow the action through but append a record to `.harness/bypass.log` (timestamp + sha + reason + payload). The bypass leaves a paper trail so it cannot be silent. Use only with explicit intent — e.g. a mass-rename refactor that legitimately touches `.claude/`. |
| `AHK_HOOK_MODE` | unset | When `warn`, every gate hook (structural-test-on-edit, pretooluse-edit-guard, subagent-stop) logs the would-be violation to stderr but does not deny. Useful for one-off debugging; do not leave set in normal use. |

## Tuning

| Var | Default | Effect |
| --- | --- | --- |
| `AHK_TELEMETRY_MAX_LINES` | `5000` | Soft cap on `.harness/telemetry.jsonl` size. The `telemetry_append` helper rotates via `tail -n <N>` once the file grows past this number of lines. Set `0` to disable rotation entirely. Numeric only — non-numeric values fall back to the default rather than failing the hook. |
| `AHK_HEADLESS_RECOVER` | `0` | When `1`, the Stop hook spawns `claude -p` for one turn of recovery on failure. Costs tokens; off by default. Persistent equivalent: `.harness/config.json#recovery.headless`. |
| `AHK_RECOVERY_LOCK_STALE_SECS` | `300` | How long the Stop-hook recovery lock is considered stale before a new recovery attempt can take it. Prevents stuck locks after a killed session. |
| `AHK_STATUSLINE_NO_COLOR` | unset | When `1`, the statusline emits plain text — no ANSI color escapes. Useful on terminals that do not render colors well, or when piping the output. |

## Where each variable lives

```
AHK_DISABLE_TELEMETRY  → .harness/scripts/telemetry-on-skill.sh, .harness/scripts/subagent-stop.sh
AHK_DISABLE_MEMORY     → .harness/scripts/project-memory.mjs, .harness/scripts/session-end.sh, .harness/scripts/session-start.sh
AHK_DISABLE_NOTIFY     → .harness/scripts/notify-on-block.sh
AHK_DISABLE_HTML_OPEN  → .claude/skills/deliver-html/scripts/wrap-html.mjs
AHK_DISABLE_HTML_NUDGE → .claude/skills/deliver-html/SKILL.md
AHK_DISABLE_JQ         → .harness/scripts/_lib/jp.sh (probed by every hook that parses JSON)
AHK_ALLOW_BYPASS       → .harness/scripts/userprompt-guard.sh, .harness/scripts/pretooluse-*.sh
AHK_HOOK_MODE          → .harness/scripts/structural-test-on-edit.sh, .harness/scripts/pretooluse-edit-guard.sh, .harness/scripts/subagent-stop.sh
AHK_TELEMETRY_MAX_LINES→ .harness/scripts/_lib/telemetry.sh (used by telemetry-on-skill, subagent-stop, notify-on-block)
AHK_HEADLESS_RECOVER   → .harness/scripts/precompletion-checklist.sh
AHK_STATUSLINE_NO_COLOR→ .harness/scripts/statusline.mjs
```

## Disabling vs. removing

Prefer env-var opt-out over removing a hook from `.claude/settings.json` —
the kit's structural-test and version-sync checks expect every hook listed in
`hooks.json` to be present. Removing a hook leaves the index claiming a
contract the file system no longer fulfills, and `agent-harness-kit upgrade`
will keep re-installing it.
