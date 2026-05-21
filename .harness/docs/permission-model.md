# Skill Permission Model

The kit installs `.harness/permissions.json` and a PreToolUse guard that can
enforce per-skill tool policy.

## Policy Shape

```json
{
  "version": 1,
  "default": {
    "allow": ["Read", "Grep", "Glob", "LS"],
    "deny": ["Bash(git push*)"]
  },
  "skills": {
    "orchestrate": {
      "allow": ["Read", "Bash(node .claude/skills/orchestrate/orchestrate.mjs*)"],
      "deny": ["Write", "Edit", "MultiEdit"]
    }
  }
}
```

## Runtime Behavior

- If no active skill is known, the guard stays silent.
- If an active skill has a matching deny rule, the guard returns a Claude
  `permissionDecision: "deny"` response.
- If an active skill has an allow list and the tool does not match it, the
  guard denies the call.
- `AHK_SKILL_PERMISSIONS_MODE=warn` logs to `.harness/bypass.log` without
  blocking. `AHK_ALLOW_BYPASS=1` does the same for explicit override cases.

The guard reads `AHK_ACTIVE_SKILL` first and can also infer the active skill
from recent `skill_invoked` telemetry rows for the same session.

## Skill Contracts

Each skill directory now carries a `skill.json` contract:

```json
{
  "schemaVersion": 1,
  "id": "orchestrate",
  "name": "orchestrate",
  "version": "1.0.0",
  "capabilities": ["orchestration", "workflow"],
  "permissions": {
    "allow": ["Read", "Bash(node .claude/skills/orchestrate/orchestrate.mjs*)"],
    "deny": ["Write", "Edit", "MultiEdit"]
  }
}
```

`.harness/skill-registry.json` is the install-time registry. Run
`node .harness/scripts/check-skill-contracts.mjs` in an installed project, or
`npm run check:skill-contracts` in this repo, to validate version/capability
metadata, explicit permission declarations, and drift between `.claude`,
`.agents`, and template surfaces.
