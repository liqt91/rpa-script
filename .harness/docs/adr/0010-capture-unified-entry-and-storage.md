# ADR 0010 — Element capture unified entry and two-dimensional storage

- **Status:** accepted
- **Date:** 2026-08-06
- **Deciders:** project owner

## Context

Element capture has historically spread across multiple entry points and
storage shapes:

- The workflow editor exposed four capture buttons (网页 guide, 桌面 Win32
  picker, UIA picker, and a unified 工具 tool). Only the last one, the unified
  GUI tool (`CaptureToolModal` → `POST /api/commands/gui-picker` →
  `scripts/capture_gui/capture_once.py`), covers all channels.
- The unified tool saved a raw `ElementInfo` dict into the `attributes` column,
  which broke three consumers:
  1. Web elements never populated the `web_selector` column, so the runtime
     emitter could not locate them.
  2. Desktop elements stored `win32_path`/`uia_path`, but the runtime commands
     (`pickFromPathWin32`, `pickElementUia`) read `attributes.path`.
  3. UIA-capable desktop captures were always stored as Win32 (`element_kind`),
     losing the UIA designation.
- The GUI browser-capture mapping misread the extension payload
  (`path`→`domPath`, `attrs`→`features`, missing `listFamily`/`pageUrl`), so
  DOM-path editing, attributes, list metadata, and page URL were empty for web
  captures.
- Legacy entry points (`/api/commands/picker`, `/api/commands/picker_uia`,
  `scripts/picker.py`, `scripts/picker_uia.py`, the `/capture` web page +
  `capture_router.py`, `data/captured_elements.json`) existed in parallel with
  the unified tool and stored their own incompatible `attributes.path` shapes.

## Decision

**Make the element-library 工具 button the single capture entry and adopt a
two-dimensional storage model on `workflow_elements`.**

### Two-dimensional discrimination

- `element_kind` is narrowed back to its ADR-0006 web-structural semantics
  `{plain, anchor, child}`.
- A new `element_type` column (`{web, win32, uia}`, default `web`) records the
  capture channel. Desktop elements always use `element_kind='plain'`.

### Unified `attributes` contract (desktop)

The canonical key consumed by runtime commands is `attributes.path`:

- `element_type='win32'`: `path` = Win32 ancestor chain
  `[{hwnd, class_name, title, rect}, ...]`; plus `hwnd/class_name/title/rect`.
- `element_type='uia'`: `path` = UIA ancestor chain
  `[{name, class_name, control_type, automation_id, rect}, ...]`; plus
  `name/class_name/control_type/automation_id/rect`.

### Every element captures an image

Image is **not** a separate element type. All channels store a visual snapshot
in the existing `screenshot` column plus image-fallback metadata in
`attributes` (`region`, `threshold`=0.8, `match_method`="template",
`screen_size`). This feeds a future image-based fallback tier without a new
type.

### Normalization at the boundary

`elements_service.normalize_element_capture()` runs inside the
`create`/`update` element endpoints whenever `attributes` looks like an
`ElementInfo` capture payload. It fills `web_selector`/candidates/`dom_path` for
web, chooses `uia` vs `win32` from whether the UIA chain is meaningful, rewrites
`attributes.path`, and preserves `screenshot` + image metadata.

### Removals

- Frontend: 网页/桌面/UIA buttons and the guide modal, the unused browser
  selector, the 图像库 tab, the dead `handlePicker` in `Toolbar`, and the
  `runPicker`/`runPickerUia` API helpers.
- Backend: `/api/commands/picker`, `/api/commands/picker_uia` endpoints;
  `scripts/picker.py`, `scripts/picker_uia.py`; `capture_router.py`,
  `static/capture.html`, and their `main.py` registration; the legacy
  `data/captured_elements.json`. The standalone tkinter GUI
  (`scripts/capture_gui/main.py`) is kept and uses its own JSON store.

## Consequences

Positive:
- One capture path produces data every runtime consumer understands.
- The editor UI exposes a single, discoverable capture entry.
- Desktop UIA elements are correctly classified again.
- Every element carries an image snapshot for future fallback without a new
  storage table.

Negative:
- Database migration (014) is required; legacy `element_kind` values are
  rewritten during migration.
- The unified tool now depends on Pillow for desktop region screenshots.
- Removing the legacy endpoints is a public API change for anything that
  referenced them (none found in-repo).

## Alternatives considered

- **Keep a single `element_kind` field with five values.** Rejected: mixes the
  orthogonal dimensions of capture channel and web structural role, and the
  runtime already distinguishes them.
- **Make image a separate `element_type='image'`.** Rejected by the project
  owner: image is captured for every element rather than being its own kind.
- **Normalize only in the frontend modal.** Rejected: boundary validation
  belongs in the backend so every future capture path stays consistent.
