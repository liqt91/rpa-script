"""
Public API router — trigger workflows via API key.
No JWT session required; uses X-API-Key header.
"""

import asyncio
import json
import os
import uuid as _uuid
import datetime as _dt

from fastapi import APIRouter, Header, HTTPException, Body, Query, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.repo import runtime_models as models
from src.runtime.workflow.extension_runner import run_workflow_extension
from src.providers import run_progress
from src.providers.workflow_lock import (
    WorkflowConcurrencyError,
    workflow_lock,
)

router = APIRouter(prefix="/api/public", tags=["public"])


def get_db():
    db = models.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _verify_api_key(db: Session, wf_id: int, api_key: str) -> models.Workflow:
    """Validate API key and return the workflow. Raises HTTPException on failure."""
    if not api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header required")
    wf = db.get(models.Workflow, wf_id)
    if not wf or not wf.api_enabled or wf.api_key != api_key:
        raise HTTPException(status_code=401, detail="Invalid API key or workflow not API-enabled")
    return wf


@router.post("/trigger/{wf_id}")
async def trigger_workflow(
    wf_id: int,
    payload: dict = Body(default={}),
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    """Trigger a workflow execution by API key. Returns run_id immediately."""
    wf = _verify_api_key(db, wf_id, x_api_key)

    nodes = (
        db.query(models.WorkflowNode)
        .filter(models.WorkflowNode.workflow_id == wf_id)
        .order_by(models.WorkflowNode.order)
        .all()
    )
    for n in nodes:
        if n.extra and isinstance(n.extra, str):
            try:
                n.extra = json.loads(n.extra)
            except Exception:
                n.extra = {}

    parameters = payload.get("parameters") or {}
    webhook_url = (payload.get("webhook_url") or "").strip()
    run_id = f"api_{_uuid.uuid4().hex[:12]}"
    started_at = _dt.datetime.now()

    # Check concurrency before firing
    from src.providers.workflow_lock import current_workflow_lock_capacity
    if current_workflow_lock_capacity() <= 0:
        raise HTTPException(
            status_code=503,
            detail="Workflow execution capacity full. Please retry later.",
        )

    # Fire-and-forget: run in background
    async def _run_bg():
        nonlocal started_at
        try:
            async with workflow_lock():
                result = await run_workflow_extension(
                    wf, nodes,
                    run_id=run_id,
                    initial_parameters=parameters,
                    trigger_type="api",
                )
        except Exception as e:
            result = {"runId": run_id, "success": False, "error": str(e)}

        completed_at = _dt.datetime.now()

        # Save run log
        bg_db = models.SessionLocal()
        try:
            log = models.Result(
                task_id=None,
                workflow_id=wf_id,
                run_id=result.get("runId", run_id),
                url=wf.url or "",
                total=result.get("completedSteps", 0),
                data=json.dumps({
                    "workflow_id": wf_id,
                    "mode": "extension",
                    "success": result.get("success"),
                    "total_steps": result.get("totalSteps"),
                    "failed_steps": result.get("failedSteps"),
                    "error": result.get("error"),
                    "outputs": result.get("outputs", {}),
                }),
                trigger_type="api",
                log_dir=result.get("logDir", ""),
                started_at=started_at,
                completed_at=completed_at,
            )
            bg_db.add(log)
            bg_db.commit()
        except Exception as e:
            print(f"[PublicRouter] failed to save run log: {e}")
        finally:
            bg_db.close()

        # Fire webhook callback
        if webhook_url:
            _schedule_webhook(webhook_url, result, wf_id, run_id, started_at, completed_at)

    asyncio.create_task(_run_bg())

    return {
        "run_id": run_id,
        "workflow_id": wf_id,
        "status": "started",
        "sse_url": f"/api/public/stream/{run_id}",
        "result_url": f"/api/public/result/{run_id}",
    }


@router.get("/stream/{run_id}")
async def stream_run_progress(
    run_id: str,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """SSE endpoint to stream workflow execution progress."""
    if not run_id.startswith("api_"):
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_stream():
        queue = await run_progress.get(run_id)
        if queue is None:
            yield f"data: {json.dumps({'type': 'done', 'success': False, 'error': 'Run not active or already completed'})}\n\n"
            return
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                    continue
                if msg is None:
                    break
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("type") in ("done", "stepError"):
                    break
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/result/{run_id}")
async def get_run_result(
    run_id: str,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    """Query the result of a workflow execution."""
    log = (
        db.query(models.Result)
        .filter(models.Result.run_id == run_id)
        .first()
    )
    if not log:
        raise HTTPException(status_code=404, detail="Run not found")
    wf = db.get(models.Workflow, log.workflow_id)
    if not wf or not wf.api_enabled or wf.api_key != x_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key or workflow not API-enabled")

    d = json.loads(log.data) if log.data else {}
    return {
        "run_id": log.run_id,
        "workflow_id": log.workflow_id,
        "success": d.get("success"),
        "outputs": d.get("outputs", {}),
        "error": d.get("error"),
        "total_steps": d.get("total_steps", 0),
        "completed_steps": log.total,
        "started_at": log.started_at.isoformat() if log.started_at else None,
        "completed_at": log.completed_at.isoformat() if log.completed_at else None,
    }


def _schedule_webhook(webhook_url: str, result: dict, wf_id: int, run_id: str,
                       started_at, completed_at):
    """Fire webhook callback in background with one retry."""
    import httpx

    async def _do():
        payload = {
            "event": "workflow.completed",
            "run_id": run_id,
            "workflow_id": wf_id,
            "success": result.get("success"),
            "outputs": result.get("outputs", {}),
            "table_data": {
                "columns": result.get("tableColumns", []),
                "rows": result.get("tableRows", []),
            },
            "error": result.get("error"),
            "started_at": started_at.isoformat() if started_at else None,
            "completed_at": completed_at.isoformat() if completed_at else None,
        }
        for attempt in (1, 2):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(webhook_url, json=payload)
                    if resp.status_code < 400:
                        print(f"[PublicRouter] webhook success: {webhook_url}")
                        return
                    print(f"[PublicRouter] webhook attempt {attempt} got {resp.status_code}")
            except Exception as e:
                print(f"[PublicRouter] webhook attempt {attempt} failed: {e}")
        print(f"[PublicRouter] webhook final failure for {webhook_url}")

    try:
        asyncio.ensure_future(_do())
    except Exception as e:
        print(f"[PublicRouter] webhook schedule error: {e}")
