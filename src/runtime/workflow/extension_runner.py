"""
Extension Runner — executes a workflow via the browser extension over WebSocket.

Flows:
    1. Convert nodes to instruction sequence via extension_emitter
    2. Iterate instructions, send each to extension via ext_manager
    3. Wait for stepResult / stepError (with timeout)
    4. Implement retry logic based on extra.onError / retryCount
    5. Collect results into a report
    6. Execute compound instructions (loops, conditions, try/catch)
"""

import asyncio
import ast
import json
import logging
import os
import re
from typing import Any, Callable, Optional

import httpx
import time

from src.runtime.websocket_manager import ext_manager
from .extension_emitter import build_instructions
from .commands import COMMAND_REGISTRY
from src.providers import run_progress
from src.repo import runtime_models as models
from src.repo.models import SessionLocal
from src.repo.browser_utils import is_browser_running, launch_browser_with_extension

logger = logging.getLogger(__name__)

DEFAULT_STEP_TIMEOUT = 30.0

_VAR_PLACEHOLDER_RE = re.compile(r"\$\{(\w+)\}|\{\{(\w+)\}\}")

# ─── Local command registry ───────────────────────────────────────
# Handlers registered here execute backend-only commands without an
# extension round-trip. New local commands just need a function + decorator.

LOCAL_HANDLERS: dict[str, Callable[["ExtensionRunner", str, dict], Any]] = {}


def register_local(name: str):
    def decorator(fn: Callable[["ExtensionRunner", str, dict], Any]):
        LOCAL_HANDLERS[name] = fn
        return fn
    return decorator


def _clean_var_ref(val):
    """Strip ${var} or {{var}} wrapper from a variable name field."""
    if not isinstance(val, str):
        return str(val) if val is not None else ""
    m = re.match(r'^\$\{(\w+)\}$|^\{\{(\w+)\}\}$', val.strip())
    if m:
        return m.group(1) or m.group(2)
    return val.strip()


def _get_output_var(extra: dict) -> str:
    """统一读取保存结果的变量名（saveToVar / varName / resultVar）。"""
    raw = extra.get("saveToVar") or extra.get("varName") or extra.get("resultVar") or ""
    return _clean_var_ref(raw)


async def wait_for_extension_connection(
    browser_type: str,
    ext_manager,
    timeout: float = 10.0,
) -> str:
    """Wait for the browser extension WebSocket connection to come online.

    Does NOT launch the browser; the caller is responsible for starting Chrome.
    Returns the client_id, or raises TimeoutError.
    """
    if ext_manager is None:
        from src.runtime.websocket_manager import ext_manager as _em
        ext_manager = _em

    # 1. Already online?
    conns = ext_manager.connections_by_browser(browser_type)
    if conns:
        logger.info(f"[{browser_type}] 扩展已在线: {conns[0].client_id}")
        return conns[0].client_id

    # 2. Extension may have connected but not registered yet; brief wait
    if ext_manager.is_any_online:
        await asyncio.sleep(2)
        conns = ext_manager.connections_by_browser(browser_type)
        if conns:
            logger.info(f"[{browser_type}] 扩展注册后已在线: {conns[0].client_id}")
            return conns[0].client_id

    logger.info(f"[{browser_type}] 等待扩展连接...")

    # 3. Exponential backoff polling
    start = time.time()
    delay = 0.5

    while time.time() - start < timeout:
        conns = ext_manager.connections_by_browser(browser_type)
        if conns:
            return conns[0].client_id

        await asyncio.sleep(delay)
        delay = min(delay * 1.5, 5.0)

    raise TimeoutError(
        f"{browser_type} 扩展未在 {timeout}s 内连接，"
        "请关闭该浏览器所有窗口后重试，或在扩展管理页面手动加载 extension/ 目录"
    )


async def wait_for_extension(
    browser_type: str,
    ext_manager,
    timeout: float = 10.0,
) -> str:
    """Legacy convenience: launch browser with extension if needed, then wait.

    Kept for callers that expect auto-launch behavior; new code should launch
    explicitly and call wait_for_extension_connection().
    """
    if not is_browser_running(browser_type):
        logger.info(f"[{browser_type}] 浏览器未运行，尝试自动启动并加载扩展...")
        launch_browser_with_extension(browser_type)
        await asyncio.sleep(3.0)
    return await wait_for_extension_connection(browser_type, ext_manager, timeout)


class LoopBreak(Exception):
    """Raised by break instruction to exit the current loop."""
    pass


class LoopContinue(Exception):
    """Raised by continue instruction to skip to next loop iteration."""
    pass


def _is_local_command(cmd_type: str) -> bool:
    """Return True if the command should be handled locally (backend) rather than sent to extension."""
    cmd = COMMAND_REGISTRY.get(cmd_type)
    if not cmd:
        return False
    return cmd.get("runtimes", {}).get("extension", {}).get("local", False)


class _TableAccessor:
    """Allow table access by row/col index: _table[0][0] or _table[0]['A']."""

    def __init__(self, table_data: dict):
        self._data = table_data
        self._dirty = False

    def _col_name(self, col):
        columns = self._data.get("columns", [])
        if isinstance(col, int):
            if 0 <= col < len(columns):
                return columns[col]["name"]
            # Fallback to A, B, C... when columns not yet defined
            if col < 26:
                return chr(65 + col)
            return str(col)
        return col

    def get(self, row: int, col):
        rows = self._data.get("rows", [])
        col_name = self._col_name(col)
        if row < len(rows):
            return rows[row].get(col_name)
        return None

    def set(self, row: int, col, value):
        rows = self._data.setdefault("rows", [])
        while len(rows) <= row:
            rows.append({})
        col_name = self._col_name(col)
        rows[row][col_name] = value
        self._dirty = True

    def add_cols(self, count: int):
        """Append `count` columns (always adds, never skips).

        Usage: _table.add_cols(3)  # appends 3 new columns
        """
        columns = self._data.setdefault("columns", [])
        rows = self._data.setdefault("rows", [])
        current = len(columns)
        for i in range(current, current + count):
            name = chr(65 + i) if i < 26 else f"Col{i}"
            columns.append({"name": name, "type": "text"})
            for row in rows:
                row.setdefault(name, "")
        self._dirty = True

    def add_rows(self, count: int):
        """Append `count` empty rows (always adds, never skips).

        Usage: _table.add_rows(3)  # appends 3 new rows
        """
        rows = self._data.setdefault("rows", [])
        for _ in range(count):
            rows.append({})
        self._dirty = True

    def ensure_cols(self, count: int):
        """Ensure at least `count` columns exist (idempotent).

        Usage: _table.ensure_cols(5)  # no-op if already 5+ columns
        """
        columns = self._data.setdefault("columns", [])
        rows = self._data.setdefault("rows", [])
        current = len(columns)
        if count <= current:
            return
        for i in range(current, count):
            name = chr(65 + i) if i < 26 else f"Col{i}"
            columns.append({"name": name, "type": "text"})
            for row in rows:
                row.setdefault(name, "")
        self._dirty = True

    def ensure_rows(self, count: int):
        """Ensure at least `count` rows exist (idempotent).

        Usage: _table.ensure_rows(5)  # no-op if already 5+ rows
        """
        rows = self._data.setdefault("rows", [])
        current = len(rows)
        if count <= current:
            return
        for _ in range(count - current):
            rows.append({})
        self._dirty = True

    def __len__(self):
        return len(self._data.get("rows", []))

    @property
    def dirty(self) -> bool:
        return self._dirty

    def __getitem__(self, row: int):
        class _RowProxy:
            def __init__(proxy_self, accessor: "_TableAccessor", row_idx: int):
                proxy_self._accessor = accessor
                proxy_self._row = row_idx

            def __getitem__(proxy_self, col):
                return proxy_self._accessor.get(proxy_self._row, col)

            def __setitem__(proxy_self, col, value):
                proxy_self._accessor.set(proxy_self._row, col, value)

        return _RowProxy(self, row)


# Global registry of active runners keyed by run_id
_active_runners: dict[str, "ExtensionRunner"] = {}
_active_runners_lock = asyncio.Lock()

# Cache latest run table result per workflow (runtime-only, memory)
_last_run_tables: dict[int, dict] = {}


async def get_active_runner(run_id: str) -> "ExtensionRunner" | None:
    async with _active_runners_lock:
        return _active_runners.get(run_id)


async def set_active_runner(run_id: str, runner: "ExtensionRunner") -> None:
    async with _active_runners_lock:
        _active_runners[run_id] = runner


async def remove_active_runner(run_id: str) -> None:
    async with _active_runners_lock:
        _active_runners.pop(run_id, None)


async def list_active_runners() -> list[tuple[str, "ExtensionRunner"]]:
    async with _active_runners_lock:
        return list(_active_runners.items())


