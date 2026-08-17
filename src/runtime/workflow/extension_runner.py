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

from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes
import json
import logging
import os
import random
import re
from typing import Any, Callable

import time

from src.runtime.websocket_manager import ext_manager
from .extension_emitter import build_instructions
from src.providers import run_progress
from src.repo import runtime_models as models
from src.repo.models import SessionLocal
from src.repo.browser_utils import is_browser_running, launch_browser_with_extension

# Single import triggers all handler registration (backend + extension + emitter)
from . import handlers  # noqa: F401
from .handler_validator import validate_handler_sync  # noqa: F401

logger = logging.getLogger(__name__)

# 扩展侧无需元素定位器的指令（由 extra.url / windowVar 驱动）：
# P4 locator 校验仅对需要元素的指令生效，避免误杀导航/窗口类指令。
_LOCATOR_FREE_EXTENSION_CMDS = frozenset({
    "navigate", "newTab", "launchBrowser",
    "closeBrowser", "closeTab", "switchTab",
    "takeScreenshot", "pressKey", "getCurrentUrl",
})


def _get_cursor_pos():
    """Get current absolute cursor position. Windows only."""
    try:
        import ctypes
        from ctypes import wintypes
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    except Exception:
        return 0, 0


def _os_move_mouse(screen_x: int, screen_y: int, instant: bool = False) -> bool:
    """Move mouse to absolute screen coordinates with natural curve + jitter.
    Set instant=True to teleport (used during calibration phase).
    """
    if os.name != "nt":
        return False
    try:
        import ctypes
        import math
        import random

        if instant:
            ctypes.windll.user32.SetCursorPos(screen_x, screen_y)
            return True

        # Human-like: Bezier curve + ease-out + jitter
        sx, sy = _get_cursor_pos()
        dx = screen_x - sx
        dy = screen_y - sy
        dist = math.sqrt(dx * dx + dy * dy)

        # Control points for quadratic bezier (random curve)
        cpx = sx + dx * 0.3 + random.randint(-40, 40)
        cpy = sy + dy * 0.4 + random.randint(-30, 30)

        steps = max(10, int(dist / 8))
        for i in range(steps + 1):
            t = i / steps
            te = 1 - (1 - t) ** 3  # ease-out cubit

            x = int((1 - te) ** 2 * sx + 2 * (1 - te) * te * cpx + te ** 2 * screen_x)
            y = int((1 - te) ** 2 * sy + 2 * (1 - te) * te * cpy + te ** 2 * screen_y)

            # Jitter (decreases as we approach target)
            if 0 < i < steps:
                j = max(1, int((1 - t) * dist / 30))
                x += random.randint(-j, j)
                y += random.randint(-j, j)

            ctypes.windll.user32.SetCursorPos(x, y)
            time.sleep(random.uniform(0.001, 0.005))

        # Final precise position
        ctypes.windll.user32.SetCursorPos(screen_x, screen_y)
        return True
    except Exception:
        return False


def _os_click() -> bool:
    """Send a left mouse click at the current cursor position. Windows only."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # down
        time.sleep(0.05)
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # up
        return True
    except Exception:
        return False


# Virtual key code map for common keys
_VK_MAP = {
    "Enter": 0x0D, "Tab": 0x09, "Escape": 0x1B, "Backspace": 0x08,
    "Delete": 0x2E, " ": 0x20,  # Space
    "ArrowUp": 0x26, "ArrowDown": 0x28, "ArrowLeft": 0x25, "ArrowRight": 0x27,
    "PageUp": 0x21, "PageDown": 0x22, "Home": 0x24, "End": 0x23,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
}


def _os_press_key(key: str, modifiers: str = "") -> bool:
    """Send a keyboard key press at OS level. Windows only."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        vk = _VK_MAP.get(key)
        if vk is None and len(key) == 1:
            vk = ord(key.upper())

        if vk is None:
            return False

        mods = [m.strip() for m in modifiers.split(",") if m.strip()]
        for m in mods:
            if m == "Ctrl":
                ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
            elif m == "Alt":
                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
            elif m == "Shift":
                ctypes.windll.user32.keybd_event(0x10, 0, 0, 0)

        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # KEYUP

        for m in reversed(mods):
            if m == "Shift":
                ctypes.windll.user32.keybd_event(0x10, 0, 2, 0)
            elif m == "Alt":
                ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
            elif m == "Ctrl":
                ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
        return True
    except Exception:
        return False


