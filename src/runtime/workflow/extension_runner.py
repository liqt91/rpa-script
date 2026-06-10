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
from typing import Any

import httpx
import time

from src.runtime.websocket_manager import ext_manager
from .extension_emitter import build_instructions
from .commands import COMMAND_REGISTRY
from src.providers import run_progress
from src.repo import runtime_models as models
from src.repo.models import SessionLocal

logger = logging.getLogger(__name__)

DEFAULT_STEP_TIMEOUT = 30.0

_VAR_PLACEHOLDER_RE = re.compile(r"\$\{(\w+)\}|\{\{(\w+)\}\}")

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


async def wait_for_extension(
    browser_type: str,
    ext_manager,
    timeout: float = 10.0,
) -> str:
    """等待指定浏览器的扩展 WebSocket 连接上线。

    只轮询等待，不自动启动浏览器。
    返回 client_id，超时抛出 TimeoutError。
    """
    if ext_manager is None:
        from src.runtime.websocket_manager import ext_manager as _em
        ext_manager = _em

    # 1. 已在线？
    conns = ext_manager.connections_by_browser(browser_type)
    if conns:
        logger.info(f"[{browser_type}] 扩展已在线: {conns[0].client_id}")
        return conns[0].client_id

    # 2. 扩展可能刚连接但还没 register，先短暂等待
    if ext_manager.is_any_online:
        await asyncio.sleep(2)
        conns = ext_manager.connections_by_browser(browser_type)
        if conns:
            logger.info(f"[{browser_type}] 扩展注册后已在线: {conns[0].client_id}")
            return conns[0].client_id

    # 3. 指数退避轮询等待扩展连接（不启动浏览器）
    start = time.time()
    delay = 0.5
    logger.info(f"[{browser_type}] 扩展未连接，等待中（不会自动启动浏览器）...")

    while time.time() - start < timeout:
        conns = ext_manager.connections_by_browser(browser_type)
        if conns:
            return conns[0].client_id

        await asyncio.sleep(delay)
        delay = min(delay * 1.5, 5.0)

    raise TimeoutError(
        f"{browser_type} 扩展未在 {timeout}s 内连接，请手动启动浏览器并确认扩展已安装启用"
    )


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

# Cache latest run table result per workflow (runtime-only, memory)
_last_run_tables: dict[int, dict] = {}