class ExtensionRunner:
    def __init__(
        self,
        client_id: str,
        run_id: str | None = None,
        log_dir: str | None = None,
        queue: asyncio.Queue | None = None,
        workflow_id: int | None = None,
    ):
        self.client_id = client_id
        self.run_id = run_id or f"run_{id(self)}"
        self.workflow_id = workflow_id
        self.vars: dict[str, Any] = {}
        self.results: list[dict] = []
        self.completed = 0
        self.failed_steps: list[dict] = []
        self._last_error: str | None = None
        self._try_depth: int = 0
        self.queue = queue or asyncio.Queue()
        self._step_seq = 0
        self._paused = asyncio.Event()
        self._paused.set()  # default: not paused
        self._stopped = False
        self._current_step: dict | None = None
        self._pause_event_sent = False
        self._table_data: dict = {"columns": [], "rows": []}
        self._table_dirty: bool = False
        self.log_dir = log_dir or ""
        self._log_file = None
        self._run_started_sent = False
        if self.log_dir:
            os.makedirs(self.log_dir, exist_ok=True)
            self._log_file = open(os.path.join(self.log_dir, "run.log"), "w", encoding="utf-8")

    def pause(self) -> None:
        if not self._stopped:
            self._paused.clear()
            logger.info(f"[ExtensionRunner] run_id={self.run_id} paused")

    def resume(self) -> None:
        self._paused.set()
        self._pause_event_sent = False
        logger.info(f"[ExtensionRunner] run_id={self.run_id} resumed")

    async def stop(self) -> None:
        self._stopped = True
        self._paused.set()  # wake up if currently paused
        # Cancel the pending step future so _wait_future_with_stop exits immediately
        if self._current_step:
            step_id = self._current_step.get("stepId")
            if step_id:
                try:
                    await ext_manager.cancel_step_future(step_id)
                except Exception:
                    pass
        logger.info(f"[ExtensionRunner] run_id={self.run_id} stopped")

    async def _wait_future_with_stop(self, future: asyncio.Future, timeout: float) -> Any:
        """Wait for a future, but allow stop() to interrupt."""
        start = asyncio.get_event_loop().time()
        while not future.done():
            if self._stopped:
                raise asyncio.CancelledError("Run stopped by user")
            await asyncio.sleep(0.1)
            if asyncio.get_event_loop().time() - start >= timeout:
                raise asyncio.TimeoutError()
        if future.cancelled():
            raise asyncio.CancelledError("Step future was cancelled")
        return future.result()

    async def _ensure_connected(self) -> None:
        """Delay WebSocket binding until the first extension instruction.
        Infers browser type from the current step (openBrowser extra.browserType),
        defaulting to chrome. Sends runStarted on first connection.
        """
        if self.client_id:
            return
        browser_type = "chrome"
        if self._current_step:
            extra = self._current_step.get("extra") or {}
            bt = extra.get("browserType")
            if bt:
                browser_type = bt
        self.client_id = await wait_for_extension_connection(browser_type, ext_manager, timeout=10.0)
        if not self._run_started_sent:
            self._run_started_sent = True
            await ext_manager.send_to(self.client_id, "runStarted", {"runId": self.run_id})

    async def _emit(self, event: dict) -> None:
        # Enrich compound stepComplete events with the container's start/end
        # positions so the UI can render the closing marker correctly.
        if (
            event.get("type") == "stepComplete"
            and self._current_step
            and self._current_step.get("compound")
        ):
            event.setdefault("order", self._current_step.get("order"))
            event.setdefault("endOrder", self._current_step.get("endOrder"))
            event.setdefault("endNodeId", self._current_step.get("endNodeId"))
        try:
            await asyncio.wait_for(self.queue.put(event), timeout=1.0)
        except Exception:
            pass
        # 同步写入本地日志文件
        if self._log_file:
            try:
                line = json.dumps(event, ensure_ascii=False, default=str)
                self._log_file.write(line + "\n")
                self._log_file.flush()
            except Exception:
                pass

    def _next_step_id(self) -> str:
        self._step_seq += 1
        return f"{self.run_id}_int_{self._step_seq}"

    async def _wait_if_paused(self) -> bool:
        """Block while paused; return False if stopped."""
        if not self._paused.is_set() and not self._stopped and not self._pause_event_sent:
            self._pause_event_sent = True
            await self._emit({
                "type": "paused",
                "runId": self.run_id,
                "nodeId": self._current_step.get("nodeId") if self._current_step else None,
                "stepId": self._current_step.get("stepId") if self._current_step else None,
            })
        await self._paused.wait()
        return not self._stopped

    async def _interruptible_sleep(self, seconds: float) -> None:
        """Sleep for up to `seconds`, checking stop/pause every 200ms."""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + seconds
        while loop.time() < deadline:
            if self._stopped:
                raise asyncio.CancelledError("Run stopped by user")
            if not await self._wait_if_paused():
                raise asyncio.CancelledError("Run stopped by user")
            remaining = deadline - loop.time()
            await asyncio.sleep(min(0.2, remaining))

    async def run(self, wf: models.Workflow, nodes: list[models.WorkflowNode]) -> dict:
        """Run workflow nodes through the extension. Returns execution report."""
        await run_progress.register(self.run_id, self.queue)
        # Load workflow elements and build element_map for selector resolution
        db = SessionLocal()
        try:
            elements = (
                db.query(models.WorkflowElement)
                .filter(models.WorkflowElement.workflow_id == wf.id)
                .all()
            )
            element_map = {el.name: el for el in elements}
        finally:
            db.close()

        instructions = build_instructions(nodes, element_map=element_map)
        logger.info(
            f"[ExtensionRunner] wf={wf.id} steps={len(instructions)} "
            f"client={self.client_id} run_id={self.run_id}"
        )

        await set_active_runner(self.run_id, self)
        try:
            for instr in instructions:
                self._current_step = instr
                if not await self._wait_if_paused():
                    break
                await self._emit({
                    "type": "stepStart",
                    "stepId": instr.get("stepId"),
                    "nodeId": instr.get("nodeId"),
                    "compound": instr.get("compound", False),
                    "cmdType": instr.get("cmdType", ""),
                })
                try:
                    success = await self._execute_instruction(instr)
                    if not success:
                        break
                except LoopBreak:
                    logger.warning("[ExtensionRunner] break outside loop — ignored")
                    self.completed += 1
                except LoopContinue:
                    logger.warning("[ExtensionRunner] continue outside loop — ignored")
                    self.completed += 1

            return {
                "success": not self._stopped,
                "completedSteps": self.completed,
                "totalSteps": len(instructions),
                "failedSteps": self.failed_steps,
                "results": self.results,
                "stopped": self._stopped,
            }
        finally:
            await self._emit({
                "type": "done",
                "success": not self._stopped,
                "completedSteps": self.completed,
                "totalSteps": len(instructions),
                "failedSteps": self.failed_steps,
                "stopped": self._stopped,
            })
            # 保存数据表格到日志目录
            if self.log_dir:
                try:
                    with open(os.path.join(self.log_dir, "table.json"), "w", encoding="utf-8") as f:
                        json.dump(self._table_data, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                try:
                    if self._log_file:
                        self._log_file.close()
                        self._log_file = None
                except Exception:
                    pass
            await run_progress.unregister(self.run_id)
            await remove_active_runner(self.run_id)

    @staticmethod
    def _resolve_vars(obj: Any, vars_dict: dict[str, Any]) -> Any:
        """Recursively replace ${var} and {{var}} placeholders in strings."""
        if isinstance(obj, str):
            def _repl(m):
                key = m.group(1) or m.group(2)
                if key in vars_dict:
                    return str(vars_dict[key])
                logger.warning(
                    f"[ExtensionRunner] resolve_vars: key '{key}' not found "
                    f"in vars={list(vars_dict.keys())}"
                )
                return m.group(0)
            return _VAR_PLACEHOLDER_RE.sub(_repl, obj)
        if isinstance(obj, list):
            return [ExtensionRunner._resolve_vars(item, vars_dict) for item in obj]
        if isinstance(obj, dict):
            return {k: ExtensionRunner._resolve_vars(v, vars_dict) for k, v in obj.items()}
        return obj

    def _resolve_loop_context(self, extra: dict) -> dict | None:
        """Return the loop context that should anchor this instruction.

        - scope=global -> no context.
        - loopAnchor set -> nearest matching loopElementName in the stack.
        - otherwise -> top of the stack (nearest outer loop).
        """
        if extra.get("scope", "local") == "global":
            return None
        stack = self.vars.get("__loop_ctx")
        if not isinstance(stack, list) or not stack:
            return None
        anchor = (extra.get("loopAnchor") or "").strip()
        if not anchor:
            return stack[-1]
        for ctx in reversed(stack):
            if ctx.get("loopElementName") == anchor:
                return ctx
        # Anchor not found: fall back to nearest loop and warn.
        logger.warning(f"[ExtensionRunner] loopAnchor '{anchor}' not found in active loops; using nearest")
        return stack[-1]

    async def _call_extension_handler(self, handler: str, payload: dict, timeout: float = DEFAULT_STEP_TIMEOUT) -> Any:
        """Call a specific extension handler and return the result."""
        await self._ensure_connected()
        conn = ext_manager.get_connection(self.client_id)
        if not conn:
            raise RuntimeError(f"Extension {self.client_id} is not connected")

        # Inject loop context into extra so content.js resolves locators by index alignment
        extra = dict(payload.get("extra") or {})
        ctx = self._resolve_loop_context(extra)
        if ctx:
            extra["contextLocator"] = ctx["locator"]
            extra["contextLocatorType"] = ctx["selectorFamily"]
            extra["contextIndex"] = ctx["index"]
            extra["contextTotal"] = ctx.get("total")
            for key in ("sourceLocator", "sourceSelectorFamily", "sourceIndex", "sourceTotal"):
                if key in ctx:
                    extra[key] = ctx[key]
            # Prefer the capture-time relative selector when the element carries
            # one (injected into extra by the emitter). content.js then queries
            # the child relative to the resolved loop-item parent rather than
            # globally + contains-filtering.
            if extra.get("relativeLocator") and extra.get("useRelative", True):
                extra["useRelative"] = True
            logger.info(
                f"[ExtensionRunner] loop context index={ctx['index'] + 1}/{ctx.get('total', '?')} "
                f"locator={ctx['locator'][:60]}..."
            )
            payload = {**payload, "extra": extra}

        step_id = self._next_step_id()
        node_id = payload.get("nodeId") or (self._current_step.get("nodeId") if self._current_step else None)
        instr = {
            "stepId": step_id, "nodeId": node_id,
            "type": handler,
            **payload,
        }
        logger.info(f"[ExtensionRunner] -> ext handler={handler} stepId={step_id} payload={payload}")
        future = await ext_manager.register_step_future(step_id)
        try:
            ok = await ext_manager.send_to(
                self.client_id,
                "executeStep",
                {"stepId": step_id, "nodeId": node_id, **instr},
            )
            if not ok:
                await ext_manager.cancel_step_future(step_id)
                raise RuntimeError(f"Failed to send {handler} to extension")

            resp = await self._wait_future_with_stop(future, timeout=timeout)
            if resp["status"] == "error":
                raise RuntimeError(resp.get("error", f"Extension {handler} failed"))
            result = resp.get("result", {})
            logger.info(f"[ExtensionRunner] <- ext handler={handler} stepId={step_id} result={result}")
            return result
        except asyncio.TimeoutError:
            await ext_manager.cancel_step_future(step_id)
            raise TimeoutError(f"{handler} timed out after {timeout}s")
        except asyncio.CancelledError:
            await ext_manager.cancel_step_future(step_id)
            raise

    async def _check_element_exists(
        self,
        locator: str,
        selector_family: str,
        visible_only: bool = True,
        timeout: float = 3.0,
        extra: dict = None,
    ) -> bool:
        """Ask extension whether an element exists."""
        try:
            payload_extra = {"timeout": timeout}
            if extra:
                payload_extra["scope"] = extra.get("scope", "local")
                if "visibilityMode" in extra:
                    payload_extra["visibilityMode"] = extra["visibilityMode"]
                else:
                    payload_extra["visibleOnly"] = visible_only
            else:
                payload_extra["visibleOnly"] = visible_only
            result = await self._call_extension_handler(
                "checkElementExists",
                {
                    "locator": locator,
                    "selectorFamily": selector_family,
                    "extra": payload_extra,
                },
                timeout=timeout + 2,
            )
            return result.get("exists", False)
        except Exception as e:
            logger.warning(f"[ExtensionRunner] checkElementExists failed: {e}")
            return False

    async def _check_element_visible(
        self,
        locator: str,
        selector_family: str,
        timeout: float = 3.0,
        extra: dict = None,
    ) -> bool:
        try:
            payload_extra = {"timeout": timeout}
            if extra:
                payload_extra["scope"] = extra.get("scope", "local")
                if "visibilityMode" in extra:
                    payload_extra["visibilityMode"] = extra["visibilityMode"]
                else:
                    payload_extra["visibleOnly"] = True
            else:
                payload_extra["visibleOnly"] = True
            result = await self._call_extension_handler(
                "checkElementVisible",
                {
                    "locator": locator,
                    "selectorFamily": selector_family,
                    "extra": payload_extra,
                },
                timeout=timeout + 2,
            )
            visible = result.get("visible", False)
            logger.info(
                f"[ExtensionRunner] checkElementVisible locator={locator} "
                f"type={selector_family} -> visible={visible}"
            )
            return visible
        except Exception as e:
            logger.warning(f"[ExtensionRunner] checkElementVisible failed: {e}")
            return False

    async def _get_element_text(
        self, locator: str, selector_family: str, timeout: float = 3.0, extra: dict = None
    ) -> str:
        try:
            payload_extra = {"timeout": timeout}
            if extra:
                payload_extra["scope"] = extra.get("scope", "local")
                if "visibilityMode" in extra:
                    payload_extra["visibilityMode"] = extra["visibilityMode"]
                elif "visibleOnly" in extra:
                    payload_extra["visibleOnly"] = extra["visibleOnly"]
            result = await self._call_extension_handler(
                "getElementText",
                {
                    "locator": locator,
                    "selectorFamily": selector_family,
                    "extra": payload_extra,
                },
                timeout=timeout + 2,
            )
            return result.get("text", "")
        except Exception as e:
            logger.warning(f"[ExtensionRunner] getElementText failed: {e}")
            return ""

    async def _get_current_url(self) -> str:
        try:
            result = await self._call_extension_handler("getCurrentUrl", {}, timeout=5.0)
            return result.get("url", "")
        except Exception as e:
            logger.warning(f"[ExtensionRunner] getCurrentUrl failed: {e}")
            return ""

    async def _find_elements(
        self,
        locator: str,
        selector_family: str,
        timeout: float = 10.0,
        extra: dict = None,
    ) -> list[dict]:
        try:
            payload_extra = {"timeout": timeout}
            if extra:
                payload_extra["scope"] = extra.get("scope", "local")
                if "visibilityMode" in extra:
                    payload_extra["visibilityMode"] = extra["visibilityMode"]
                else:
                    payload_extra["visibleOnly"] = extra.get("visibleOnly", True)
                # Pass capture-time relative fields so child elements can serve as
                # forEachElement loop anchors inside their parent loops.
                for key in ("useRelative", "relativeLocator", "relativeSelectorFamily", "anchorChain", "loopAnchor"):
                    if key in extra:
                        payload_extra[key] = extra[key]
            result = await self._call_extension_handler(
                "findElements",
                {
                    "locator": locator,
                    "selectorFamily": selector_family,
                    "extra": payload_extra,
                },
                timeout=timeout + 2,
            )
            return result.get("items", [])
        except Exception as e:
            logger.warning(f"[ExtensionRunner] findElements failed: {e}")
            return []

    async def _evaluate_condition(self, instr: dict) -> dict:
        """Evaluate a condition for if/while compound instructions."""
        cmd_type = instr.get("cmdType", "")
        extra = self._resolve_vars(instr.get("extra") or {}, self.vars)
        locator = instr.get("locator") or extra.get("locator", "")
        selector_family = instr.get("selectorFamily") or extra.get("selector_family", "css")
        timeout = extra.get("timeout", 3)

        # Collect additional locators when present (multi-element conditions)
        locators = [(locator, selector_family)]
        for alt in instr.get("altLocators") or []:
            locators.append((alt.get("locator"), alt.get("selectorFamily") or selector_family))

        if cmd_type == "ifElementExists":
            op = extra.get("operator", "exists")
            elements = []
            results = []
            for loc, fam in locators:
                res = await self._check_element_exists(loc, fam, timeout=timeout, extra=extra)
                results.append(res)
                elements.append({"locator": loc, "family": fam, "exists": res})
            met = not any(results) if op == "notExists" else any(results)
            return {"met": met, "cmdType": cmd_type, "operator": op, "elements": elements}
        if cmd_type == "ifElementVisible":
            op = extra.get("operator", "visible")
            logger.info(
                f"[ExtensionRunner] evaluating ifElementVisible "
                f"locators={locators} timeout={timeout} operator={op} "
                f"visibilityMode={extra.get('visibilityMode', 'visible')}"
            )
            elements = []
            results = []
            for loc, fam in locators:
                res = await self._check_element_visible(loc, fam, timeout=timeout, extra=extra)
                results.append(res)
                elements.append({"locator": loc, "family": fam, "visible": res})
            logger.info(f"[ExtensionRunner] ifElementVisible results={results}")
            met = not any(results) if op == "notVisible" else any(results)
            return {"met": met, "cmdType": cmd_type, "operator": op, "elements": elements}
        if cmd_type == "ifTextContains":
            text = await self._get_element_text(locator, selector_family, timeout=timeout, extra=extra)
            expected = extra.get("text", "")
            op = extra.get("operator", "contains")
            met = False
            if op == "notContains":
                met = expected not in text
            elif op == "startsWith":
                met = text.startswith(expected)
            elif op == "endsWith":
                met = text.endswith(expected)
            else:
                met = expected in text
            logger.info(f"[ExtensionRunner] ifTextContains text={text!r} expected={expected!r} op={op} met={met}")
            return met
        if cmd_type == "ifTextEquals":
            text = await self._get_element_text(locator, selector_family, timeout=timeout, extra=extra)
            expected = extra.get("text", "")
            met = text == expected
            logger.info(f"[ExtensionRunner] ifTextEquals text={text!r} expected={expected!r} met={met}")
            return met
        if cmd_type == "ifUrlContains":
            url = await self._get_current_url()
            pattern = extra.get("urlPattern", "")
            return pattern in url
        if cmd_type == "ifVarEquals":
            var_name = _clean_var_ref(extra.get("varName", ""))
            expected = extra.get("value", "")
            vtype = extra.get("valueType", "string")
            op = extra.get("operator", "equals")
            actual = self.vars.get(var_name)
            if vtype == "number":
                try:
                    fa, fe = float(actual), float(expected)
                    if op == "greaterThan":
                        return fa > fe
                    if op == "lessThan":
                        return fa < fe
                    return fa == fe
                except (ValueError, TypeError):
                    return False
            if vtype == "bool":
                return bool(actual) == (str(expected).lower() in ("true", "1", "yes"))
            if op == "greaterThan":
                return str(actual) > str(expected)
            if op == "lessThan":
                return str(actual) < str(expected)
            return str(actual) == str(expected)
        if cmd_type == "ifVarContains":
            var_name = _clean_var_ref(extra.get("varName", ""))
            expected = extra.get("value", "")
            op = extra.get("operator", "contains")
            actual = self.vars.get(var_name)
            if isinstance(actual, list):
                has = expected in actual
                return not has if op == "notContains" else has
            s = str(actual)
            if op == "notContains":
                return expected not in s
            if op == "startsWith":
                return s.startswith(expected)
            if op == "endsWith":
                return s.endswith(expected)
            return expected in s
        if cmd_type == "ifListContains":
            list_name = _clean_var_ref(extra.get("listName", ""))
            expected = self._resolve_vars(str(extra.get("value", "")), self.vars)
            actual = self.vars.get(list_name)
            if isinstance(actual, list):
                return expected in actual
            logger.warning(f"[ExtensionRunner] ifListContains: {list_name} is not a list")
            return False
        if cmd_type == "ifDictContains":
            dict_name = _clean_var_ref(extra.get("dictName", ""))
            key = self._resolve_vars(str(extra.get("key", "")), self.vars)
            actual = self.vars.get(dict_name)
            if isinstance(actual, dict):
                return key in actual
            logger.warning(f"[ExtensionRunner] ifDictContains: {dict_name} is not a dict")
            return False

        # whileCondition variants
        if cmd_type == "whileCondition":
            cond_type = extra.get("conditionType", "elementExists")
            met = False
            if cond_type == "elementExists":
                met = await self._check_element_exists(locator, selector_family, timeout=timeout, extra=extra)
            elif cond_type == "elementNotExists":
                met = not await self._check_element_exists(locator, selector_family, timeout=timeout, extra=extra)
            elif cond_type == "urlContains":
                url = await self._get_current_url()
                pattern = extra.get("urlPattern", "")
                met = pattern in url
            elif cond_type == "varEquals":
                var_name = _clean_var_ref(extra.get("varName", ""))
                expected = extra.get("varValue", "")
                actual = self.vars.get(var_name)
                met = str(actual) == str(expected)
            elif cond_type == "varContains":
                var_name = _clean_var_ref(extra.get("varName", ""))
                expected = extra.get("varValue", "")
                actual = self.vars.get(var_name)
                if isinstance(actual, list):
                    met = expected in actual
                else:
                    met = expected in str(actual)
            return {"met": met, "cmdType": cmd_type}

        logger.warning(f"[ExtensionRunner] Unknown condition type: {cmd_type}")
        return {"met": False, "cmdType": cmd_type}

    async def _run_body(self, body: list[dict], emit_events: bool = True) -> bool:
        """Execute a list of instructions (a body block). Returns False if flow should stop."""
        for sub in body:
            self._current_step = sub
            if not await self._wait_if_paused():
                return False
            if emit_events:
                await self._emit({
                    "type": "stepStart",
                    "stepId": sub.get("stepId"),
                    "nodeId": sub.get("nodeId"),
                })
            success = await self._execute_instruction(sub)
            if not success:
                return False
        return True

    async def _handle_compound(self, instr: dict) -> bool:
        """Execute a compound instruction (loop, condition, try, break, continue)."""
        cmd_type = instr.get("cmdType", "")
        step_id = instr.get("stepId", "")
        extra = self._resolve_vars(instr.get("extra") or {}, self.vars)

        # ── break / continue ──
        if cmd_type == "break":
            raise LoopBreak()
        if cmd_type == "continue":
            raise LoopContinue()

        # ── forRange ──
        if cmd_type == "forRange":
            start = int(extra.get("start", 0))
            end = int(extra.get("end", 10))
            step = int(extra.get("step", 1))
            var_name = _clean_var_ref(extra.get("varName", "i"))
            body = instr.get("body", [])
            for i in range(start, end, step):
                if self._stopped:
                    break
                self.vars[var_name] = i
                logger.info(f"[ExtensionRunner] forRange {var_name}={i}")
                try:
                    if not await self._run_body(body):
                        return False
                except LoopBreak:
                    logger.info("[ExtensionRunner] forRange break")
                    break
                except LoopContinue:
                    logger.info("[ExtensionRunner] forRange continue")
                    continue
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"forRange": "done"},
            })
            return True

        # ── forEachElement ──
        if cmd_type == "forEachElement":
            locator = instr.get("locator") or extra.get("locator", "")
            selector_family = instr.get("selectorFamily") or extra.get("selector_family", "css")
            item_var = _clean_var_ref(extra.get("itemVar", "item"))
            idx_var = _clean_var_ref(extra.get("indexVar", "index"))
            timeout = extra.get("timeout", 10)
            body = instr.get("body", [])

            logger.info(
                f"[ExtensionRunner] forEachElement "
                f"visibilityMode={extra.get('visibilityMode', 'visible')} "
                f"visibleOnly={extra.get('visibleOnly', '-')}"
            )
            elements = await self._find_elements(locator, selector_family, timeout=timeout, extra=extra)
            logger.info(f"[ExtensionRunner] forEachElement found {len(elements)} elements")
            self.vars.setdefault("__loop_ctx", []).append(None)  # reserve slot, will overwrite each iteration
            try:
                for idx, item in enumerate(elements):
                    if self._stopped:
                        break
                    self.vars[idx_var] = idx
                    self.vars[item_var] = item.get("text", "") if isinstance(item, dict) else str(item)
                    # Set loop context so child instructions resolve locators relative to current element.
                    # When the extension gives us a unique element selector, use it directly so nested
                    # loops don't rely on a global list index (which would resolve to the wrong item).
                    # Always keep the original loop selector/index as a fallback in case the absolute
                    # XPath context locator goes stale after DOM mutations.
                    base_ctx = {
                        "sourceLocator": locator,
                        "sourceSelectorFamily": selector_family,
                        "sourceIndex": idx,
                        "sourceTotal": len(elements),
                        "loopElementName": instr.get("elementName"),
                    }
                    if isinstance(item, dict) and item.get("contextLocator"):
                        self.vars["__loop_ctx"][-1] = {
                            **base_ctx,
                            "locator": item["contextLocator"],
                            "selectorFamily": item.get("contextLocatorType", selector_family),
                            "index": 0,
                            "total": 1,
                        }
                    else:
                        self.vars["__loop_ctx"][-1] = {
                            **base_ctx,
                            "locator": locator,
                            "selectorFamily": selector_family,
                            "index": idx,
                            "total": len(elements),
                        }
                    logger.info(f"[ExtensionRunner] forEachElement [{idx}] {item_var}={self.vars[item_var]!r}")
                    try:
                        if not await self._run_body(body):
                            return False
                    except LoopBreak:
                        logger.info("[ExtensionRunner] forEachElement break")
                        break
                    except LoopContinue:
                        logger.info("[ExtensionRunner] forEachElement continue")
                        continue
            finally:
                self.vars["__loop_ctx"].pop()
                if not self.vars["__loop_ctx"]:
                    self.vars.pop("__loop_ctx", None)
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"forEachElement": len(elements)},
            })
            return True

        # ── forList ──
        if cmd_type == "forList":
            list_var = _clean_var_ref(extra.get("listVar", "items"))
            items = self.vars.get(list_var, [])
            if not isinstance(items, list):
                items = []
            item_var = _clean_var_ref(extra.get("itemVar", "item"))
            idx_var = _clean_var_ref(extra.get("indexVar", "index"))
            body = instr.get("body", [])
            logger.info(f"[ExtensionRunner] forList {list_var} has {len(items)} items")
            for idx, item in enumerate(items):
                if self._stopped:
                    break
                self.vars[idx_var] = idx
                self.vars[item_var] = item
                logger.info(f"[ExtensionRunner] forList [{idx}] {item_var}={item!r}")
                try:
                    if not await self._run_body(body):
                        return False
                except LoopBreak:
                    logger.info("[ExtensionRunner] forList break")
                    break
                except LoopContinue:
                    logger.info("[ExtensionRunner] forList continue")
                    continue
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"forList": len(items)},
            })
            return True

        # ── forEachTableRow ──
        if cmd_type == "forEachTableRow":
            rows = self._table_data.get("rows", [])
            item_var = _clean_var_ref(extra.get("itemVar", "row"))
            idx_var = _clean_var_ref(extra.get("indexVar", "index"))
            body = instr.get("body", [])
            logger.info(f"[ExtensionRunner] forEachTableRow has {len(rows)} rows")
            for idx, row in enumerate(rows):
                if self._stopped:
                    break
                self.vars[idx_var] = idx
                self.vars[item_var] = row
                logger.info(f"[ExtensionRunner] forEachTableRow [{idx}] {item_var}={row!r}")
                try:
                    if not await self._run_body(body):
                        return False
                except LoopBreak:
                    logger.info("[ExtensionRunner] forEachTableRow break")
                    break
                except LoopContinue:
                    logger.info("[ExtensionRunner] forEachTableRow continue")
                    continue
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"forEachTableRow": len(rows)},
            })
            return True

        # ── whileCondition ──
        if cmd_type == "whileCondition":
            max_iter = int(extra.get("maxIterations", 100))
            body = instr.get("body", [])
            execute_first = extra.get("executeFirst", False)
            first_iter = True
            for _iter in range(max_iter):
                if self._stopped:
                    break
                # do-while: execute body first, then check condition for continuation
                if not (execute_first and first_iter):
                    condition_met = (await self._evaluate_condition(instr))["met"]
                    logger.info(
                        f"[ExtensionRunner] whileCondition iter={_iter} "
                        f"met={condition_met} executeFirst={execute_first}"
                    )
                    if not condition_met:
                        break
                first_iter = False
                try:
                    if not await self._run_body(body):
                        return False
                except LoopBreak:
                    logger.info("[ExtensionRunner] whileCondition break")
                    break
                except LoopContinue:
                    logger.info("[ExtensionRunner] whileCondition continue")
                    continue
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"whileCondition": "done"},
            })
            return True

        # ── if* conditions ──
        if cmd_type.startswith("if"):
            eval_result = await self._evaluate_condition(instr)
            condition_met = eval_result["met"]
            logger.info(f"[ExtensionRunner] {cmd_type} condition={condition_met}")
            body = instr.get("body", []) if condition_met else instr.get("elseBody", [])
            success = await self._run_body(body)
            self.completed += 1
            result_payload = {cmd_type: condition_met}
            if "elements" in eval_result:
                result_payload["elements"] = eval_result["elements"]
            if "operator" in eval_result:
                result_payload["operator"] = eval_result["operator"]
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": result_payload,
            })
            return success

        # ── try/catch ──
        if cmd_type == "try":
            body = instr.get("body", [])
            else_body = instr.get("elseBody", [])
            error_var = _clean_var_ref(extra.get("errorVar", "error"))
            caught_error: str | None = None
            self._try_depth += 1
            try:
                success = await self._run_body(body)
                if not success:
                    # Body returned False (a step failed with onError=stop).
                    # Treat it as an exception so the catch block runs.
                    raise RuntimeError(self._last_error or "try body failed")
                self.completed += 1
                await self._emit({
                    "type": "stepComplete",
                    "stepId": step_id,
                    "nodeId": instr.get("nodeId"),
                    "result": {"try": "success"},
                })
                return success
            except LoopBreak:
                raise
            except LoopContinue:
                raise
            except Exception as e:
                caught_error = str(e)
            finally:
                self._try_depth -= 1

            if caught_error is not None:
                self.vars[error_var] = caught_error
                logger.info(f"[ExtensionRunner] catch {error_var}={caught_error!r}")
                success = await self._run_body(else_body)
                self.completed += 1
                await self._emit({
                    "type": "stepComplete",
                    "stepId": step_id,
                    "nodeId": instr.get("nodeId"),
                    "result": {"try": "caught", "error": caught_error},
                })
                return success

        logger.warning(f"[ExtensionRunner] Unknown compound instruction: {cmd_type}")
        return True

    async def _handle_local(self, cmd_type: str, step_id: str, instr: dict) -> bool:
        """Execute a locally-handled command (backend-only, no extension round-trip)."""
        # Schema-driven registry first — new local commands just need @register_local.
        handler = LOCAL_HANDLERS.get(cmd_type)
        if handler:
            return await handler(self, cmd_type, step_id, instr)

        # Legacy hard-coded handlers below. Migrate these to @register_local over time.
        extra = instr.get("extra") or {}
        if cmd_type == "httpRequest":
            method = extra.get("method", "GET")
            url = extra.get("url", "")
            headers_str = extra.get("headers", "")
            body = extra.get("body", "")
            result_var = _get_output_var(extra)
            timeout = extra.get("timeout", 30)
            logger.info(f"[ExtensionRunner] httpRequest {method} {url}")
            try:
                request_headers = {}
                if headers_str:
                    try:
                        request_headers = json.loads(headers_str)
                    except Exception:
                        pass
                request_kwargs = {"timeout": float(timeout)}
                if body and method.upper() in ("POST", "PUT", "PATCH"):
                    try:
                        request_kwargs["json"] = json.loads(body)
                    except Exception:
                        request_kwargs["content"] = body.encode("utf-8")
                async with httpx.AsyncClient() as client:
                    response = await client.request(method.upper(), url, headers=request_headers, **request_kwargs)
                    result = {
                        "status_code": response.status_code,
                        "text": response.text,
                        "headers": dict(response.headers),
                    }
            except Exception as e:
                logger.error(f"[ExtensionRunner] httpRequest failed: {e}")
                raise
            if result_var:
                self.vars[result_var] = result
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"httpRequest": url, "method": method, "status_code": result.get("status_code")},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"httpRequest": url, "status_code": result.get("status_code")},
            })
            return True

        # ── Data Table commands ──
        if cmd_type == "readTableCell":
            row_idx = int(extra.get("rowIndex", 0))
            col_name = extra.get("columnName", "")
            var_name = _get_output_var(extra)
            rows = self._table_data.get("rows", [])
            value = ""
            if 0 <= row_idx < len(rows):
                value = rows[row_idx].get(col_name, "")
            if var_name:
                self.vars[var_name] = value
            logger.info(f"[ExtensionRunner] readTableCell [{row_idx}][{col_name}] = {value!r}")
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"readTableCell": value},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"readTableCell": value},
            })
            return True

        if cmd_type == "writeTableCell":
            row_idx = int(extra.get("rowIndex", 0))
            col_name = extra.get("columnName", "")
            value = self._resolve_vars(str(extra.get("value", "")), self.vars)
            rows = self._table_data.setdefault("rows", [])
            # Ensure row exists
            while len(rows) <= row_idx:
                rows.append({})
            rows[row_idx][col_name] = value
            # Auto-add column definition so _TableAccessor numeric index works
            if col_name:
                columns = self._table_data.setdefault("columns", [])
                if not any(c.get("name") == col_name for c in columns):
                    columns.append({"name": col_name, "type": "text"})
            self._table_dirty = True
            logger.info(f"[ExtensionRunner] writeTableCell [{row_idx}][{col_name}] = {value!r}")
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"writeTableCell": value},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"writeTableCell": value, "tableData": self._table_data},
            })
            return True

        if cmd_type == "getTableRowCount":
            var_name = _get_output_var(extra)
            count = len(self._table_data.get("rows", []))
            if var_name:
                self.vars[var_name] = count
            logger.info(f"[ExtensionRunner] getTableRowCount = {count}")
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"getTableRowCount": count},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"getTableRowCount": count},
            })
            return True

        if cmd_type == "writeTableRow":
            write_mode = extra.get("writeMode", "append")
            row_idx = int(extra.get("rowIndex", 0))
            row_data_raw = extra.get("rowData", "{}")
            # Resolve variables with JSON encoding so strings get quoted
            raw_str = str(row_data_raw)
            matches = list(_VAR_PLACEHOLDER_RE.finditer(raw_str))
            if matches:
                resolved = raw_str
                for m in reversed(matches):
                    key = m.group(1) or m.group(2)
                    val = self.vars.get(key)
                    if isinstance(val, str):
                        replacement = json.dumps(val)
                    elif isinstance(val, (int, float, bool)):
                        replacement = json.dumps(val)
                    elif val is None:
                        replacement = "null"
                    else:
                        replacement = json.dumps(str(val))
                    resolved = resolved[:m.start()] + replacement + resolved[m.end():]
            else:
                resolved = raw_str
            try:
                row_data = json.loads(resolved)
            except Exception:
                try:
                    row_data = ast.literal_eval(resolved)
                except Exception:
                    row_data = {}
            if isinstance(row_data, list):
                cols = self._table_data.get("columns", [])
                row_data = {
                    (cols[i]["name"] if i < len(cols) else chr(65 + i)): v
                    for i, v in enumerate(row_data)
                }
            elif not isinstance(row_data, dict):
                row_data = {}
            # Auto-create column definitions when writing a row to an empty table
            columns = self._table_data.setdefault("columns", [])
            if not columns and isinstance(row_data, dict):
                for key in row_data.keys():
                    columns.append({"name": key, "type": "text"})
            rows = self._table_data.setdefault("rows", [])
            if write_mode == "append":
                rows.append(row_data)
                logger.info(f"[ExtensionRunner] writeTableRow append = {row_data!r}")
            elif write_mode == "insert":
                row_idx = max(0, min(row_idx, len(rows)))
                rows.insert(row_idx, row_data)
                logger.info(f"[ExtensionRunner] writeTableRow insert [{row_idx}] = {row_data!r}")
            else:  # overwrite
                while len(rows) <= row_idx:
                    rows.append({})
                rows[row_idx] = row_data
                logger.info(f"[ExtensionRunner] writeTableRow overwrite [{row_idx}] = {row_data!r}")
            self._table_dirty = True
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"writeTableRow": row_data},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"writeTableRow": row_data, "tableData": self._table_data},
            })
            return True

        if cmd_type == "custom":
            code = extra.get("code", "")
            result_var = _get_output_var(extra)
            description = extra.get("description", "")
            if not code.strip():
                self.results.append({
                    "stepId": step_id,
                    "nodeId": instr.get("nodeId"),
                    "status": "success",
                    "result": {"custom": True, "note": "empty code"},
                })
                self.completed += 1
                await self._emit({
                    "type": "stepComplete",
                    "stepId": step_id,
                    "nodeId": instr.get("nodeId"),
                    "result": {"custom": True},
                })
                return True
            print_buffer = []
            def _custom_print(*args, **kwargs):
                line = " ".join(str(a) for a in args)
                print_buffer.append(line)
                logger.info(f"[custom print] {line}")
            safe_globals = {
                "__builtins__": {
                    "len": len, "range": range, "enumerate": enumerate,
                    "zip": zip, "map": map, "filter": filter,
                    "int": int, "float": float, "str": str, "bool": bool,
                    "list": list, "dict": dict, "set": set, "tuple": tuple,
                    "abs": abs, "min": min, "max": max, "sum": sum,
                    "round": round, "pow": pow, "divmod": divmod,
                    "sorted": sorted, "reversed": reversed,
                    "isinstance": isinstance, "hasattr": hasattr, "getattr": getattr,
                    "chr": chr, "ord": ord,
                    "print": _custom_print,
                },
                "json": __import__("json"),
                "re": __import__("re"),
                "math": __import__("math"),
                "datetime": __import__("datetime"),
                "time": __import__("time"),
                "random": __import__("random"),
            }
            _table = _TableAccessor(self._table_data)
            safe_locals = dict(self.vars)
            safe_locals["_table_data"] = self._table_data
            safe_locals["_table"] = _table
            safe_locals["_table_dirty"] = False
            try:
                exec(code, safe_globals, safe_locals)
                # Write back modified vars (excluding internals)
                for k, v in safe_locals.items():
                    if not k.startswith("_"):
                        self.vars[k] = v
                # Write back table data if modified
                if safe_locals.get("_table_dirty") or _table.dirty:
                    self._table_data = safe_locals["_table_data"]
                    self._table_dirty = True
                result = safe_locals.get("_result", None)
                if result_var:
                    self.vars[result_var] = result
                logger.info(f"[ExtensionRunner] custom executed: {description or 'no desc'}")
                self.results.append({
                    "stepId": step_id,
                    "nodeId": instr.get("nodeId"),
                    "status": "success",
                    "result": {"custom": True},
                })
                self.completed += 1
                await self._emit({
                    "type": "stepComplete",
                    "stepId": step_id,
                    "nodeId": instr.get("nodeId"),
                    "result": {"custom": True, "result": result, "prints": print_buffer},
                })
                return True
            except Exception as e:
                logger.error(f"[ExtensionRunner] custom failed: {e}")
                self.failed_steps.append({
                    "stepId": step_id,
                    "nodeId": instr.get("nodeId"),
                    "instruction": instr,
                    "error": str(e),
                })
                self.results.append({
                    "stepId": step_id,
                    "nodeId": instr.get("nodeId"),
                    "status": "error",
                    "error": str(e),
                })
                await self._emit({
                    "type": "stepError",
                    "stepId": step_id,
                    "nodeId": instr.get("nodeId"),
                    "error": str(e),
                })
                return False

        # Unknown local command — fail so we know to register a handler
        self.failed_steps.append({
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "instruction": instr,
            "error": f"No local handler for {cmd_type}",
        })
        self.results.append({
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "status": "error",
            "error": f"No local handler for {cmd_type}",
        })
        await self._emit({
            "type": "stepError",
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "error": f"No local handler for {cmd_type}",
        })
        return False

    async def _execute_instruction(self, instr: dict) -> bool:
        step_id = instr["stepId"]
        step_type = instr.get("type", "")
        extra = instr.get("extra") or {}
        on_error = extra.get("onError", "stop")
        retry_count = extra.get("retryCount", 0)
        timeout = extra.get("timeout", DEFAULT_STEP_TIMEOUT)

        # Compound instructions (loops, conditions, break, continue, try)
        if instr.get("compound"):
            try:
                return await self._handle_compound(instr)
            except LoopBreak:
                # Propagate to outer loop handler; if no outer loop, just stop
                raise
            except LoopContinue:
                raise
            except Exception as e:
                logger.error(f"[ExtensionRunner] compound {instr.get('cmdType')} failed: {e}")
                self.failed_steps.append({
                    "stepId": step_id,
                    "nodeId": instr.get("nodeId"),
                    "instruction": instr,
                    "error": str(e),
                })
                self.results.append({
                    "stepId": step_id,
                    "nodeId": instr.get("nodeId"),
                    "status": "error",
                    "error": str(e),
                })
                await self._emit({
                    "type": "stepError",
                    "stepId": step_id,
                    "nodeId": instr.get("nodeId"),
                    "error": str(e),
                })
                if on_error == "stop":
                    return False
                elif on_error == "continue":
                    self.completed += 1
                    return True
                return False

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

                # Soft "not found" inside a loop (contextNotFound) is reported as a
                # warning by the extension. Honor the node's onError policy: "continue"
                # keeps the empty value, anything else treats it as a real failure so
                # that a missing element does not silently become blank text.
                if (
                    isinstance(result, dict)
                    and result.get("contextNotFound")
                    and on_error != "continue"
                ):
                    last_error = result.get("warning") or f"{cmd_type}: 元素在当前循环项中未找到"
                    logger.warning(
                        f"[ExtensionRunner] {step_id} {cmd_type} contextNotFound "
                        f"with onError={on_error}, treating as failure"
                    )
                    break

                self.results.append({
                    "stepId": step_id,
                    "nodeId": instr.get("nodeId"),
                    "status": "success",
                    "result": result,
                })
                self.completed += 1

                # Surface soft warnings (e.g. a child element was absent inside the
                # current loop item → empty value + continue). These are not errors:
                # the run proceeds, but the user must see them rather than silently
                # collecting blanks.
                if isinstance(result, dict) and result.get("warning"):
                    warning_msg = result["warning"]
                    logger.warning(f"[ExtensionRunner] {step_id} {cmd_type} warning: {warning_msg}")
                    await self._emit({
                        "type": "stepWarning",
                        "stepId": step_id,
                        "nodeId": instr.get("nodeId"),
                        "cmdType": cmd_type,
                        "warning": warning_msg,
                    })

                if isinstance(result, dict) and "matchedCount" in result:
                    logger.info(
                        f"[ExtensionRunner] {step_id} {cmd_type} matched "
                        f"{result['matchedCount']} element(s) for locator={resolved_instr.get('locator')}"
                    )

                await self._emit({
                    "type": "stepComplete",
                    "stepId": step_id, "nodeId": instr.get("nodeId"),
                    "result": result,
                })

                # Save results to variable if requested (extracted, navigatedTo, or whole result)
                save_to_var = _get_output_var(resolved_instr.get("extra") or {})
                logger.info(
                    f"[ExtensionRunner] save check step={step_id} cmd={cmd_type} "
                    f"save_to_var={save_to_var!r} result={result!r}"
                )
                if save_to_var and result:
                    if isinstance(result, dict):
                        if "extracted" in result:
                            value = result["extracted"]
                        elif "navigatedTo" in result:
                            value = result["navigatedTo"]
                        elif "value" in result:
                            value = result["value"]
                        else:
                            value = result
                    else:
                        value = result
                    self.vars[save_to_var] = value
                    logger.info(f"[ExtensionRunner] saved result to var {save_to_var}: {value!r}")

                # Update window variable tabId when navigation creates/switches tabs
                window_var = (resolved_instr.get("extra") or {}).get("windowVar")
                if window_var and isinstance(result, dict) and result.get("tabId") is not None:
                    window_val = self.vars.get(window_var)
                    tab_id = result["tabId"]
                    window_id = result.get("windowId")
                    if isinstance(window_val, dict):
                        window_val["tabId"] = tab_id
                        if window_id is not None:
                            window_val["windowId"] = window_id
                        logger.info(f"[ExtensionRunner] updated {window_var} tabId={tab_id}")
                    elif window_val is not None:
                        try:
                            wid = int(window_val)
                        except (ValueError, TypeError):
                            wid = window_val
                        self.vars[window_var] = {
                            "windowId": window_id if window_id is not None else wid,
                            "tabId": tab_id,
                        }
                        logger.info(f"[ExtensionRunner] upgraded {window_var} to dict with tabId={tab_id}")

                return True
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[ExtensionRunner] {step_id} attempt {attempt + 1}/{retry_count + 1} failed: {e}")
                if self._stopped:
                    logger.info(f"[ExtensionRunner] {step_id} stop requested, breaking retry loop")
                    break
                if attempt < retry_count:
                    await asyncio.sleep(1.0)

        # All retries exhausted
        self._last_error = last_error
        locator = resolved_instr.get("locator")
        locator_part = f" locator={locator}" if locator else ""
        rich_error = f"[{step_id} node={instr.get('nodeId')} cmd={cmd_type}{locator_part}] {last_error}"
        result_entry = {
            "stepId": step_id, "nodeId": instr.get("nodeId"),
            "status": "error", "error": rich_error,
        }
        error_event = {
            "type": "stepError",
            "stepId": step_id, "nodeId": instr.get("nodeId"),
            "error": rich_error,
        }
        if self._try_depth > 0:
            # Errors inside a try block are caught by the try handler; don't count
            # them as uncaught workflow failures in the final summary popup.
            result_entry["caught"] = True
            error_event["caught"] = True
            self.results.append(result_entry)
            await self._emit(error_event)
        else:
            self.failed_steps.append({
                "stepId": step_id, "nodeId": instr.get("nodeId"),
                "instruction": instr, "error": rich_error,
            })
            self.results.append(result_entry)
            await self._emit(error_event)

        if on_error == "stop":
            return False
        elif on_error == "continue":
            self.completed += 1
            return True
        else:
            return False

    async def _send_and_wait(self, step_id: str, instr: dict, timeout: float) -> Any:
        """Send executeStep to extension and wait for result."""
        await self._ensure_connected()
        conn = ext_manager.get_connection(self.client_id)
        if not conn:
            raise RuntimeError(f"Extension {self.client_id} is not connected")

        # Resolve explicit window variable -> windowId/tabId for extension routing
        extra = dict(instr.get("extra") or {})
        window_var = extra.get("windowVar")
        if window_var:
            window_val = self.vars.get(window_var)
            if window_val is None:
                raise RuntimeError(f"窗口变量 '{window_var}' 未定义，请先执行打开浏览器指令")
            if isinstance(window_val, dict):
                if window_val.get("windowId") is not None:
                    extra["windowId"] = window_val.get("windowId")
                if window_val.get("tabId") is not None:
                    extra["tabId"] = window_val.get("tabId")
            else:
                try:
                    extra["windowId"] = int(window_val)
                except (ValueError, TypeError):
                    extra["windowId"] = window_val
            instr = {**instr, "extra": extra}

        # Inject loop context into extra so content.js resolves locators by index alignment
        ctx = self._resolve_loop_context(extra)
        if ctx:
            extra["contextLocator"] = ctx["locator"]
            extra["contextLocatorType"] = ctx["selectorFamily"]
            extra["contextIndex"] = ctx["index"]
            extra["contextTotal"] = ctx.get("total")
            # Prefer the capture-time relative selector when present (see
            # _call_extension_handler for the rationale).
            if extra.get("relativeLocator") and extra.get("useRelative", True):
                extra["useRelative"] = True
            logger.info(
                f"[ExtensionRunner] loop context index={ctx['index'] + 1}/{ctx.get('total', '?')} "
                f"locator={ctx['locator'][:60]}..."
            )
            instr = {**instr, "extra": extra}

        # Register future BEFORE sending to avoid race with fast responses (e.g. navigate)
        future = await ext_manager.register_step_future(step_id)
        try:
            ok = await ext_manager.send_to(
                self.client_id,
                "executeStep",
                {"stepId": step_id, "nodeId": instr.get("nodeId"), **instr},
            )
            if not ok:
                await ext_manager.cancel_step_future(step_id)
                raise RuntimeError(f"Failed to send step {step_id} to extension")

            resp = await self._wait_future_with_stop(future, timeout=timeout)
            if resp["status"] == "error":
                raise RuntimeError(resp.get("error", "Unknown extension error"))
            return resp.get("result")
        except asyncio.TimeoutError:
            await ext_manager.cancel_step_future(step_id)
            raise TimeoutError(f"Step {step_id} timed out after {timeout}s")
        except asyncio.CancelledError:
            await ext_manager.cancel_step_future(step_id)
            raise