# ── SendInput 结构（x64 下 sizeof(INPUT)=40：union 含 MOUSEINPUT=32 字节）──
# 只定义 KEYBDINPUT 会算出 32，SendInput 会以 ERROR_INVALID_PARAMETER(87) 拒绝。

_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _send_unicode_char(code: int) -> bool:
    """Send one Unicode character via SendInput (down + up)."""
    if os.name != "nt":
        return False
    user32 = ctypes.windll.user32
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    arr = (_INPUT * 2)()
    arr[0].type = 1
    arr[0].ki.wVk = 0
    arr[0].ki.wScan = code
    arr[0].ki.dwFlags = _KEYEVENTF_UNICODE
    arr[1].type = 1
    arr[1].ki.wVk = 0
    arr[1].ki.wScan = code
    arr[1].ki.dwFlags = _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP
    sent = user32.SendInput(2, arr, ctypes.sizeof(_INPUT))
    return sent == 2


_TYPO_PROB = 0.06          # 每次击键打错字的概率
_TYPO_POOL = "qwertyuiopasdfghjklzxcvbnm0123456789"


def _os_type_text(text: str, clear_first: bool = False) -> bool:
    """Type a string with real OS keystrokes (SendInput + KEYEVENTF_UNICODE).

    Human-like typing: character by character with variable intervals, and a
    small chance of typing a wrong character then deleting it and retyping the
    correct one. Works for any Unicode char (incl. CJK); the browser receives
    trusted key events. Optionally clears existing content first.
    """
    if os.name != "nt":
        return False
    if clear_first:
        _os_press_key("a", "Ctrl")   # Ctrl+A select all
        time.sleep(random.uniform(0.04, 0.12))
        _os_press_key("Backspace", "")  # Delete selected
        time.sleep(random.uniform(0.04, 0.12))

    ok = True
    for ch in text:
        # 可变击键间隔（拟人节奏）
        time.sleep(random.uniform(0.03, 0.18))
        # 概率打错字 → 删除 → 重打正确字符
        if random.random() < _TYPO_PROB:
            wrong = random.choice(_TYPO_POOL)
            if _send_unicode_char(ord(wrong)):
                time.sleep(random.uniform(0.08, 0.25))
                _os_press_key("Backspace", "")
                time.sleep(random.uniform(0.08, 0.25))
        if not _send_unicode_char(ord(ch)):
            ok = False
    time.sleep(0.05)
    return ok


DEFAULT_STEP_TIMEOUT = 30.0

_VAR_PLACEHOLDER_RE = re.compile(r"\$\{(\w+)\}|\{\{(\w+)\}\}")
_WF_VAR_RE = re.compile(r"\$\{wf:(\d+)\.(\w+)\}")


def _resolve_wf_var(m: re.Match) -> str:
    """Resolve ${wf:<workflow_id>.<var_name>} from cached last-run outputs."""
    wf_id = int(m.group(1))
    var_name = m.group(2)
    outputs = _last_run_outputs.get(wf_id, {})
    if var_name in outputs:
        val = outputs[var_name]
        return str(val) if not isinstance(val, str) else val
    logger.warning(f"[ExtensionRunner] cross-wf ref: wf={wf_id} var={var_name} not found in cached outputs")
    return m.group(0)

def _clean_var_ref(val):
    """Strip ${var} or {{var}} wrapper from a variable name field."""
    if not isinstance(val, str):
        return str(val) if val is not None else ""
    m = re.match(r'^\$\{(\w+)\}$|^\{\{(\w+)\}\}$', val.strip())
    if m:
        return m.group(1) or m.group(2)
    return val.strip()


class LoopBreak(Exception):
    """Raised by break instruction to exit the current loop."""
    pass


class LoopContinue(Exception):
    """Raised by continue instruction to skip to next loop iteration."""
    pass


# ─── Local command registry ───────────────────────────────────────
# Handlers registered here execute backend-only commands without an
# extension round-trip. New local commands just need a function + decorator.

LOCAL_HANDLERS: dict[str, Callable[["ExtensionRunner", str, dict], Any]] = {}


