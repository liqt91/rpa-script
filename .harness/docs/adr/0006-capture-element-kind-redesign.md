# ADR 0006 — Capture element kind redesign

- **Status:** accepted
- **Date:** 2026-07-01
- **Deciders:** project owner

## Context

The side panel currently exposes two capture tabs: "捕获新元素" (capture new element) and "捕获子元素" (capture child element). The backend, however, treats a child element as an ordinary element that happens to carry relative-selector fields. There is no explicit marker distinguishing:

- a plain global element,
- an element intended as a loop anchor,
- a child element captured relative to an anchor.

This ambiguity forces the exporter and runtime to infer semantics from indirectly related fields such as `anchor_element_name`, which is brittle and makes validation impossible at the boundary. Meanwhile, the front end has two partially overlapping controls for the same anchor context (`activeAnchorSelect` at the top and the anchor card below), and switching candidates in child mode does not automatically recompute the relative selector.

## Decision

Introduce an explicit `element_kind` column on `WorkflowElement` with values `{plain, anchor, child}` and make child capture an anchor-first workflow.

- **Backend**
  - Add `WorkflowElement.element_kind` (`String(16)`, default `"plain"`).
  - Keep `relative_selector`, `anchor_selector`, `anchor_element_name`, and `anchor_mode`.
  - Reduce `anchor_mode` to `{none, anchor-first, manual}`. Map legacy values `auto` → `anchor-first` and `backfill` → `manual` in a migration.
  - Validate at save time: a `child` element must reference an existing `anchor` element by name within the same workflow.

- **Front end**
  - "捕获新元素" produces global selectors and saves `element_kind` as `plain` or `anchor` (user can mark an anchor).
  - "捕获子元素" requires a selected `activeAnchor` before capture, highlights anchor instances persistently, and computes the relative selector at capture time.
  - In child mode, candidate/family changes automatically recompute the relative selector (`anchor-first`); manual edits of the relative input mark the mode as `manual`.
  - The global selector becomes a collapsible fallback for child elements.

- **Runtime / exporter**
  - Route resolution by `element_kind`:
    - `anchor` and `plain` use the global selector.
    - `child` resolves the anchor element by name, then evaluates the relative selector inside each anchor instance.

## Consequences

Positive:
- Clear data model: the runtime no longer guesses whether an element is a child.
- Stronger validation: impossible to save a child without a valid anchor reference.
- Better UX: child capture is consistently anchored; relative selectors stay in sync with chosen candidates.

Negative:
- Requires a database migration and front-end state changes in one coordinated change.
- Existing captured elements must be classified during migration; ambiguous rows default to `plain` and can be reclassified manually.

## Alternatives considered

- **Keep the current implicit model and only improve the UI.** Rejected because the exporter/runtime still cannot distinguish anchor/child semantics reliably, and validation remains weak.
- **Use `anchor_mode` alone to encode child status.** Rejected because `anchor_mode` already mixes provenance (`manual` vs `auto`) and intent; overloading it with element type would make the field harder to reason about and impossible to validate mechanically.
