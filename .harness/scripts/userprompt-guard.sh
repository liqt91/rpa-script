#!/usr/bin/env bash
# UserPromptSubmit hook — denies prompt patterns that undo harness safety
# rules. Hard guardrail replacing soft CLAUDE.md guidance.
#
# Denied patterns:
#   1. "ignore previous instructions" / "disregard above"
#   2. "disable the structural test" / "skip the structural check"
#   3. "bypass the (Stop|PreToolUse|hook) (rules?|checks?)"
#   4. "remove the .harness" / "delete .harness directory"
#   5. "set disableAllHooks: true"
#
# Escape hatch: AHK_ALLOW_BYPASS=1 logs to .harness/bypass.log + lets through.
set -eo pipefail

INPUT=$(cat)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
_LIB_DIR="$SCRIPT_DIR/_lib"
. "$_LIB_DIR/jp.sh"

if ! have_jp; then
  exit 0
fi

PROMPT=$(echo "$INPUT" | jp '.prompt // empty')
[ -z "$PROMPT" ] && exit 0

LOWER=$(printf '%s' "$PROMPT" | tr '[:upper:]' '[:lower:]')

REASON=""

if printf '%s' "$LOWER" | grep -qE '(ignore|disregard|forget) (the|all|any|your|previous|prior|above)'; then
  REASON="Prompts that ask Claude to ignore previous instructions defeat the harness's safety rules. State the actual change you need; the structural test and Stop checklist are deterministic and stay enforced."
fi

if [ -z "$REASON" ] \
   && printf '%s' "$LOWER" | grep -qE '(disable|skip|turn off|bypass) (the )?(structural|layer|stop hook|stop check|precompletion|lint|harness:check)'; then
  REASON="Disabling the structural test or Stop checklist is not how the kit is meant to be used. Fix the violation in code, or open an ADR if the layer rule itself needs to change."
fi

if [ -z "$REASON" ] \
   && printf '%s' "$LOWER" | grep -qE 'bypass (the )?(pretooluse|posttooluse|sessionstart|sessionend|precompact|hook|hooks|rules?|checks?)'; then
  REASON="Prompts that ask to bypass kit hooks defeat their purpose. If a specific hook is wrong for your workflow, edit it explicitly with a commit message; do not phrase the request as 'bypass'."
fi

if [ -z "$REASON" ] \
   && printf '%s' "$LOWER" | grep -qE '(remove|delete|wipe|rm -rf|drop) (the )?(\.harness|\.claude)( |/|$|\.)'; then
  REASON="Removing .harness/ or .claude/ deletes the kit's lockfile, structural baseline, skills, agents, and hooks. Use 'agent-harness-kit upgrade' to refresh installed files; do not delete by hand."
fi

if [ -z "$REASON" ] \
   && printf '%s' "$LOWER" | grep -qE 'disableallhooks.*true'; then
  REASON="disableAllHooks: true defeats every protection the kit installs. Remove specific hooks explicitly if needed; do not flip the master switch."
fi

if [ -z "$REASON" ]; then
  exit 0
fi

if [ "${AHK_ALLOW_BYPASS:-}" = "1" ]; then
  mkdir -p .harness
  TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  SHA=$(git rev-parse --short HEAD 2>/dev/null || echo 'no-git')
  ESCAPED_PROMPT=${PROMPT//$'\n'/ }
  ESCAPED_PROMPT=${ESCAPED_PROMPT//\"/\\\"}
  printf '{"ts":"%s","sha":"%s","bypass":"AHK_ALLOW_BYPASS","reason":"%s","prompt":"%s","hook":"UserPromptSubmit"}\n' \
    "$TS" "$SHA" "${REASON//\"/\\\"}" "$ESCAPED_PROMPT" >> .harness/bypass.log
  exit 0
fi

if command -v node >/dev/null 2>&1; then
  node -e "
    const reason = process.argv[1];
    const out = { decision: 'block', reason };
    process.stdout.write(JSON.stringify(out));
  " "$REASON"
elif have_jq; then
  jq -nc --arg r "$REASON" '{decision:"block", reason:$r}'
else
  echo "$REASON" >&2
  exit 2
fi
exit 0