def _populate_local_handlers():
    """Auto-populate LOCAL_HANDLERS from handler registry.

    Any handler with an execute() method is eligible — this includes backend
    handlers and extension handlers that do Python-side pre-work (e.g. launchBrowser).
    auto_register() is idempotent; calling it here guarantees the registry is
    fully populated regardless of import order (extension_runner is imported
    during control-command registration via forEachElement).
    """
    from src.runtime.commands import auto_register
    auto_register()
    from .handlers.registry import get_all_handlers
    for htype, hdef in get_all_handlers().items():
        cls = hdef.get("handler_class")
        if cls and hasattr(cls, "execute"):
            LOCAL_HANDLERS[htype] = cls.execute

_populate_local_handlers()


def register_local(name: str):
    def decorator(fn: Callable[["ExtensionRunner", str, dict], Any]):
        LOCAL_HANDLERS[name] = fn
        return fn
    return decorator


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
        f"浏览器扩展未在 {timeout}s 内连接（目标浏览器: {browser_type}），"
        "请先打开对应浏览器并加载扩展，或在流程开头使用「打开浏览器」指令指定 browserType"
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
# Cache latest run outputs per workflow (runtime-only, for cross-wf ${wf:id.var} refs)
_last_run_outputs: dict[int, dict] = {}


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


