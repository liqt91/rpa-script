"""Process-wide workflow execution lock.

ADR-0007: a single asyncio.Semaphore serializes browser-extension workflow runs
because ExtensionManager maintains only one WebSocket connection per browser
type and ExtensionRunner._send_and_wait() is synchronous within a run.
"""

import asyncio
import os
from contextlib import asynccontextmanager

MAX_CONCURRENT_WORKFLOWS = int(os.environ.get("MAX_CONCURRENT_WORKFLOWS", "1"))
WORKFLOW_LOCK_WAIT_SECONDS = float(os.environ.get("WORKFLOW_LOCK_WAIT_SECONDS", "30"))

_workflow_lock = asyncio.Semaphore(MAX_CONCURRENT_WORKFLOWS)


@asynccontextmanager
async def workflow_lock(timeout: float = WORKFLOW_LOCK_WAIT_SECONDS):
    """Acquire the global workflow lock; raise TimeoutError if unavailable."""
    try:
        await asyncio.wait_for(_workflow_lock.acquire(), timeout=timeout)
    except asyncio.TimeoutError:
        raise
    try:
        yield
    finally:
        _workflow_lock.release()


def workflow_lock_capacity() -> int:
    """Return configured maximum concurrent workflows."""
    return MAX_CONCURRENT_WORKFLOWS
