---
name: eval-rubric-author
description: Use this skill when adding or changing harness eval tasks. Writes deterministic checks first, then optional rubric dimensions with JSON output, so evals grade outcome, process, style, and efficiency without becoming vague prompt feedback.
allowed-tools: Read, Write, Edit, Grep, Glob, Bash(npm run harness:eval:*), Bash(node .harness/scripts/eval-runner-v2.mjs:*)
---

# Eval Rubric Author

## When to use

- Adding a new eval or regression task.
- A task passes even though the agent behavior was bad.
- A model-assisted rubric is needed for process/style judgment after deterministic checks pass.
- The user asks for "rubric", "eval task", "hidden check", or "judge schema".

## Steps

1. Define the behavior being protected in one sentence.
2. Add deterministic outcome checks first: files changed, command output, JSON shape, hidden check, or structural rule.
3. Add rubric dimensions only for what deterministic checks cannot judge:
   - `outcome`
   - `process`
   - `style`
   - `efficiency`
4. Require machine-readable judge output with `passed`, `score`, `reason`, and `evidence`.
5. Add at least one negative fixture or failure example.
6. Run the narrow eval and inspect the JSONL, not just the exit code.

## Rubric JSON shape

```json
{
  "dimension": "process",
  "passed": true,
  "score": 0.9,
  "reason": "The agent inspected the target module before editing.",
  "evidence": ["transcript:tool_call:inspect-module"]
}
```

## Output contract

```markdown
### Eval rubric
**Task:** <task id>
**Deterministic checks:** <list>
**Rubric dimensions:** <list>
**Negative fixture:** <path or n/a>
**Verified:** <command and result>
```

## Anti-patterns

- Do not use a model judge for file existence, command success, or JSON schema checks.
- Do not create a rubric that can pass without evidence.
- Do not update a failing task's expected answer to match bad behavior.
