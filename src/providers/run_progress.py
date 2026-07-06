"""Shared progress queue registry for workflow execution SSE streaming."""

import asyncio
from typing import Optional

_queues: dict[str, asyncio.Queue] = {}
_queues_lock = asyncio.Lock()


async def register(run_id: str, queue: asyncio.Queue) -> None:
    async with _queues_lock:
        _queues[run_id] = queue


async def unregister(run_id: str) -> None:
    async with _queues_lock:
        _queues.pop(run_id, None)


async def get(run_id: str) -> asyncio.Queue | None:
    async with _queues_lock:
        return _queues.get(run_id)
