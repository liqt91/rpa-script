---
name: create-story
description: Create a Story Packet for normal/high-risk features. Use after /feature-intake classifies work as normal or high-risk, or when the user asks to break a feature into acceptance criteria, test expectations, and agent-sized work units.
allowed-tools: Read, Write, Edit, Bash(node .claude/skills/create-story/create-story.mjs:*)
suggested-turns: 8
---

# Create Story Packet

Turns feature intake output into a concrete `.harness/docs/stories/feature-N.md` Story Packet.

## Steps

1. Run the helper with a title and optional flags:

   ```bash
   node .claude/skills/create-story/create-story.mjs "Feature title" --classification=normal --hours=2
   ```

2. Review the generated Story Packet and fill in missing acceptance criteria if needed.
3. Ensure normal/high-risk features have `storyPath` in `.harness/feature_list.json`.
4. For high-risk work, create or link an ADR and assign a reviewer before implementation.

## Output contract

```markdown
### Story Packet: <feature-id>
### Path: .harness/docs/stories/<feature-id>.md
### Classification: normal|high-risk
### Next step: approve story | add ADR | implement
```

## Anti-patterns

- Do not create Story Packets for tiny typo-level changes.
- Do not prescribe implementation details unless they are hard constraints.
- Do not mark a story approved until acceptance criteria and tests are concrete.
