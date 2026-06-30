---
name: propose-harness-improvement
description: Use this skill whenever the agent makes a mistake, the user observes an avoidable failure, a pattern recurs, or someone says "the agent keeps doing X". Files an "Engineer the Harness" entry — Mitchell Hashimoto's discipline: every failure becomes a permanent prevention mechanism. Always invoke this instead of just fixing the immediate symptom.
allowed-tools: Read, Edit, Write, Bash(git diff:*)
suggested-turns: 8
---

## Steps

1. **Triage.** Ask: "What just went wrong? What was the agent's intended
   behavior? What's the symptom?"
2. **Classify.** One of:
   - **(a) Missing context** — the agent didn't know something. Fix: add to
     `.harness/docs/`.
   - **(b) Missing rule** — the agent did something forbidden by an
     unwritten rule. Fix: invoke `/structural-test-author`.
   - **(c) Missing tool/skill** — the agent reached for the wrong tool. Fix:
     invoke `/write-skill`.
   - **(d) Wrong layer / architecture** — the structure invited the
     mistake. Fix: write an ADR via `/add-adr`.
   - **(e) Wrong instruction in prompt** — the failure traces back to a
     skill/agent prompt that was ambiguous, misleading, or under-constrained.
     The agent followed the prompt correctly but the prompt itself led astray.
     Fix: edit the offending file under `.claude/skills/<name>/SKILL.md` or
     `.claude/agents/<name>.md`. Re-run `/eval-runner` afterward to confirm
     the regression is closed.
3. **Append entry** to `.harness/docs/agent-failures.md` with: date, symptom, fix,
   fix-type, file modified.
4. **Apply the fix in the right place.** NEVER paper over with a CLAUDE.md
   "be careful" sentence unless rule (a) applies — and even then, only as a
   pointer to a longer doc.
5. **Update PROGRESS.** Append `harness-improvement: <slug>` to
   `.harness/PROGRESS.md`.

## Output contract

```
### Failure: <one-line summary>
### Classification: (a|b|c|d) <name>
### Fix applied at: <file:line>
### .harness/docs/agent-failures.md entry: §<n>
```

## Anti-patterns (block on these)

- Don't add a vague "be careful with X" sentence to CLAUDE.md.
- Don't add a rule whose enforcement is also LLM-based.
- Don't use this skill to log unrelated cleanup ideas — those go in
  `.harness/docs/tech-debt-tracker.md`.