async def run_workflow_extension(wf: models.Workflow, nodes: list[models.WorkflowNode],
                                  client_id: str | None = None,
                                  run_id: str | None = None,
                                  initial_table_data: dict | None = None,
                                  initial_parameters: dict | None = None,
                                  trigger_type: str = "manual") -> dict:
    """
    Convenience entry point.
    If client_id is None, connection is deferred until the first extension
    instruction is encountered (on-demand connection).
    initial_table_data: {"columns": [...], "rows": [...]} passed from frontend.
    initial_parameters: {"varName": "value"} overrides workflow parameter defaults.
    trigger_type: manual / scheduled
    """
    import time
    import json as _json
    from src.config import runtime_config as config

    _run_id = run_id or f"run_{int(time.time() * 1000)}"

    # 创建日志目录（打包后通过 RPA_LOG_DIR 指向持久化用户目录）
    log_root = os.environ.get("RPA_LOG_DIR", config.REPO_DIR)
    log_dir = os.path.join(log_root, "data", "run_logs", str(wf.id), _run_id)
    os.makedirs(log_dir, exist_ok=True)

    # 提前注册进度队列，让 SSE 在 runner 启动前就能连上（wait_for_extension 可能耗时数秒）
    pre_queue = asyncio.Queue()
    await run_progress.register(_run_id, pre_queue)

    runner = ExtensionRunner(client_id or "", run_id=_run_id, log_dir=log_dir, queue=pre_queue, workflow_id=wf.id)

    # Initialize workflow-level parameters (design-time defaults + runtime overrides)
    param_defaults = {}
    try:
        wf_params = _json.loads(wf.parameters or "[]") if hasattr(wf, "parameters") else []
    except Exception:
        wf_params = []
    for p in wf_params:
        name = p.get("name")
        if name:
            param_defaults[name] = p.get("default")
    if initial_parameters:
        param_defaults.update(initial_parameters)
    runner.vars.update(param_defaults)
    logger.info(f"[run_workflow_extension] initialized parameters: {list(runner.vars.keys())}")

    # Initialize table data from frontend payload (runtime variable, no DB)
    if initial_table_data:
        runner._table_data = {
            "columns": initial_table_data.get("columns", []),
            "rows": initial_table_data.get("rows", []),
        }
        logger.info(
            f"[run_workflow_extension] initialized table from payload "
            f"cols={len(runner._table_data['columns'])} rows={len(runner._table_data['rows'])}"
        )

    result: dict = {}
    stopped = False
    try:
        result = await runner.run(wf, nodes)
    except asyncio.CancelledError:
        stopped = True
        result = {
            "runId": runner.run_id,
            "success": False,
            "stopped": True,
            "completedSteps": runner.completed,
            "totalSteps": 0,
            "failedSteps": runner.failed_steps,
            "results": runner.results,
            "error": "Run stopped by user",
        }
    finally:
        # Cache for "last run result" panel (runtime-only, no DB flush)
        _last_run_tables[wf.id] = {
            "columns": runner._table_data.get("columns", []),
            "rows": runner._table_data.get("rows", []),
            "runId": runner.run_id,
            "success": False if stopped else (result.get("success", False) if result else False),
        }
        await run_progress.unregister(_run_id)

    result["tableRows"] = runner._table_data.get("rows", [])
    result["tableColumns"] = runner._table_data.get("columns", [])
    result["logDir"] = log_dir
    return result


