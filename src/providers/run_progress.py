"""Shared progress queue registry for workflow execution SSE streaming."""

import asyncio

_queues: dict[str, asyncio.Queue] = {}


def register(run_id: str, queue: asyncio.Queue) -> None:
    _queues[run_id] = queue


def unregister(run_id: str) -> None:
    _queues.pop(run_id, None)


def get(run_id: str) -> asyncio.Queue | None:
    return _queues.get(run_id)
