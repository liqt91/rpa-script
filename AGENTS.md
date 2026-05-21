# rpa_script — Agent Working Notes

rpa_script — solo-dev project on the agent-harness-kit harness. generic/generic project. Single-developer hobby
project. This file is intentionally short — it is a **table of contents**, not
an encyclopedia.

## Build & Run

- Install:    `npm install`
- Dev:        `npm run dev`
- Test:       `npm test`
- Lint:       `npm run lint`
- Structural: `npm run harness:check` (must pass before any PR)

## Architecture (brief)

Layer order, enforced mechanically:

**types → config → repo → service → runtime → ui** — code may only depend forward. Cross-cutting concerns
enter via `providers/`.

Full diagram and rationale: `.harness/docs/architecture.md`.

## Golden principles (must hold)

1. Prefer shared utilities in `src/shared/` over new helpers.
2. Validate at boundaries; never probe data shape "YOLO-style".
3. Each test is end-to-end through one feature in `.harness/feature_list.json`.

Full list: `.harness/docs/golden-principles.md`.

## Where to look (read on demand)

The lines below use Claude Code 2.1+ `@`-imports — Claude loads the file
into context only when this section is referenced, keeping the working
CLAUDE.md tiny.

- @.harness/docs/architecture.md      — when adding a new module or moving code.
- @.harness/docs/adr/                 — when changing public APIs.
- @.harness/docs/golden-principles.md — before any refactor.
- @.harness/feature_list.json         — before claiming a feature is done.
- @.harness/project/state.json        — before changing phase, MVP scope, risks, or checklists.
- `.harness/memory/current-summary.md` — compact shared project memory injected by SessionStart.
- `.harness/PROGRESS.md`     — read at session start; append at session end (kit-managed, not @-imported).

## Skills you should use

- `/inspect-module <path>`            when you need to understand existing code.
- `/add-feature <description>`        when adding new capability — never freestyle.
- `/structural-test-author <layer>`   when adding a new structural rule.
- `/garbage-collection`               every Friday or before tagging a release.
- `/eval-runner`                      before merging any change to a skill or agent file.
- `/deliver-html`                     when user wants an analysis / audit / plan / decision doc / next-actions report — HTML for humans, MD stays for agent files (principle #11).
- `/remember-project`                 when a decision, risk, scope change, or handoff note must survive future sessions.
- `/project-status`                   when the user needs a phase/MVP/checklist/risk/status dashboard.

## Subagents you should delegate to (do NOT inline these reviews)

- `architecture-reviewer` — for any cross-layer change.
- `security-reviewer`     — for any auth, input handling, or secret-touching change.
- `reliability-reviewer`  — for any new error path, retry loop, or async boundary.

## Workflow contract

1. Start session: run `/inspect-module .`, read `.harness/PROGRESS.md`, and keep `.harness/project/state.json` aligned with the active work.
2. Pick ONE feature from `.harness/feature_list.json` whose `passes: false`.
3. Implement. Run the structural test. If it fails, FIX before continuing.
4. Self-verify with the matching reviewer subagent(s).
5. Commit with descriptive message. Append a line to `.harness/PROGRESS.md`.
6. Update `.harness/feature_list.json` (`passes: true`) **only after** end-to-end test passes.

## What NOT to do

- Don't add a new layer without an ADR.
- Don't npm install packages with native bindings without an ADR.
- Don't disable the structural test to make a PR pass.
- Don't write code that the structural test cannot reason about (no dynamic
  imports across layers).
- Don't update CLAUDE.md without proposing a harness improvement
  (`/propose-harness-improvement`).
- Don't grow CLAUDE.md past 200 instructions — Stop hook blocks the stop on
  overflow (HumanLayer measurement). Excess belongs in `.harness/docs/` or @-imports.