# ─── Local command handlers ───────────────────────────────────────
# Register simple backend-only commands here. Each handler receives:
#   runner: ExtensionRunner instance
#   cmd_type: command type string
#   step_id: current step id
#   instr: instruction dict


@register_local("setVar")
async def _local_setVar(runner: "ExtensionRunner", cmd_type: str, step_id: str, instr: dict) -> bool:
    extra = instr.get("extra") or {}
    var_name = _clean_var_ref(extra.get("name", ""))
    var_value = runner._resolve_vars(extra.get("value", ""), runner.vars)
    vtype = extra.get("valueType", "string")
    if vtype == "number":
        try:
            var_value = float(var_value)
        except (ValueError, TypeError):
            pass
    elif vtype == "bool":
        var_value = str(var_value).lower() in ("true", "1", "yes")
    elif vtype == "list":
        try:
            var_value = json.loads(var_value)
        except Exception:
            try:
                var_value = ast.literal_eval(var_value)
            except Exception:
                var_value = []
    elif vtype == "dict":
        try:
            var_value = json.loads(var_value)
        except Exception:
            try:
                var_value = ast.literal_eval(var_value)
            except Exception:
                var_value = {}
    elif vtype == "string":
        val_str = str(var_value)
        if "+" in val_str:
            parts = val_str.split("+")
            has_quoted = any(
                (p.strip().startswith('"') and p.strip().endswith('"')) or
                (p.strip().startswith("'") and p.strip().endswith("'"))
                for p in parts
            )
            if has_quoted:
                merged = []
                for p in parts:
                    p = p.strip()
                    if (p.startswith('"') and p.endswith('"')) or (p.startswith("'") and p.endswith("'")):
                        p = p[1:-1]
                    merged.append(p)
                var_value = "".join(merged)
    runner.vars[var_name] = var_value
    logger.info(f"[ExtensionRunner] setVar {var_name} = {var_value!r}")
    runner.results.append({
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "status": "success",
        "result": {"setVar": var_name, "value": var_value},
    })
    runner.completed += 1
    await runner._emit({
        "type": "stepComplete",
        "stepId": step_id, "nodeId": instr.get("nodeId"),
        "result": {"setVar": var_name, "value": var_value},
    })
    return True


