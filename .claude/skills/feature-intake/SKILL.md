---
name: feature-intake
description: Use this skill whenever the user asks to "add a feature", "implement X", "build Y", or before invoking /add-feature. Classifies the request into tiny/normal/high-risk based on estimated complexity and blast radius, then routes to the appropriate workflow — straight to code (tiny), story packet (normal), or ADR + story packet + mandatory review (high-risk). Prevents "wrong direction" sessions by forcing a pause before implementation. Pattern from harness-experimental and OpenAI's "implementation prompts do not go straight to code" discipline.
allowed-tools: Read, Write, Edit, Bash(node .claude/skills/feature-intake/scripts/classify.mjs:*)
suggested-turns: 6
---

## When to use

- User asks to implement a feature, add functionality, or build something new
- Before running `/add-feature` on a new item
- When you're about to start coding and haven't assessed risk yet
- User mentions "add", "implement", "build", "create" followed by a feature description

## Steps

1. **Run the classifier.** Pass the feature description to the deterministic classifier:

   ```bash
   node .claude/skills/feature-intake/scripts/classify.mjs "feature description here"
   ```

   Returns JSON: `{ classification: "tiny"|"normal"|"high-risk", reasoning: "...", estimatedHours: N, signals: [...] }`

2. **Review classification with user.** Present the classification and reasoning. Ask if they agree or want to override.

3. **Route based on classification:**

   **Tiny (< 30 min):**
   - Add to `.harness/feature_list.json` with `classification: "tiny"`
   - Proceed directly to implementation
   - No ceremony required

   **Normal (< 4h):**
   - Create story packet in `.harness/docs/stories/` using the template
   - Add to `.harness/feature_list.json` with `classification: "normal"` and link to story
   - Story must include: description, acceptance criteria, test expectations
   - Proceed to implementation after story is approved

   **High-risk (> 4h or breaking change):**
   - Create ADR in `.harness/docs/adr/` (use `/add-adr` skill)
   - Create story packet in `.harness/docs/stories/`
   - Add to `.harness/feature_list.json` with `classification: "high-risk"`
   - Assign appropriate reviewer (security-reviewer for auth/permissions, architecture-reviewer for structural changes, etc.)
   - Wait for ADR + story approval before implementation

4. **Update .harness/feature_list.json.** Add the feature with proper classification metadata:

   ```json
   {
     "id": "feature-N",
     "title": "...",
     "classification": "tiny|normal|high-risk",
     "estimatedHours": N,
     "storyPath": ".harness/docs/stories/feature-N.md",
     "adrPath": ".harness/docs/adr/NNNN-title.md",
     "assignedReviewer": "security-reviewer",
     "status": "intake-complete"
   }
   ```

5. **Proceed to next phase.** For tiny: implement. For normal/high-risk: wait for approval.

## Output contract

```
### Feature Intake: <title>
### Classification: <tiny|normal|high-risk>
### Estimated hours: <N>
### Reasoning: <why this classification>
### Next steps:
- [ ] <action 1>
- [ ] <action 2>
```

## Anti-patterns

- Don't skip classification and go straight to code — that's the failure mode this skill prevents
- Don't over-classify tiny tasks as normal — ceremony has a cost
- Don't under-classify breaking changes as normal — missing ADR creates tech debt
- Don't implement high-risk features without reviewer assignment — that's the safety net

## Classification signals

**Tiny indicators:**
- Single file edit
- < 50 lines of code
- No new dependencies
- No breaking changes
- No security implications
- Clear, well-understood pattern

**High-risk indicators:**
- Breaking API changes
- Authentication/authorization changes
- Database schema changes
- New external dependencies
- Cross-cutting concerns (logging, error handling)
- Performance-critical paths
- > 4 hours estimated
- Affects multiple layers/domains
- Security-sensitive (auth, permissions, secrets, PII)

**Normal:** Everything else
