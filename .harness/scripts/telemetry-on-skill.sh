#!/usr/bin/env bash
# PostToolUse telemetry hook — logs every Skill invocation to
# .harness/telemetry.jsonl. Pure observation; never blocks.
#
# Used by harness:report to compute per-skill success rate, average duration,
# and to surface drift over time.
#
# v0.7: migrated from `command -v jq` fail-open gate to the kit's jp() helper
# so the telemetry record still gets written on jq-less CI / Windows. Without
# the migration, telemetry quietly went dark anywhere jq wasn't installed.
# v0.10.3: jp/have_jq/have_jp extracted to _lib/jp.sh; AHK_DISABLE_TELEMETRY
# opt-out + AHK_TELEMETRY_MAX_LINES rotation added.
set -e

# Opt-out: respect AHK_DISABLE_TELEMETRY=1 before reading stdin so the user
# can fully disable observability without removing the hook from settings.
[ "${AHK_DISABLE_TELEMETRY:-}" = "1" ] && exit 0

INPUT=$(cat)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
_LIB_DIR="$SCRIPT_DIR/_lib"
. "$_LIB_DIR/jp.sh"
. "$_LIB_DIR/telemetry.sh"
if ! have_jp; then exit 0; fi

TOOL=$(echo "$INPUT" | jp '.tool_name // empty')
[ "$TOOL" = "Skill" ] || exit 0

SKILL=$(echo "$INPUT" | jp '.tool_input.skill // empty')
[ -z "$SKILL" ] && exit 0

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SHA=$(git rev-parse --short HEAD 2>/dev/null || echo 'no-git')

# Compose JSONL line by hand — same shape as the previous jq-built record.
# Skill names are constrained to `[a-z0-9-]+` upstream so we don't need full
# JSON escaping here. telemetry_append handles mkdir, append, and rotation.
LINE=$(printf '{"schemaVersion":1,"ts":"%s","event":"skill_invoked","source":"PostToolUse","skill":"%s","sha":"%s"}' \
  "$TS" "$SKILL" "$SHA")
telemetry_append "$LINE"
exit 0