class ExtensionRunner:
    def __init__(self, client_id: str, run_id: str | None = None, log_dir: str | None = None, queue: asyncio.Queue | None = None):
        self.client_id = client_id
        self.run_id = run_id or f"run_{id(self)}"
        self.vars: dict[str, Any] = {}
        self.results: list[dict] = []
        self.completed = 0
        self.failed_steps: list[dict] = []
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
        run_progress.register(self.run_id, self.queue)

    def pause(self) -> None:
        if not self._stopped:
            self._paused.clear()
            logger.info(f"[ExtensionRunner] run_id={self.run_id} paused")

    def resume(self) -> None:
        self._paused.set()
        self._pause_event_sent = False
        logger.info(f"[ExtensionRunner] run_id={self.run_id} resumed")

    def stop(self) -> None:
        self._stopped = True
        self._paused.set()  # wake up if currently paused
        # Cancel the pending step future so _wait_future_with_stop exits immediately
        if self._current_step:
            step_id = self._current_step.get("stepId")
            if step_id:
                try:
                    ext_manager.cancel_step_future(step_id)
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
        self.client_id = await wait_for_extension(browser_type, ext_manager, timeout=10.0)
        if not self._run_started_sent:
            self._run_started_sent = True
            await ext_manager.send_to(self.client_id, "runStarted", {"runId": self.run_id})

    async def _emit(self, event: dict) -> None:
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

    async def run(self, wf: models.Workflow, nodes: list[models.WorkflowNode]) -> dict:
        """Run workflow nodes through the extension. Returns execution report."""
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

        _active_runners[self.run_id] = self
        try:
            for instr in instructions:
                self._current_step = instr
                if not await self._wait_if_paused():
                    break
                await self._emit({
                    "type": "stepStart",
                    "stepId": instr.get("stepId"),
                    "nodeId": instr.get("nodeId"),
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
            run_progress.unregister(self.run_id)
            _active_runners.pop(self.run_id, None)

    @staticmethod
    def _resolve_vars(obj: Any, vars_dict: dict[str, Any]) -> Any:
        """Recursively replace ${var} and {{var}} placeholders in strings."""
        if isinstance(obj, str):
            def _repl(m):
                key = m.group(1) or m.group(2)
                if key in vars_dict:
                    return str(vars_dict[key])
                logger.warning(f"[ExtensionRunner] resolve_vars: key '{key}' not found in vars={list(vars_dict.keys())}")
                return m.group(0)
            return _VAR_PLACEHOLDER_RE.sub(_repl, obj)
        if isinstance(obj, list):
            return [ExtensionRunner._resolve_vars(item, vars_dict) for item in obj]
        if isinstance(obj, dict):
            return {k: ExtensionRunner._resolve_vars(v, vars_dict) for k, v in obj.items()}
        return obj

    async def _call_extension_handler(self, handler: str, payload: dict, timeout: float = DEFAULT_STEP_TIMEOUT) -> Any:
        """Call a specific extension handler and return the result."""
        await self._ensure_connected()
        conn = ext_manager.get_connection(self.client_id)
        if not conn:
            raise RuntimeError(f"Extension {self.client_id} is not connected")

        # Inject loop context into extra so content.js resolves locators relative to current element
        ctx = self.vars.get("__loop_ctx")
        if ctx:
            extra = dict(payload.get("extra") or {})
            if extra.get("scope", "local") != "global":
                extra["contextLocator"] = ctx["locator"]
                extra["contextLocatorType"] = ctx["selectorFamily"]
                extra["contextIndex"] = ctx["index"]
                payload = {**payload, "extra": extra}

        step_id = self._next_step_id()
        node_id = payload.get("nodeId") or (self._current_step.get("nodeId") if self._current_step else None)
        instr = {
            "stepId": step_id, "nodeId": node_id,
            "type": handler,
            **payload,
        }
        logger.info(f"[ExtensionRunner] -> ext handler={handler} stepId={step_id} payload={payload}")
        future = ext_manager.register_step_future(step_id)
        try:
            ok = await ext_manager.send_to(
                self.client_id,
                "executeStep",
                {"stepId": step_id, "nodeId": node_id, **instr},
            )
            if not ok:
                ext_manager.cancel_step_future(step_id)
                raise RuntimeError(f"Failed to send {handler} to extension")

            resp = await self._wait_future_with_stop(future, timeout=timeout)
            if resp["status"] == "error":
                raise RuntimeError(resp.get("error", f"Extension {handler} failed"))
            result = resp.get("result", {})
            logger.info(f"[ExtensionRunner] <- ext handler={handler} stepId={step_id} result={result}")
            return result
        except asyncio.TimeoutError:
            ext_manager.cancel_step_future(step_id)
            raise TimeoutError(f"{handler} timed out after {timeout}s")
        except asyncio.CancelledError:
            ext_manager.cancel_step_future(step_id)
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
            payload_extra = {"visibleOnly": visible_only, "timeout": timeout}
            if extra:
                payload_extra["scope"] = extra.get("scope", "local")
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
                f"locators={locators} timeout={timeout} operator={op}"
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
            if op == "notContains":
                return expected not in text
            if op == "startsWith":
                return text.startswith(expected)
            if op == "endsWith":
                return text.endswith(expected)
            return expected in text
        if cmd_type == "ifTextEquals":
            text = await self._get_element_text(locator, selector_family, timeout=timeout, extra=extra)
            expected = extra.get("text", "")
            return text == expected
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

            elements = await self._find_elements(locator, selector_family, timeout=timeout, extra=extra)
            logger.info(f"[ExtensionRunner] forEachElement found {len(elements)} elements")
            prev_ctx = self.vars.get("__loop_ctx")
            for idx, item in enumerate(elements):
                if self._stopped:
                    break
                self.vars[idx_var] = idx
                self.vars[item_var] = item.get("text", "") if isinstance(item, dict) else str(item)
                # Set loop context so child instructions resolve locators relative to current element
                self.vars["__loop_ctx"] = {
                    "locator": locator,
                    "selectorFamily": selector_family,
                    "index": idx,
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
            if prev_ctx is not None:
                self.vars["__loop_ctx"] = prev_ctx
            else:
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
            for _iter in range(max_iter):
                if self._stopped:
                    break
                condition_met = (await self._evaluate_condition(instr))["met"]
                logger.info(f"[ExtensionRunner] whileCondition iter={_iter} met={condition_met}")
                if not condition_met:
                    break
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
            try:
                success = await self._run_body(body)
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
                self.vars[error_var] = str(e)
                logger.info(f"[ExtensionRunner] catch {error_var}={str(e)!r}")
                success = await self._run_body(else_body)
                self.completed += 1
                await self._emit({
                    "type": "stepComplete",
                    "stepId": step_id,
                    "nodeId": instr.get("nodeId"),
                    "result": {"try": "caught", "error": str(e)},
                })
                return success

        logger.warning(f"[ExtensionRunner] Unknown compound instruction: {cmd_type}")
        return True

    async def _handle_local(self, cmd_type: str, step_id: str, instr: dict) -> bool:
        """Execute a locally-handled command (backend-only, no extension round-trip)."""
        extra = instr.get("extra") or {}
        if cmd_type == "setVar":
            var_name = _clean_var_ref(extra.get("name", ""))
            var_value = self._resolve_vars(extra.get("value", ""), self.vars)
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
                # Support simple string concatenation: "a" + "b" or a + "b"
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
            self.vars[var_name] = var_value
            logger.info(f"[ExtensionRunner] setVar {var_name} = {var_value!r}")
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"setVar": var_name, "value": var_value},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id, "nodeId": instr.get("nodeId"),
                "result": {"setVar": var_name, "value": var_value},
            })
            return True

        if cmd_type == "log":
            msg = extra.get("message", "")
            level = extra.get("level", "info")
            logger.info(f"[ExtensionRunner] LOG vars={list(self.vars.keys())} msg={msg!r}")
            resolved_msg = self._resolve_vars(msg, self.vars)
            logger.info(f"[ExtensionRunner] LOG [{level}] {resolved_msg}")
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"log": resolved_msg},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id, "nodeId": instr.get("nodeId"),
                "result": {"log": resolved_msg},
            })
            return True

        if cmd_type == "appendToList":
            list_name = _clean_var_ref(extra.get("listName", ""))
            value = extra.get("value", "")
            resolved_value = self._resolve_vars(value, self.vars)
            if list_name not in self.vars or not isinstance(self.vars[list_name], list):
                self.vars[list_name] = []
            self.vars[list_name].append(resolved_value)
            logger.info(f"[ExtensionRunner] appendToList {list_name} += {resolved_value!r}")
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"appendToList": list_name, "value": resolved_value},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"appendToList": list_name},
            })
            return True

        if cmd_type == "setDictValue":
            dict_name = _clean_var_ref(extra.get("dictName", ""))
            key = self._resolve_vars(str(extra.get("key", "")), self.vars)
            value = self._resolve_vars(str(extra.get("value", "")), self.vars)
            if dict_name not in self.vars or not isinstance(self.vars[dict_name], dict):
                self.vars[dict_name] = {}
            self.vars[dict_name][key] = value
            logger.info(f"[ExtensionRunner] setDictValue {dict_name}[{key}] = {value!r}")
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"setDictValue": dict_name, "key": key, "value": value},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"setDictValue": dict_name},
            })
            return True

        if cmd_type == "getDictValue":
            dict_name = _clean_var_ref(extra.get("dictName", ""))
            key = self._resolve_vars(str(extra.get("key", "")), self.vars)
            target_var = _get_output_var(extra)
            d = self.vars.get(dict_name, {})
            result = d.get(key) if isinstance(d, dict) else None
            if target_var:
                self.vars[target_var] = result
            logger.info(f"[ExtensionRunner] getDictValue {dict_name}[{key}] -> {target_var} = {result!r}")
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"getDictValue": dict_name, "key": key, "value": result},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"getDictValue": dict_name, "value": result},
            })
            return True

        if cmd_type == "removeDictKey":
            dict_name = _clean_var_ref(extra.get("dictName", ""))
            key = self._resolve_vars(str(extra.get("key", "")), self.vars)
            d = self.vars.get(dict_name, {})
            removed = False
            if isinstance(d, dict) and key in d:
                del d[key]
                removed = True
            logger.info(f"[ExtensionRunner] removeDictKey {dict_name}[{key}] removed={removed}")
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"removeDictKey": dict_name, "key": key, "removed": removed},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"removeDictKey": dict_name},
            })
            return True

        if cmd_type == "stringConcat":
            target_var = _clean_var_ref(extra.get("targetVar", ""))
            part1 = self._resolve_vars(str(extra.get("part1", "")), self.vars)
            part2 = self._resolve_vars(str(extra.get("part2", "")), self.vars)
            part3 = self._resolve_vars(str(extra.get("part3", "")), self.vars)
            result = part1 + part2 + part3
            self.vars[target_var] = result
            logger.info(f"[ExtensionRunner] stringConcat {target_var} = {result!r}")
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"stringConcat": target_var, "value": result},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"stringConcat": target_var},
            })
            return True

        if cmd_type == "increment":
            var_name = _clean_var_ref(extra.get("varName", ""))
            step = extra.get("step", 1)
            try:
                step = float(step)
            except (ValueError, TypeError):
                step = 1
            current = self.vars.get(var_name, 0)
            try:
                current = float(current)
            except (ValueError, TypeError):
                current = 0
            self.vars[var_name] = current + step
            logger.info(f"[ExtensionRunner] increment {var_name} += {step}")
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"increment": var_name, "value": self.vars[var_name]},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"increment": var_name},
            })
            return True

        if cmd_type == "pushItem":
            data_expr = extra.get("dataExpr", "")
            resolved_expr = self._resolve_vars(data_expr, self.vars)
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"pushItem": resolved_expr},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"pushItem": resolved_expr},
            })
            return True

        if cmd_type == "saveToFile":
            data_var = extra.get("dataVar", "")
            file_path = extra.get("filePath", "")
            fmt = extra.get("format", "json")
            data = self.vars.get(data_var)
            logger.info(f"[ExtensionRunner] saveToFile {file_path} format={fmt}")
            try:
                dir_name = os.path.dirname(file_path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    if fmt == "json":
                        json.dump(data, f, ensure_ascii=False, default=str)
                    else:
                        f.write(str(data) if data is not None else "")
            except Exception as e:
                logger.error(f"[ExtensionRunner] saveToFile failed: {e}")
                raise
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"saveToFile": file_path, "format": fmt},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"saveToFile": file_path},
            })
            return True

        if cmd_type == "callAiApp":
            app_type = extra.get("appType", "")
            inputs = extra.get("inputs", "")
            result_var = _get_output_var(extra)
            logger.info(f"[ExtensionRunner] callAiApp app={app_type}")
            stub_result = {"appType": app_type, "inputs": inputs, "note": "stub"}
            if result_var:
                self.vars[result_var] = stub_result
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"callAiApp": app_type},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"callAiApp": app_type},
            })
            return True

        if cmd_type == "callWorkflow":
            workflow_id = extra.get("workflowId", "")
            inputs = extra.get("inputs", "")
            logger.info(f"[ExtensionRunner] callWorkflow id={workflow_id}")
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"callWorkflow": workflow_id},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"callWorkflow": workflow_id},
            })
            return True

        if cmd_type == "return":
            result_expr = extra.get("resultExpr", "")
            resolved_expr = self._resolve_vars(result_expr, self.vars)
            logger.info(f"[ExtensionRunner] return result={resolved_expr!r}")
            self.results.append({
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "status": "success",
                "result": {"return": resolved_expr},
            })
            self.completed += 1
            await self._emit({
                "type": "stepComplete",
                "stepId": step_id,
                "nodeId": instr.get("nodeId"),
                "result": {"return": resolved_expr},
            })
            return True

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
                self.results.append({
                    "stepId": step_id,
                    "nodeId": instr.get("nodeId"),
                    "status": "success",
                    "result": result,
                })
                self.completed += 1

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
                logger.info(f"[ExtensionRunner] save check step={step_id} cmd={cmd_type} save_to_var={save_to_var!r} result={result!r}")
                if save_to_var and result:
                    value = result.get("extracted") or result.get("navigatedTo") or result.get("value") or result
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
                        self.vars[window_var] = {"windowId": window_id if window_id is not None else wid, "tabId": tab_id}
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
        self.failed_steps.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "instruction": instr, "error": last_error})
        self.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"), "status": "error", "error": last_error})
        await self._emit({
            "type": "stepError",
            "stepId": step_id, "nodeId": instr.get("nodeId"),
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

        # Inject loop context into extra so content.js resolves locators relative to current element
        ctx = self.vars.get("__loop_ctx")
        if ctx:
            if extra.get("scope", "local") != "global":
                extra["contextLocator"] = ctx["locator"]
                extra["contextLocatorType"] = ctx["selectorFamily"]
                extra["contextIndex"] = ctx["index"]
            instr = {**instr, "extra": extra}

        # Register future BEFORE sending to avoid race with fast responses (e.g. navigate)
        future = ext_manager.register_step_future(step_id)
        try:
            ok = await ext_manager.send_to(
                self.client_id,
                "executeStep",
                {"stepId": step_id, "nodeId": instr.get("nodeId"), **instr},
            )
            if not ok:
                ext_manager.cancel_step_future(step_id)
                raise RuntimeError(f"Failed to send step {step_id} to extension")

            resp = await self._wait_future_with_stop(future, timeout=timeout)
            if resp["status"] == "error":
                raise RuntimeError(resp.get("error", "Unknown extension error"))
            return resp.get("result")
        except asyncio.TimeoutError:
            ext_manager.cancel_step_future(step_id)
            raise TimeoutError(f"Step {step_id} timed out after {timeout}s")
        except asyncio.CancelledError:
            ext_manager.cancel_step_future(step_id)
            raise


async def run_workflow_extension(wf: models.Workflow, nodes: list[models.WorkflowNode],
                                  client_id: str | None = None,
                                  run_id: str | None = None,
                                  initial_table_data: dict | None = None,
                                  trigger_type: str = "manual") -> dict:
    """
    Convenience entry point.
    If client_id is None, connection is deferred until the first extension
    instruction is encountered (on-demand connection).
    initial_table_data: {"columns": [...], "rows": [...]} passed from frontend.
    trigger_type: manual / scheduled
    """
    import time
    from src.config import runtime_config as config

    _run_id = run_id or f"run_{int(time.time() * 1000)}"

    # 创建日志目录（打包后通过 RPA_LOG_DIR 指向持久化用户目录）
    log_root = os.environ.get("RPA_LOG_DIR", config.REPO_DIR)
    log_dir = os.path.join(log_root, "data", "run_logs", str(wf.id), _run_id)
    os.makedirs(log_dir, exist_ok=True)

    # 提前注册进度队列，让 SSE 在 runner 启动前就能连上（wait_for_extension 可能耗时数秒）
    pre_queue = asyncio.Queue()
    run_progress.register(_run_id, pre_queue)

    runner = ExtensionRunner(client_id or "", run_id=_run_id, log_dir=log_dir, queue=pre_queue)

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
        run_progress.unregister(_run_id)

    result["tableRows"] = runner._table_data.get("rows", [])
    result["tableColumns"] = runner._table_data.get("columns", [])
    result["logDir"] = log_dir
    return result