def _eval_expression(condition: str, vars_dict: dict) -> bool:
    """求值条件表达式（如 "${a} > 10"）：先做 ${var} 插值，再作为布尔表达式求值。

    受限全局（禁用 builtins），求值失败按 False 处理。
    """
    if not isinstance(condition, str) or not condition.strip():
        return False
    try:
        resolved = ExtensionRunner._resolve_vars(condition, vars_dict)
        return bool(eval(resolved, {"__builtins__": {}}, {}))
    except Exception:
        return False


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
        # 事件计数器：用于 UI 展示的 totalSteps/completedSteps，保证 completed ≤ total
        # （self.completed 只统计顶层步，循环体子步会导致 completed 超过 total）。
        self._steps_started = 0
        self._steps_finished = 0
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

    def _ensure_table_data(self) -> dict:
        """Ensure _table_data is initialized and return it."""
        if not isinstance(self._table_data, dict):
            self._table_data = {"columns": [], "rows": []}
        if "columns" not in self._table_data:
            self._table_data["columns"] = []
        if "rows" not in self._table_data:
            self._table_data["rows"] = []
        return self._table_data

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
        Infers browser type from the current step (launchBrowser extra.browserType),
        defaulting to chrome. Sends runStarted on first connection.
        """
        if self.client_id:
            return
        browser_type = "chrome"
        explicit = False
        if self._current_step:
            extra = self._current_step.get("extra") or {}
            bt = extra.get("browserType")
            if bt:
                browser_type = bt
                explicit = True
        # 未显式指定浏览器时，优先回退到当前已在线的扩展浏览器类型，
        # 避免 Edge 用户在无 launchBrowser 步骤时被错误地按 chrome 等待。
        if not explicit and ext_manager.is_any_online:
            summary = ext_manager.browser_summary
            if summary:
                online = summary[0].get("browser")
                if online and online != "unknown":
                    browser_type = online
        self.client_id = await wait_for_extension_connection(browser_type, ext_manager, timeout=10.0)
        if not self._run_started_sent:
            self._run_started_sent = True
            await ext_manager.send_to(self.client_id, "runStarted", {"runId": self.run_id})

    async def _emit(self, event: dict) -> None:
        # 事件计数（M4）：stepStart 计 total，stepComplete/stepError 计 completed
        etype = event.get("type")
        if etype == "stepStart":
            self._steps_started += 1
        elif etype in ("stepComplete", "stepError"):
            self._steps_finished += 1
        # 复合指令（if/try/forRange/forEachElement 等）的 stepComplete 由 runner 直接 emit，
        # 不会像普通 handler 那样自己 append results —— 在此统一补录，保证 API 运行结果完整。
        # 普通 handler 已自行 append（含 stepId），靠 stepId 去重避免重复条目。
        if event.get("type") == "stepComplete" and event.get("stepId"):
            _sid = event["stepId"]
            if not any(r.get("stepId") == _sid for r in self.results):
                self.results.append({
                    "stepId": _sid,
                    "nodeId": event.get("nodeId"),
                    "status": "success",
                    "result": event.get("result", {}),
                })
        # Enrich stepComplete events with cmdLabel from instruction
        if event.get("type") == "stepComplete":
            event.setdefault("cmdLabel", self._current_step.get("cmdLabel", ""))
            event.setdefault("cmdType", self._current_step.get("cmdType", ""))
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
                summary = self._summarize(instr, self.vars)
                await self._emit({
                    "type": "stepStart",
                    "stepId": instr.get("stepId"),
                    "nodeId": instr.get("nodeId"),
                    "compound": instr.get("compound", False),
                    "cmdType": instr.get("cmdType", ""),
                    "cmdLabel": instr.get("cmdLabel", instr.get("cmdType", "")),
                    "_summary": summary,
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
                "completedSteps": self._steps_finished,
                "totalSteps": max(self._steps_started, self._steps_finished),
                "failedSteps": self.failed_steps,
                "results": self.results,
                "stopped": self._stopped,
            }
        finally:
            # Extract output params from vars if configured
            _emit_outputs = {}
            if hasattr(self, '_output_param_names') and self._output_param_names:
                _emit_outputs = {
                    name: self.vars.get(name)
                    for name in self._output_param_names
                    if name in self.vars
                }
            await self._emit({
                "type": "done",
                "success": not self._stopped,
                "completedSteps": self._steps_finished,
                "totalSteps": max(self._steps_started, self._steps_finished),
                "failedSteps": self.failed_steps,
                "stopped": self._stopped,
                "outputs": _emit_outputs,
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
            # Give SSE polling a moment to connect and drain the queue
            # (pure-local workflows finish in <100ms, SSE may not have connected yet)
            await asyncio.sleep(0.3)
            await run_progress.unregister(self.run_id)
            await remove_active_runner(self.run_id)

    @staticmethod
    def _resolve_vars(obj: Any, vars_dict: dict[str, Any]) -> Any:
        """Recursively replace ${var}, {{var}} and ${wf:id.var} placeholders in strings."""
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
            # First resolve cross-workflow refs ${wf:<id>.<var>}
            obj = _WF_VAR_RE.sub(_resolve_wf_var, obj)
            # Then resolve normal vars
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

    async def _check_element_visible(
        self,
        locator: str,
        selector_family: str,
        timeout: float = 3.0,
        extra: dict = None,
    ) -> bool:
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

    async def _get_element_text(
        self, locator: str, selector_family: str, timeout: float = 3.0, extra: dict = None
    ) -> str:
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

    async def _get_current_url(self) -> str:
        result = await self._call_extension_handler("getCurrentUrl", {}, timeout=5.0)
        return result.get("url", "")

    async def _find_elements(
        self,
        locator: str,
        selector_family: str,
        timeout: float = 10.0,
        extra: dict = None,
    ) -> list[dict]:
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

        # Data-driven condition evaluation
        from .handlers.registry import get_handler as _gh
        _h = _gh(cmd_type)
        if _h and _h.get("handler_class") and hasattr(_h["handler_class"], "evaluate"):
            return await _h["handler_class"].evaluate(self, instr)

        if cmd_type == "whileCondition":
            cond_type = extra.get("conditionType", "elementExists")
            met = False
            if cond_type == "expression":
                try:
                    met = bool(_eval_expression(extra.get("condition", "False"), self.vars))
                except Exception:
                    met = False
            elif cond_type == "elementExists":
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

    class _SafeFormatDict(dict):
        """A dict that returns empty string for missing keys, so
        summary_tpl like '{windowTitle} ({searchMode})' never raises KeyError."""
        def __missing__(self, key):
            return ""

    # Param names injected by the system (not user-facing) — skip in generic summary.
    _GENERIC_PARAM_NAMES = {"onError", "retryCount", "timeout", "description", "humanLike"}

    @staticmethod
    def _summarize(instr: dict, vars_dict: dict | None = None) -> str:
        """生成指令输入摘要，用于调试日志。

        优先从 handler registry 读取 summary_tpl 模板格式化；
        若无模板，遍历 params 拼 "标签: 值, ..." 作为通用兜底。
        传入 vars_dict 时先解析 {{var}}/${var} 占位符，避免摘要显示未解析模板。
        """
        cmd = instr.get("cmdType", instr.get("cmd", ""))
        extra = ExtensionRunner._resolve_vars(instr.get("extra") or {}, vars_dict or {})

        from .handlers.registry import get_handler as _get_hdef
        hdef = _get_hdef(cmd)

        # 1. summary_tpl 模板优先
        tpl = hdef.get("summaryTpl", "") if hdef else ""
        if tpl:
            return tpl.format_map(ExtensionRunner._SafeFormatDict(extra))

        # 2. 通用兜底：遍历 handler 参数，拼 "标签: 值"
        if hdef:
            parts = []
            for p in hdef.get("params", []):
                name = p.get("name", "")
                if not name or name in ExtensionRunner._GENERIC_PARAM_NAMES:
                    continue
                val = extra.get(name)
                if val is None or val == "":
                    continue
                # 跳过等于参数声明默认值的项（如 whileCondition 的 condition 默认 "False"），
                # 避免摘要里出现 "表达式: False" 之类的噪音。
                if "default" in p and str(val) == str(p["default"]):
                    continue
                label = p.get("label", name)
                parts.append(f"{label}: {str(val)[:40]}")
            if parts:
                return ", ".join(parts)

        return ""

    @staticmethod
    def _has_usable_locator(instr: dict) -> bool:
        """检查指令是否有可用的元素定位器（主 locator 或 altLocators 任一有效）。

        覆盖字符串 / 候选数组 / {locator|syntax|selector} 对象三种形态，
        与 content.js 侧的多 locator 解析保持一致。
        """
        def _ok(v) -> bool:
            if isinstance(v, str):
                return bool(v.strip())
            if isinstance(v, list):
                return any(_ok(i) for i in v)
            if isinstance(v, dict):
                return (_ok(v.get("locator")) or _ok(v.get("syntax"))
                        or _ok(v.get("selector")))
            return bool(v)

        if _ok(instr.get("locator")):
            return True
        for alt in instr.get("altLocators") or []:
            if _ok(alt):
                return True
        return False

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
                    "compound": sub.get("compound", False),
                    "cmdType": sub.get("cmdType", ""),
                    "cmdLabel": sub.get("cmdLabel", sub.get("cmdType", "")),
                    "_summary": self._summarize(sub, self.vars),
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
        # ── Data-driven loop/compound execution ──
        from .handlers.registry import get_handler as _gh2
        _h2 = _gh2(cmd_type)
        if _h2 and _h2.get("handler_class") and hasattr(_h2["handler_class"], "execute"):
            return await _h2["handler_class"].execute(self, cmd_type, instr, extra)

        # ── if* conditions ──
        if cmd_type.startswith("if"):
            eval_result = await self._evaluate_condition(instr)
            # 部分 if* handler 的 evaluate() 返回裸 bool（而非 {"met": ...} 字典），
            # 在边界处统一归一化，避免 TypeError: 'bool' object is not subscriptable。
            if not isinstance(eval_result, dict):
                eval_result = {"met": bool(eval_result)}
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
        step_type = instr.get("cmd", "")
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

        # Schema-driven command routing
        # - has execute() → call local handler first (pre-work or full work)
        # - runtime=="extension" → then dispatch to extension
        # - runtime=="backend" (with execute) → local only, done
        cmd_type = instr.get("cmdType") or step_type
        from .handlers.registry import get_handler as _gh2
        _hdef = _gh2(cmd_type)
        _has_local = _hdef and hasattr(_hdef.get("handler_class", object), "execute") if _hdef else False
        _is_extension = _hdef and _hdef.get("runtime") == "extension" if _hdef else False

        # 未注册/已废弃指令（emitter 照常下发）：显式报错，替代此前的静默跳过。
        if _hdef is None:
            msg = f"指令「{cmd_type}」无执行处理器（该指令未注册或已废弃）"
            if cmd_type == "openBrowser":
                msg += "：openBrowser 已删除，请改用 launchBrowser（打开浏览器）指令"
            logger.error(f"[ExtensionRunner] {step_id} {msg}")
            self.failed_steps.append({
                "stepId": step_id, "nodeId": instr.get("nodeId"),
                "instruction": instr, "error": msg,
            })
            self.results.append({
                "stepId": step_id, "nodeId": instr.get("nodeId"),
                "status": "error", "error": msg,
            })
            self._last_error = msg
            await self._emit({
                "type": "stepError", "stepId": step_id,
                "nodeId": instr.get("nodeId"), "error": msg,
            })
            if on_error == "continue":
                self.completed += 1
                return True
            return False

        if _has_local:
            try:
                local_ok = await self._handle_local(cmd_type, step_id, instr)
                if not local_ok:
                    return False
            except LoopBreak:
                raise
            except LoopContinue:
                raise
            except Exception as e:
                logger.error(f"[ExtensionRunner] local {cmd_type} failed: {e}")
                self.failed_steps.append({
                    "stepId": step_id, "nodeId": instr.get("nodeId"),
                    "instruction": instr, "error": str(e),
                })
                self.results.append({
                    "stepId": step_id, "nodeId": instr.get("nodeId"),
                    "status": "error", "error": str(e),
                })
                await self._emit({
                    "type": "stepError", "stepId": step_id,
                    "nodeId": instr.get("nodeId"), "error": str(e),
                })
                if on_error == "stop":
                    return False
                elif on_error == "continue":
                    self.completed += 1
                    return True
                return False
            if not _is_extension:
                return True  # backend: local handler did everything; done

        # Resolve variable placeholders in the instruction before sending
        resolved_instr = self._resolve_vars(instr, self.vars)

        # P4: 元素定位器为空时给出明确错误，避免被扩展侧
        # 「工作标签页已被手动关闭」等状态类错误掩盖真实原因。
        # 仅对需要元素定位的指令生效：navigate/newTab/launchBrowser 等
        # 无定位器指令（由 extra.url / windowVar 驱动）跳过该校验。
        if ("locator" in resolved_instr
                and cmd_type not in _LOCATOR_FREE_EXTENSION_CMDS
                and not self._has_usable_locator(resolved_instr)):
            msg = (f"指令「{cmd_type}」的元素定位器为空（locator 无有效值）。"
                   f"请检查该步骤引用的元素是否已正确配置或重新捕获"
                   f"（元素数据可能损坏、未选中元素，或变量未解析出定位器）。")
            logger.error(f"[ExtensionRunner] {step_id} {msg}")
            self.failed_steps.append({
                "stepId": step_id, "nodeId": instr.get("nodeId"),
                "instruction": instr, "error": msg,
            })
            self.results.append({
                "stepId": step_id, "nodeId": instr.get("nodeId"),
                "status": "error", "error": msg,
            })
            self._last_error = msg
            await self._emit({
                "type": "stepError", "stepId": step_id,
                "nodeId": instr.get("nodeId"), "error": msg,
            })
            if on_error == "stop":
                return False
            elif on_error == "continue":
                self.completed += 1
                return True
            return False

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

                # ── OS mouse move + click for element operations (hover/click/input) ──
                if isinstance(result, dict) and "viewX" in result:
                    human_like = extra.get("humanLike", True)
                    if human_like:
                        await self._handle_mouse_op(result, extra)

                # ── OS text input (inputElement 模拟键盘输入: real keystrokes) ──
                # Content decides via result fields (osType/osEnter); no re-gate here.
                # SendInput failure → surface a clear error instead of silently
                # reporting success with nothing typed.
                if isinstance(result, dict) and result.get("osType"):
                    ok = _os_type_text(result["osType"], clear_first=result.get("osClear", False))
                    if not ok:
                        raise RuntimeError(
                            "模拟键盘输入失败：真实按键未送达。请确认目标浏览器窗口在前台，"
                            "且输入框已通过前面的「点击元素」指令获取焦点。"
                        )
                    logger.info(f"[ExtensionRunner] OS typed {len(result['osType'])} chars")

                # ── OS Enter after input (inputElement pressEnter) ──
                if isinstance(result, dict) and result.get("osEnter"):
                    _os_press_key("Enter", "")
                    logger.info("[ExtensionRunner] OS Enter after input")

                # ── OS key press (pressKey command: trusted keystroke) ──
                if isinstance(result, dict) and result.get("osKey"):
                    _os_press_key(result["osKey"], result.get("osModifiers") or "")
                    logger.info(
                        "[ExtensionRunner] OS key: %s modifiers=%s",
                        result["osKey"], result.get("osModifiers") or "",
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
                        if result.get("contextNotFound"):
                            # 循环项内未找到子元素：存空串而非标记 dict
                            value = ""
                        elif "extracted" in result:
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

                # Update / create window variable from extension result.
                # Find handler params tagged "output" + "str-var" — if the result
                # contains windowId/tabId, write or update the corresponding var.
                from .handlers.registry import get_handler as _gh
                _hdef = _gh(cmd_type)
                if _hdef:
                    for _p in (_hdef.get("params") or []):
                        if _p.get("group") == "output" and _p.get("type") == "str-var":
                            _wname = (resolved_instr.get("extra") or {}).get(_p["name"])
                            if _wname and isinstance(result, dict) and (result.get("windowId") or result.get("tabId")):
                                window_val = self.vars.get(_wname)
                                window_id = result.get("windowId")
                                tab_id = result.get("tabId")
                                if isinstance(window_val, dict):
                                    # Update existing window object
                                    if tab_id is not None:
                                        window_val["tabId"] = tab_id
                                    if window_id is not None:
                                        window_val["windowId"] = window_id
                                    logger.info(f"[ExtensionRunner] updated {_wname} tabId={tab_id}")
                                elif window_val is not None:
                                    # Upgrade scalar to dict
                                    try:
                                        wid = int(window_val)
                                    except (ValueError, TypeError):
                                        wid = window_val
                                    self.vars[_wname] = {
                                        "windowId": window_id if window_id is not None else wid,
                                        "tabId": tab_id,
                                    }
                                    logger.info(f"[ExtensionRunner] upgraded {_wname} to dict with tabId={tab_id}")
                                else:
                                    # Create new window variable (e.g. launchBrowser)
                                    self.vars[_wname] = {
                                        "windowId": window_id,
                                        "tabId": tab_id,
                                    }
                                    logger.info(
                                        f"[ExtensionRunner] created {_wname} "
                                        f"windowId={window_id} tabId={tab_id}"
                                    )

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

    async def _handle_mouse_op(self, result: dict, extra: dict) -> None:
        """Move OS mouse to element + optionally click (result.osClick). Calibrates on first call."""
        sx = result.get("screenX"); sy = result.get("screenY")
        if result.get("_needsCalib"):
            if sx is not None: _os_move_mouse(sx, sy, instant=True)
            await asyncio.sleep(0.6)
            try:
                coords = await self._call_extension_handler(
                    "recomputeScreenCoords",
                    {"extra": {"viewX": result["viewX"], "viewY": result["viewY"],
                               "dpr": result.get("dpr", 1)}},
                    timeout=5.0,
                )
                sx = coords.get("screenX"); sy = coords.get("screenY")
            except Exception:
                pass
        if sx is not None and sy is not None:
            _os_move_mouse(sx, sy)
            result["screenX"] = sx; result["screenY"] = sy
            result.pop("_needsCalib", None)
        # Real OS click (clickElement, or input focus for OS typing)
        if result.get("osClick"):
            await asyncio.sleep(0.1)
            _os_click()

    async def _send_and_wait(self, step_id: str, instr: dict, timeout: float) -> Any:
        """Send executeStep to extension and wait for result."""
        await self._ensure_connected()
        conn = ext_manager.get_connection(self.client_id)
        if not conn:
            raise RuntimeError(f"Extension {self.client_id} is not connected")

        # Resolve explicit window variable -> windowId/tabId for extension routing.
        # Skip params tagged as "output" in the handler definition —
        # output variables are created by the handler, not referenced as input.
        extra = dict(instr.get("extra") or {})
        cmd_type = instr.get("cmdType", instr.get("cmd", ""))
        from .handlers.registry import get_handler
        h = get_handler(cmd_type)
        output_names = set()
        if h:
            for p in h.get("params", []):
                if p.get("group") == "output" and p.get("type") == "str-var":
                    output_names.add(p["name"])

        # Resolve non-output str-var params to windowId/tabId
        for key, val in list(extra.items()):
            if key in output_names:
                continue
            pdef = next((p for p in (h.get("params") or []) if p.get("name") == key), None)
            if pdef and pdef.get("type") == "str-var" and isinstance(val, str) and val in self.vars:
                window_val = self.vars.get(val)
                if window_val is None:
                    raise RuntimeError(f"窗口变量 '{val}' 未定义，请先执行打开浏览器指令")
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

    # 创建日志目录（RPA_LOG_DIR 可覆盖；默认落统一数据根 DATA_DIR）
    log_root = os.environ.get("RPA_LOG_DIR") or config.DATA_DIR
    log_dir = os.path.join(log_root, "run_logs", str(wf.id), _run_id)
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
    runner._output_param_names = [
        p.get("name") for p in wf_params
        if p.get("direction") == "out" and p.get("name")
    ]
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
        # Extract output parameters from runner.vars
        output_param_names = [
            p.get("name") for p in wf_params
            if p.get("direction") == "out" and p.get("name")
        ]
        outputs = {
            name: runner.vars.get(name)
            for name in output_param_names
            if name in runner.vars
        }
        if outputs:
            _last_run_outputs[wf.id] = outputs
            logger.info(f"[run_workflow_extension] cached outputs for wf={wf.id}: {list(outputs.keys())}")
        result["outputs"] = outputs

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
