"""
浏览器扩展 WebSocket 连接管理器
负责维护扩展长连接、消息收发、命令下发
支持多浏览器（Chrome/Edge 等）区分
"""

import asyncio
import json
import logging
from typing import Callable, Dict, List, Optional
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ExtensionConnection:
    """单个扩展连接封装"""

    def __init__(self, websocket: WebSocket, client_id: str = ""):
        self.ws = websocket
        self.client_id = client_id or f"ext_{id(websocket)}"
        self.connected_at = __import__("time").time()
        self.tab_info: Optional[dict] = None   # 当前激活标签页信息
        self.browser: str = ""                  # 浏览器类型: chrome / edge / etc
        self.extension_id: str = ""             # 扩展 ID
        self.install_type: str = ""             # 安装方式: development / normal / etc

    async def send(self, message: dict):
        try:
            await self.ws.send_text(json.dumps(message))
        except Exception as e:
            logger.warning(f"向扩展 {self.client_id} 发送消息失败: {e}")

    async def recv(self) -> Optional[dict]:
        try:
            data = await self.ws.receive_text()
            return json.loads(data)
        except WebSocketDisconnect:
            return None
        except Exception as e:
            logger.warning(f"接收扩展 {self.client_id} 消息失败: {e}")
            return None


class ExtensionManager:
    """
    扩展连接管理器（单例）
    """

    def __init__(self):
        self._connections: Dict[str, ExtensionConnection] = {}
        self._lock = asyncio.Lock()
        self._callbacks: Dict[str, List[Callable]] = {}
        # Step result waiting: step_id -> asyncio.Future
        self._step_futures: Dict[str, asyncio.Future] = {}

    # ── 连接管理 ──

    async def connect(self, websocket: WebSocket) -> ExtensionConnection:
        await websocket.accept()
        conn = ExtensionConnection(websocket)
        async with self._lock:
            self._connections[conn.client_id] = conn
        logger.info(f"扩展已连接: {conn.client_id}, 当前在线: {len(self._connections)}")
        return conn

    async def disconnect(self, conn: ExtensionConnection):
        async with self._lock:
            self._connections.pop(conn.client_id, None)
        logger.info(f"扩展已断开: {conn.client_id}, 当前在线: {len(self._connections)}")

    def get_connection(self, client_id: str) -> Optional[ExtensionConnection]:
        return self._connections.get(client_id)

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    @property
    def is_any_online(self) -> bool:
        return len(self._connections) > 0

    def list_client_ids(self) -> list[str]:
        """Return a list of currently connected extension client IDs."""
        return list(self._connections.keys())

    # ── 按浏览器过滤 ──

    def connections_by_browser(self, browser_type: str) -> List[ExtensionConnection]:
        """返回指定浏览器类型的连接列表"""
        return [c for c in self._connections.values() if c.browser == browser_type]

    @property
    def browser_summary(self) -> List[dict]:
        """返回浏览器在线统计 [{browser, count, clients}]"""
        summary: Dict[str, dict] = {}
        for cid, conn in self._connections.items():
            b = conn.browser or "unknown"
            if b not in summary:
                summary[b] = {"browser": b, "count": 0, "clients": []}
            summary[b]["count"] += 1
            summary[b]["clients"].append(cid)
        return list(summary.values())

    # ── 消息发送 ──

    async def send_to(self, client_id: str, action: str, payload: dict = None) -> bool:
        conn = self._connections.get(client_id)
        if not conn:
            return False
        await conn.send({"action": action, "payload": payload or {}})
        return True

    async def broadcast(self, action: str, payload: dict = None, exclude: str = None, browser_type: str = None):
        """
        广播给在线扩展
        :param browser_type: 如果指定，只发给该浏览器类型（chrome / edge）
        """
        msg = {"action": action, "payload": payload or {}}
        dead = []
        targets = list(self._connections.values())
        if browser_type:
            targets = [c for c in targets if c.browser == browser_type]
        for conn in targets:
            if exclude and conn.client_id == exclude:
                continue
            try:
                await conn.send(msg)
            except Exception:
                dead.append(conn.client_id)
        # 清理死连接
        for cid in dead:
            self._connections.pop(cid, None)

    # ── 回调注册 ──

    def on(self, action: str, callback: Callable):
        """注册动作回调: on('captureResult', handler)"""
        self._callbacks.setdefault(action, []).append(callback)

    def off(self, action: str, callback: Callable = None):
        if callback is None:
            self._callbacks.pop(action, None)
        else:
            self._callbacks.get(action, []).remove(callback)

    async def dispatch(self, action: str, payload: dict, client_id: str):
        """分发扩展上报的消息"""
        # Fulfill pending step futures
        if action in ("stepResult", "stepError"):
            step_id = payload.get("stepId")
            async with self._lock:
                fut = self._step_futures.pop(step_id, None)
            if fut and not fut.done():
                if action == "stepResult":
                    fut.set_result({"status": "success", "result": payload.get("result"), "client_id": client_id})
                else:
                    fut.set_result({"status": "error", "error": payload.get("error"), "client_id": client_id})

        for cb in self._callbacks.get(action, []):
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(payload, client_id)
                else:
                    cb(payload, client_id)
            except Exception as e:
                logger.exception(f"处理扩展消息 {action} 时出错: {e}")

    # ── Step result waiting ──

    async def register_step_future(self, step_id: str) -> asyncio.Future:
        """Register a Future to be fulfilled when stepResult/stepError arrives."""
        fut = asyncio.get_event_loop().create_future()
        async with self._lock:
            self._step_futures[step_id] = fut
        return fut

    async def cancel_step_future(self, step_id: str):
        """Cancel a pending step future (e.g. on timeout)."""
        async with self._lock:
            fut = self._step_futures.pop(step_id, None)
        if fut and not fut.done():
            fut.cancel()

    async def await_step_result(self, step_id: str, timeout: float = 30.0) -> dict:
        """
        Wait for a stepResult or stepError for the given step_id.
        Returns {"status": "success"|"error", "result": ..., "error": ..., "client_id": ...}
        Raises TimeoutError if no response within timeout.
        """
        fut = await self.register_step_future(step_id)
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            await self.cancel_step_future(step_id)
            raise TimeoutError(f"Step {step_id} timed out after {timeout}s")

    # ── 连接保持 ──

    async def heartbeat_loop(self, conn: ExtensionConnection):
        """维持连接的心跳循环"""
        try:
            while True:
                msg = await conn.recv()
                if msg is None:
                    break
                action = msg.get("action", "")
                payload = msg.get("payload", {})

                if action == "ping":
                    await conn.send({"action": "pong", "payload": {}})
                elif action == "tabInfo":
                    conn.tab_info = payload
                elif action == "register":
                    # 扩展上报自身信息（浏览器类型、版本、扩展ID等）
                    browser = payload.get("browser", "")
                    ext_id = payload.get("extensionId", "")
                    install_type = payload.get("installType", "")
                    # 同一浏览器只允许一个连接：关闭该浏览器的旧连接
                    if browser:
                        dead = []
                        for cid, other in list(self._connections.items()):
                            if other.client_id != conn.client_id and other.browser == browser:
                                dead.append(cid)
                        for cid in dead:
                            old = self._connections.pop(cid, None)
                            if old:
                                try:
                                    await old.ws.close()
                                except Exception:
                                    pass
                                logger.info(f"扩展重复连接，断开旧连接: {cid}")
                    conn.browser = browser
                    conn.extension_id = ext_id
                    conn.install_type = install_type
                    logger.info(
                        f"扩展注册: {conn.client_id} browser={conn.browser} "
                        f"extId={ext_id} installType={install_type}"
                    )
                else:
                    await self.dispatch(action, payload, conn.client_id)
        except WebSocketDisconnect:
            pass
        finally:
            await self.disconnect(conn)


# 全局单例
ext_manager = ExtensionManager()