@register_local("log")
async def _local_log(runner: "ExtensionRunner", cmd_type: str, step_id: str, instr: dict) -> bool:
    extra = instr.get("extra") or {}
    msg = extra.get("message", "")
    level = extra.get("level", "info")
    logger.info(f"[ExtensionRunner] LOG vars={list(runner.vars.keys())} msg={msg!r}")
    resolved_msg = runner._resolve_vars(msg, runner.vars)
    logger.info(f"[ExtensionRunner] LOG [{level}] {resolved_msg}")
    runner.results.append({
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "status": "success",
        "result": {"log": resolved_msg},
    })
    runner.completed += 1
    await runner._emit({
        "type": "stepComplete",
        "stepId": step_id, "nodeId": instr.get("nodeId"),
        "result": {"log": resolved_msg},
    })
    return True


@register_local("openBrowser")
async def _local_openBrowser(runner: "ExtensionRunner", cmd_type: str, step_id: str, instr: dict) -> bool:
    """Launch the browser with the RPA extension and wait for it to connect."""
    extra = instr.get("extra") or {}
    browser_type = extra.get("browserType", "chrome")
    url = extra.get("url") or "about:blank"
    state = extra.get("windowState", "normal")

    logger.info(f"[ExtensionRunner] openBrowser type={browser_type} url={url} state={state}")

    # Browser launch is the caller's responsibility; if already running we reuse it.
    if not is_browser_running(browser_type):
        logger.info(f"[{browser_type}] 浏览器未运行，启动并加载扩展...")
        if not launch_browser_with_extension(browser_type):
            raise RuntimeError(f"无法启动 {browser_type}，请检查浏览器安装路径")
        # Give the browser process a moment to start
        await asyncio.sleep(3.0)
    else:
        logger.info(f"[{browser_type}] 浏览器已在运行，等待扩展连接...")

    runner.client_id = await wait_for_extension_connection(browser_type, ext_manager, timeout=10.0)
    if not runner._run_started_sent:
        runner._run_started_sent = True
        await ext_manager.send_to(runner.client_id, "runStarted", {"runId": runner.run_id})

    # Ask the extension to create/reuse the work window with the requested URL/state.
    # background.js openBrowser will set workWindowId/workTabId for subsequent steps.
    result = await runner._send_and_wait(step_id, instr, timeout=DEFAULT_STEP_TIMEOUT)

    # Persist the window object so later steps can reference it via windowVar.
    save_to_var = _get_output_var(extra)
    if save_to_var and isinstance(result, dict):
        runner.vars[save_to_var] = {
            "windowId": result.get("windowId"),
            "tabId": result.get("tabId"),
        }
        logger.info(f"[ExtensionRunner] openBrowser saved window to {save_to_var}: {runner.vars[save_to_var]!r}")

    runner.results.append({
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "status": "success",
        "result": {"openBrowser": browser_type, "clientId": runner.client_id, "initialResult": result},
    })
    runner.completed += 1
    await runner._emit({
        "type": "stepComplete",
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "result": {"openBrowser": browser_type, "clientId": runner.client_id},
    })
    return True


