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
import re
from typing import Any

from src.runtime.websocket_manager import ext_manager
from .extension_emitter import build_instructions
from .commands import COMMAND_REGISTRY
from src.providers import run_progress
from src.repo import runtime_models as models

logger = logging.getLogger(__name__)

DEFAULT_STEP_TIMEOUT = 30.0

_VAR_PLACEHOLDER_RE = re.compile(r"\$\{(\w+)\}|\{\{(\w+)\}\}")



def _is_local_command(cmd_type: str) -> bool:
    """Return True if the command should be handled locally (backend) rather than sent to extension."""
    cmd = COMMAND_REGISTRY.get(cmd_type)
    if not cmd:
        return False
    return cmd.get("runtimes", {}).get("extension", {}).get("local", False)

class ExtensionRunner:
    def __init__(self, client_id: str, run_id: str | None = None):
        self.client_id = client_id
        self.run_id = run_id or f"run_{id(self)}"
        self.vars: dict[str, Any] = {}
        self.results: list[dict] = []
        self.completed = 0
        self.failed_step: dict | None = None
        self.queue = asyncio.Queue()
        run_progress.register(self.run_id, self.queue)

    async def _emit(self, event: dict) -> None:
        try:
            await asyncio.wait_for(self.queue.put(event), timeout=1.0)
        except Exception:
            pass

    async def run(self, wf: models.Workflow, nodes: list[models.WorkflowNode]) -> dict:
        """Run workflow nodes through the extension. Returns execution report."""
        instructions = build_instructions(nodes)
        logger.info(f"[ExtensionRunner] wf={wf.id} steps={len(instructions)} client={self.client_id} run_id={self.run_id}")

        try:
            for instr in instructions:
                await self._emit({
                    "type": "stepStart",
                    "stepId": instr.get("stepId"),
                    "nodeId": instr.get("nodeId"),
                })
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
        finally:
            await self._emit({
                "type": "done",
                "success": self.failed_step is None,
                "completedSteps": self.completed,
                "totalSteps": len(instructions),
                "failedStep": self.failed_step,
            })
            run_progress.unregister(self.run_id)

    @staticmethod
    def _resolve_vars(obj: Any, vars_dict: dict[str, Any]) -> Any:
        """Recursively replace ${var} and {{var}} placeholders in strings."""
        if isinstance(obj, str):
            def _repl(m):
                key = m.group(1) or m.group(2)
                if key in vars_dict:
                    return str(vars_dict[key])
                return m.group(0)
            return _VAR_PLACEHOLDER_RE.sub(_repl, obj)
        if isinstance(obj, list):
            return [ExtensionRunner._resolve_vars(item, vars_dict) for item in obj]
        if isinstance(obj, dict):
            return {k: ExtensionRunner._resolve_vars(v, vars_dict) for k, v in obj.items()}
        return obj

    async def _handle_local(self, cmd_type: str, step_id: str, instr: dict) -> bool:
        """Execute a locally-handled command (backend-only, no extension round-trip)."""
        extra = instr.get("extra") or {}
        if cmd_type == "setVar":
            var_name = extra.get("name", "")
            var_value = extra.get("value", "")
            vtype = extra.get("valueType", "string")
            if vtype == "number":
                try:
                    var_value = float(var_value)
                except (ValueError, TypeError):
                    pass
            elif vtype == "bool":
                var_value = str(var_value).lower() in ("true", "1", "yes")
            self.vars[var_name] = var_value
            logger.info(f"[ExtensionRunner] setVar {var_name} = {var_value!r}")
            self.results.append({"stepId": step_id, "status": "success", "result": {"setVar": var_name, "value": var_value}})
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"setVar": var_name, "value": var_value},
            })
            return True

        if cmd_type == "log":
            msg = extra.get("message", "")
            level = extra.get("level", "info")
            resolved_msg = self._resolve_vars(msg, self.vars)
            logger.info(f"[ExtensionRunner] LOG [{level}] {resolved_msg}")
            self.results.append({"stepId": step_id, "status": "success", "result": {"log": resolved_msg}})
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"log": resolved_msg},
            })
            return True

        # Unknown local command — fail so we know to register a handler
        self.failed_step = {"stepId": step_id, "instruction": instr, "error": f"No local handler for {cmd_type}"}
        self.results.append({"stepId": step_id, "status": "error", "error": f"No local handler for {cmd_type}"})
        await self._emit({"type": "stepError", "stepId": step_id, "nodeId": instr.get("nodeId"), "error": f"No local handler for {cmd_type}"})
        return False

    async def _execute_instruction(self, instr: dict) -> bool:
        step_id = instr["stepId"]
        step_type = instr.get("type", "")
        extra = instr.get("extra") or {}
        on_error = extra.get("onError", "stop")
        retry_count = extra.get("retryCount", 0)
        timeout = extra.get("timeout", DEFAULT_STEP_TIMEOUT)

        # Schema-driven local command routing
        cmd_type = instr.get("cmdType") or step_type
        if _is_local_command(cmd_type):
            return await self._handle_local(cmd_type, step_id, instr)

        # Resolve variable placeholders in the instruction before sending
        resolved_instr = self._resolve_vars(instr, self.vars)

        last_error = None
        for attempt in range(retry_count + 1):
            try:
                result = await self._send_and_wait(step_id, resolved_instr, timeout)
                self.results.append({"stepId": step_id, "status": "success", "result": result})
                self.completed += 1
                await self._emit({
                    "type": "stepComplete",
                    "stepId": step_id,
                    "nodeId": instr.get("nodeId"),
                    "result": result,
                })

                # Save results to variable if requested (extracted, navigatedTo, or whole result)
                save_to_var = (resolved_instr.get("extra") or {}).get("saveToVar")
                if save_to_var and result:
                    value = result.get("extracted") or result.get("navigatedTo") or result
                    self.vars[save_to_var] = value
                    logger.info(f"[ExtensionRunner] saved result to var {save_to_var}: {value!r}")

                return True
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[ExtensionRunner] {step_id} attempt {attempt + 1}/{retry_count + 1} failed: {e}")
                if attempt < retry_count:
                    await asyncio.sleep(1.0)

        # All retries exhausted
        self.failed_step = {"stepId": step_id, "instruction": instr, "error": last_error}
        self.results.append({"stepId": step_id, "status": "error", "error": last_error})
        await self._emit({
            "type": "stepError",
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "error": last_error,
        })

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

        # Register future BEFORE sending to avoid race with fast responses (e.g. navigate)
        future = ext_manager.register_step_future(step_id)
        try:
            ok = await ext_manager.send_to(self.client_id, "executeStep", {"stepId": step_id, **instr})
            if not ok:
                ext_manager.cancel_step_future(step_id)
                raise RuntimeError(f"Failed to send step {step_id} to extension")

            resp = await asyncio.wait_for(future, timeout=timeout)
            if resp["status"] == "error":
                raise RuntimeError(resp.get("error", "Unknown extension error"))
            return resp.get("result")
        except asyncio.TimeoutError:
            ext_manager.cancel_step_future(step_id)
            raise TimeoutError(f"Step {step_id} timed out after {timeout}s")


async def run_workflow_extension(wf: models.Workflow, nodes: list[models.WorkflowNode],
                                  client_id: str | None = None,
                                  run_id: str | None = None) -> dict:
    """
    Convenience entry point.
    If client_id is None, picks the first online extension.
    """
    if not ext_manager.is_any_online:
        return {"success": False, "error": "没有在线的浏览器扩展，请先安装并启用扩展"}

    target = client_id
    if not target:
        # Pick first available connection
        conns = list(ext_manager.list_client_ids())
        if not conns:
            return {"success": False, "error": "没有可用的浏览器扩展连接"}
        target = conns[0]

    runner = ExtensionRunner(target, run_id=run_id)
    return await runner.run(wf, nodes)
