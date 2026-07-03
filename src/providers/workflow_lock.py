"""Process-wide concurrency lock for workflow execution (ADR-0007)."""

import asyncio
from contextlib import asynccontextmanager

from src.config import settings

MAX_CONCURRENT_WORKFLOWS: int = settings.MAX_CONCURRENT_WORKFLOWS
WORKFLOW_LOCK_TIMEOUT_SECONDS: float = settings.WORKFLOW_LOCK_TIMEOUT_SECONDS


class WorkflowConcurrencyError(Exception):
    """Raised when a workflow run cannot acquire the global concurrency lock."""

    def __init__(self, message: str = "Workflow execution capacity full"):
        super().__init__(message)


_workflow_semaphore = asyncio.Semaphore(MAX_CONCURRENT_WORKFLOWS)


@asynccontextmanager
async def workflow_lock(timeout: float = WORKFLOW_LOCK_TIMEOUT_SECONDS):
    """Acquire the global workflow concurrency lock, or raise WorkflowConcurrencyError."""
    acquired = False
    try:
        acquired = await asyncio.wait_for(_workflow_semaphore.acquire(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise WorkflowConcurrencyError(
            f"Could not acquire workflow lock within {timeout}s"
        ) from exc

    if not acquired:
        raise WorkflowConcurrencyError("Could not acquire workflow lock")

    try:
        yield
    finally:
        if acquired:
            _workflow_semaphore.release()


def current_workflow_lock_capacity() -> int:
    """Return the number of additional workflow runs that can start immediately."""
    return _workflow_semaphore._value  # type: ignore[attr-defined]
