#!/usr/bin/env bash
# PostToolUse hook — runs the structural test on the file just edited.
# Defensive: never blocks on missing tooling. Exit code 2 = block + Claude reads stderr.
#
# `pipefail` is critical — without it, `cmd | tail` swallows cmd's exit code
# and a real structural-test failure looks clean to the agent.
set -eo pipefail

INPUT=$(cat)

# Resolve where this hook lives so we can find _lib/json-pick.mjs (Node-based
# jq fallback). Pure-Node fallback removes the previous fail-open behaviour
# when jq is missing — silently skipping the structural check on jq-less
# environments (minimal CI, Windows without WSL+brew) was a known audit hole.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
_LIB_DIR="$SCRIPT_DIR/_lib"
. "$_LIB_DIR/jp.sh"
if ! have_jp; then
  echo "[ahk] structural-test-on-edit: no JSON parser available (need jq OR node + .harness/scripts/_lib/json-pick.mjs)." >&2
  exit 0
fi

FILE=$(echo "$INPUT" | jp '.tool_input.file_path // empty')
[ -z "$FILE" ] && exit 0

# Only run on source files, and only inside the configured roots.
case "$FILE" in
  *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs)  ENGINE=ts ;;
  *.py)                               ENGINE=py ;;
  *.go)                               ENGINE=go ;;
  *.rs)                               ENGINE=node ;;
  *.swift)                            ENGINE=node ;;
  *.kt|*.kts)                         ENGINE=node ;;
  *)                                  exit 0 ;;
esac

# Allow opt-out via env var — useful on Windows / macOS where some hook
# events are flaky (open issues #45065 and #6305).
if [ "${AHK_HOOK_MODE:-}" = "warn" ]; then
  echo "[ahk] hook running in warn-only mode (AHK_HOOK_MODE=warn)" >&2
  exit 0
fi

# Skip cleanly when the structural test is explicitly disabled (polyglot
# scaffolds where the adapter is not yet wired). Without this guard every
# edit fires a failing hook that the agent can't actually fix.
if [ -f .harness/config.json ] \
   && grep -qE '"engine"[[:space:]]*:[[:space:]]*"none"' .harness/config.json; then
  exit 0
fi

# Run the structural test scoped to this file. Capture output so we can
# return only the relevant lines via stderr to Claude.
if [ "$ENGINE" = "ts" ]; then
  if ! npm run --silent harness:check -- --file "$FILE" 2>&1 | tail -50 >&2; then
    cat >&2 <<EOF

Structural test failed for $FILE.
Layer order: see .harness/config.json.
Run \`npm run harness:check\` for full output.
Fix the violation before continuing — do NOT disable the test.
EOF
    exit 2
  fi
elif [ "$ENGINE" = "py" ]; then
  if [ ! -f .harness/runners/structural_test.py ]; then
    exit 0
  fi
  if ! python .harness/runners/structural_test.py --file "$FILE" 2>&1 | tail -50 >&2; then
    cat >&2 <<EOF

Structural test failed for $FILE.
Layer order: see .harness/config.json.
Run \`python .harness/runners/structural_test.py\` for full output.
Fix the violation before continuing — do NOT disable the test.
EOF
    exit 2
  fi
elif [ "$ENGINE" = "go" ]; then
  if [ ! -f .harness/runners/structural_check.go ]; then
    exit 0
  fi
  if ! go run .harness/runners/structural_check.go --file "$FILE" 2>&1 | tail -50 >&2; then
    cat >&2 <<EOF

Structural test failed for $FILE.
Layer order: see .harness/config.json.
Run \`go run .harness/runners/structural_check.go\` for full output.
Fix the violation before continuing — do NOT disable the test.
EOF
    exit 2
  fi
elif [ "$ENGINE" = "node" ]; then
  # Node-based adapters (Rust / Swift / Kotlin). All ship the same
  # .harness/runners/structural-check.mjs entry point. Workspace-wide scan because
  # the regex is cheap. Missing script → graceful degrade.
  if [ ! -f .harness/runners/structural-check.mjs ]; then
    exit 0
  fi
  if ! node .harness/runners/structural-check.mjs 2>&1 | tail -50 >&2; then
    cat >&2 <<EOF

Structural test failed (triggered by edit to $FILE).
Layer order: see .harness/config.json.
Run \`node .harness/runners/structural-check.mjs\` for full output.
Fix the violation before continuing — do NOT disable the test.
EOF
    exit 2
  fi
fi
exit 0