@register_local("appendToList")
async def _local_appendToList(runner: "ExtensionRunner", cmd_type: str, step_id: str, instr: dict) -> bool:
    extra = instr.get("extra") or {}
    list_name = _clean_var_ref(extra.get("listName", ""))
    value = extra.get("value", "")
    resolved_value = runner._resolve_vars(value, runner.vars)
    if list_name not in runner.vars or not isinstance(runner.vars[list_name], list):
        runner.vars[list_name] = []
    runner.vars[list_name].append(resolved_value)
    logger.info(f"[ExtensionRunner] appendToList {list_name} += {resolved_value!r}")
    runner.results.append({
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "status": "success",
        "result": {"appendToList": list_name, "value": resolved_value},
    })
    runner.completed += 1
    await runner._emit({
        "type": "stepComplete",
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "result": {"appendToList": list_name},
    })
    return True


@register_local("setDictValue")
async def _local_setDictValue(runner: "ExtensionRunner", cmd_type: str, step_id: str, instr: dict) -> bool:
    extra = instr.get("extra") or {}
    dict_name = _clean_var_ref(extra.get("dictName", ""))
    key = runner._resolve_vars(str(extra.get("key", "")), runner.vars)
    value = runner._resolve_vars(str(extra.get("value", "")), runner.vars)
    if dict_name not in runner.vars or not isinstance(runner.vars[dict_name], dict):
        runner.vars[dict_name] = {}
    runner.vars[dict_name][key] = value
    logger.info(f"[ExtensionRunner] setDictValue {dict_name}[{key}] = {value!r}")
    runner.results.append({
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "status": "success",
        "result": {"setDictValue": dict_name, "key": key, "value": value},
    })
    runner.completed += 1
    await runner._emit({
        "type": "stepComplete",
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "result": {"setDictValue": dict_name},
    })
    return True


