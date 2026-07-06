# Story Packet: workflow-concurrency-global-lock

## Description

Implement ADR-0007: a process-wide `asyncio.Semaphore` that serializes workflow
executions triggered through the browser-extension path.

The backend is a single-process asyncio FastAPI service. `ExtensionManager`
maintains only one WebSocket connection per browser type, and
`ExtensionRunner._send_and_wait()` blocks until the extension answers each step.
Running two workflows concurrently therefore races on the single browser
channel and on global state (`_active_runners`, `_step_futures`, `_queues`).

This feature adds a global execution lock with capacity `MAX_CONCURRENT_WORKFLOWS=1`,
queues or fails overlapping run requests, and hardens access to the shared
runner/manager state.

## Acceptance Criteria

- [ ] `GET /api/workflows/{wf_id}/run/extension` acquires a process-wide semaphore
      before entering `run_workflow_extension()`.
- [ ] If the semaphore is free, the request runs immediately.
- [ ] If the semaphore is held, the request waits up to a configurable timeout
      (`WORKFLOW_LOCK_WAIT_SECONDS`, default 30).
- [ ] After timeout, the endpoint returns HTTP 503 with header `Retry-After: 60`
      and body `{"detail": "Workflow execution capacity full. Retry after 60s."}`.
- [ ] A constant `MAX_CONCURRENT_WORKFLOWS` defaults to 1 and is overridable via
      environment variable.
- [ ] All accesses to `ExtensionManager._connections`, `_step_futures`, and
      `ExtensionRunner._active_runners` are protected by `asyncio.Lock` or local
      copies where race conditions exist.
- [ ] Existing pause/resume/stop endpoints still find the runner in `_active_runners`.
- [ ] Lock is released in a `finally` block so a crashed run does not deadlock
      future executions.

## Test Expectations

- [ ] Smoke: start server, call `GET /health`, still returns 200.
- [ ] Smoke: run one workflow via extension path; it completes normally.
- [ ] Manual concurrency: fire two run requests concurrently (e.g. with curl `-d {}`);
      the second receives 503 or waits and succeeds after the first finishes,
      depending on timing. No 500 errors.
- [ ] Structural test passes (`npm run harness:check`).

## Agent Work Units

1. Add semaphore + config
   - Create `src/service/workflow_lock.py` with global semaphore and timeout helpers.
   - Read `MAX_CONCURRENT_WORKFLOWS` / `WORKFLOW_LOCK_WAIT_SECONDS` from env/config.

2. Lock the run endpoint
   - Modify `src/runtime/routers/workflows_router.py::run_workflow_extension_endpoint`
     to acquire the semaphore with timeout and return 503 on timeout.

3. Harden global state
   - Add `asyncio.Lock` around `ExtensionManager._connections` mutations and reads
     in `src/runtime/websocket_manager.py`.
   - Add `asyncio.Lock` around `ExtensionRunner._active_runners` mutations in
     `src/runtime/workflow/extension_runner.py`.

4. Smoke test
   - Start uvicorn, verify single run still works and concurrent second run gets
     503 (or queued).

## Dependencies

- ADR-0007 already accepted.
- Affects `runtime` and `service` layers; requires `architecture-reviewer`.

## Definition of Done

- All acceptance criteria checked.
- `npm run harness:check` passes.
- Smoke test passes.
- `.harness/feature_list.json` updated (`passes: true`).
- Commit created and `.harness/PROGRESS.md` appended.
