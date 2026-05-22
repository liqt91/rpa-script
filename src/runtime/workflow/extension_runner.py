"""
Extension Runner — executes a workflow via the browser extension over WebSocket.

Flows:
    1. Convert nodes to instruction sequence via extension_emitter
    2. Iterate instructions, send each to extension via ext_manager
    3. Wait for stepResult / stepError (with timeout)
    4. Implement retry logic based on extra.onError / retryCount
    5. Collect results into a report
"""

import asyncio
import logging
from typing import Any

from src.runtime.websocket_manager import ext_manager
from .extension_emitter import build_instructions
from src.repo import runtime_models as models

logger = logging.getLogger(__name__)

DEFAULT_STEP_TIMEOUT = 30.0


class ExtensionRunner:
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.results: list[dict] = []
        self.completed = 0
        self.failed_step: dict | None = None

    async def run(self, wf: models.Workflow, nodes: list[models.WorkflowNode]) -> dict:
        """Run workflow nodes through the extension. Returns execution report."""
        instructions = build_instructions(nodes)
        logger.info(f"[ExtensionRunner] wf={wf.id} steps={len(instructions)} client={self.client_id}")

        for instr in instructions:
            success = await self._execute_instruction(instr)
            if not success:
                break

        return {
            "success": self.failed_step is None,
            "completedSteps": self.completed,
            "totalSteps": len(instructions),
            "failedStep": self.failed_step,
            "results": self.results,
        }

    async def _execute_instruction(self, instr: dict) -> bool:
        step_id = instr["stepId"]
        extra = instr.get("extra") or {}
        on_error = extra.get("onError", "stop")
        retry_count = extra.get("retryCount", 0)
        timeout = extra.get("timeout", DEFAULT_STEP_TIMEOUT)

        last_error = None
        for attempt in range(retry_count + 1):
            try:
                result = await self._send_and_wait(step_id, instr, timeout)
                self.results.append({"stepId": step_id, "status": "success", "result": result})
                self.completed += 1
                return True
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[ExtensionRunner] {step_id} attempt {attempt + 1}/{retry_count + 1} failed: {e}")
                if attempt < retry_count:
                    await asyncio.sleep(1.0)

        # All retries exhausted
        self.failed_step = {"stepId": step_id, "instruction": instr, "error": last_error}
        self.results.append({"stepId": step_id, "status": "error", "error": last_error})

        if on_error == "stop":
            return False
        elif on_error == "continue":
            self.completed += 1
            return True
        else:
            return False

    async def _send_and_wait(self, step_id: str, instr: dict, timeout: float) -> Any:
        """Send executeStep to extension and wait for result."""
        conn = ext_manager.get_connection(self.client_id)
        if not conn:
            raise RuntimeError(f"Extension {self.client_id} is not connected")

        ok = await ext_manager.send_to(self.client_id, "executeStep", {"stepId": step_id, **instr})
        if not ok:
            raise RuntimeError(f"Failed to send step {step_id} to extension")

        resp = await ext_manager.await_step_result(step_id, timeout=timeout)
        if resp["status"] == "error":
            raise RuntimeError(resp.get("error", "Unknown extension error"))
        return resp.get("result")


async def run_workflow_extension(wf: models.Workflow, nodes: list[models.WorkflowNode],
                                  client_id: str | None = None) -> dict:
    """
    Convenience entry point.
    If client_id is None, picks the first online extension.
    """
    if not ext_manager.is_any_online:
        return {"success": False, "error": "没有在线的浏览器扩展，请先安装并启用扩展"}

    target = client_id
    if not target:
        # Pick first available connection
        conns = list(ext_manager._connections.keys())
        if not conns:
            return {"success": False, "error": "没有可用的浏览器扩展连接"}
        target = conns[0]

    runner = ExtensionRunner(target)
    return await runner.run(wf, nodes)