@register_local("getDictValue")
async def _local_getDictValue(runner: "ExtensionRunner", cmd_type: str, step_id: str, instr: dict) -> bool:
    extra = instr.get("extra") or {}
    dict_name = _clean_var_ref(extra.get("dictName", ""))
    key = runner._resolve_vars(str(extra.get("key", "")), runner.vars)
    target_var = _get_output_var(extra)
    d = runner.vars.get(dict_name, {})
    result = d.get(key) if isinstance(d, dict) else None
    if target_var:
        runner.vars[target_var] = result
    logger.info(f"[ExtensionRunner] getDictValue {dict_name}[{key}] -> {target_var} = {result!r}")
    runner.results.append({
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "status": "success",
        "result": {"getDictValue": dict_name, "key": key, "value": result},
    })
    runner.completed += 1
    await runner._emit({
        "type": "stepComplete",
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "result": {"getDictValue": dict_name, "value": result},
    })
    return True


@register_local("removeDictKey")
async def _local_removeDictKey(runner: "ExtensionRunner", cmd_type: str, step_id: str, instr: dict) -> bool:
    extra = instr.get("extra") or {}
    dict_name = _clean_var_ref(extra.get("dictName", ""))
    key = runner._resolve_vars(str(extra.get("key", "")), runner.vars)
    d = runner.vars.get(dict_name, {})
    removed = False
    if isinstance(d, dict) and key in d:
        del d[key]
        removed = True
    logger.info(f"[ExtensionRunner] removeDictKey {dict_name}[{key}] removed={removed}")
    runner.results.append({
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "status": "success",
        "result": {"removeDictKey": dict_name, "key": key, "removed": removed},
    })
    runner.completed += 1
    await runner._emit({
        "type": "stepComplete",
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "result": {"removeDictKey": dict_name},
    })
    return True


