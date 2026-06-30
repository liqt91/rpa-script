---
name: harness-improvement-loop
description: Use this skill after a trace-backed agent failure or repeated harness friction. Turns the failure into a ranked harness change, records a prediction, applies the smallest prevention, and reruns the relevant eval/regression gate. This is the agent-harness-kit AHE-lite loop.
allowed-tools: Read, Write, Edit, Grep, Glob, Bash(git diff:*), Bash(npm run harness:eval:*), Bash(node .harness/scripts/harness-report.mjs:*), Bash(node .harness/scripts/regression-runner.mjs:*)
---

# Harness Improvement Loop

## When to use

- `/trace-analyzer` found a durable harness failure.
- A skill, hook, agent, or eval needs to change because the same mistake can recur.
- The user asks to "make the harness learn from this", "AHE-lite", or "prevent this next time".

## Steps

1. Read the trace analysis and name the smallest prevention target.
2. Write a prediction record before editing:
   `.harness/improvements/<YYYYMMDD-HHMM>-<slug>.json`
3. Include these fields:
   - `failureClass`
   - `preventionTarget`
   - `expectedMetric`
   - `expectedDirection`
   - `baselineEvidence`
   - `verificationCommand`
4. Apply the smallest change in one place: skill, hook, subagent, deterministic script, eval task, or docs.
5. Run the matching verification command. Prefer the narrow eval first, then a broader regression run if the change touches shared harness behavior.
6. Append the observed result to the prediction record.

## Prediction record shape

```json
{
  "failureClass": "missing-context",
  "preventionTarget": "skill",
  "expectedMetric": "task pass rate",
  "expectedDirection": "increase",
  "baselineEvidence": ".harness/eval/results/latest.jsonl",
  "verificationCommand": "npm run harness:eval -- --quick --transport=mock",
  "observedResult": null
}
```

## Output contract

```markdown
### Harness improvement
**Failure class:** <class>
**Changed:** <file list>
**Prediction:** <metric direction>
**Verified:** <command and result>
**Remaining risk:** <known gap or none>
```

## Anti-patterns

- Do not change a broad prompt when a deterministic script or eval can prevent the issue.
- Do not mark the improvement successful without recording observed results.
- Do not bundle unrelated harness improvements into one loop.