@register_local("stringConcat")
async def _local_stringConcat(runner: "ExtensionRunner", cmd_type: str, step_id: str, instr: dict) -> bool:
    extra = instr.get("extra") or {}
    target_var = _clean_var_ref(extra.get("targetVar", ""))
    part1 = runner._resolve_vars(str(extra.get("part1", "")), runner.vars)
    part2 = runner._resolve_vars(str(extra.get("part2", "")), runner.vars)
    part3 = runner._resolve_vars(str(extra.get("part3", "")), runner.vars)
    result = part1 + part2 + part3
    runner.vars[target_var] = result
    logger.info(f"[ExtensionRunner] stringConcat {target_var} = {result!r}")
    runner.results.append({
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "status": "success",
        "result": {"stringConcat": target_var, "value": result},
    })
    runner.completed += 1
    await runner._emit({
        "type": "stepComplete",
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "result": {"stringConcat": target_var},
    })
    return True


@register_local("increment")
async def _local_increment(runner: "ExtensionRunner", cmd_type: str, step_id: str, instr: dict) -> bool:
    extra = instr.get("extra") or {}
    var_name = _clean_var_ref(extra.get("varName", ""))
    step = extra.get("step", 1)
    try:
        step = float(step)
    except (ValueError, TypeError):
        step = 1
    current = runner.vars.get(var_name, 0)
    try:
        current = float(current)
    except (ValueError, TypeError):
        current = 0
    runner.vars[var_name] = current + step
    logger.info(f"[ExtensionRunner] increment {var_name} += {step}")
    runner.results.append({
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "status": "success",
        "result": {"increment": var_name, "value": runner.vars[var_name]},
    })
    runner.completed += 1
    await runner._emit({
        "type": "stepComplete",
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "result": {"increment": var_name},
    })
    return True


@register_local("sleep")
async def _local_sleep(runner: "ExtensionRunner", cmd_type: str, step_id: str, instr: dict) -> bool:
    extra = instr.get("extra") or {}
    seconds = float(extra.get("seconds", 1.0))
    ms = int(seconds * 1000)
    logger.info(f"[ExtensionRunner] sleep {seconds}s")
    await runner._interruptible_sleep(seconds)
    runner.results.append({
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "status": "success",
        "result": {"waited": ms},
    })
    runner.completed += 1
    await runner._emit({
        "type": "stepComplete",
        "stepId": step_id, "nodeId": instr.get("nodeId"),
        "result": {"waited": ms},
    })
    return True


@register_local("randomSleep")
async def _local_randomSleep(runner: "ExtensionRunner", cmd_type: str, step_id: str, instr: dict) -> bool:
    import random
    extra = instr.get("extra") or {}
    min_sec = float(extra.get("minSeconds", 1.0))
    max_sec = float(extra.get("maxSeconds", 3.0))
    seconds = random.uniform(min_sec, max_sec)
    ms = int(seconds * 1000)
    logger.info(f"[ExtensionRunner] randomSleep {seconds:.3f}s (min={min_sec}, max={max_sec})")
    await runner._interruptible_sleep(seconds)
    runner.results.append({
        "stepId": step_id,
        "nodeId": instr.get("nodeId"),
        "status": "success",
        "result": {"waited": ms, "min": min_sec, "max": max_sec},
    })
    runner.completed += 1
    await runner._emit({
        "type": "stepComplete",
        "stepId": step_id, "nodeId": instr.get("nodeId"),
        "result": {"waited": ms, "min": min_sec, "max": max_sec},
    })
    return True
