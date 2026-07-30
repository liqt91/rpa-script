"""Native Messaging 中继进程。

Chrome/Edge 通过 Native Messaging 拉起此进程，
此进程连接到 desktop_editor 的 WebSocket 做消息中继。

协议:
  stdin:  4字节长度前缀(uint32 LE) + JSON 消息
  stdout: 4字节长度前缀(uint32 LE) + JSON 消息
  WS:     127.0.0.1:{PORT} 的 WebSocket

由 Chrome 自动管理生命周期，不需要手动启动。
"""
import sys
import json
import struct
import asyncio
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format='[native_host] %(message)s',
)
logger = logging.getLogger(__name__)

PORT = int(os.getenv("RPA_PORT", "8000"))
WS_URL = f"ws://127.0.0.1:{PORT}/api/extension/ws"


def _read_message() -> bytes | None:
    """从 stdin 读取一条 Native Message。返回原始 JSON 字节。"""
    raw_len = sys.stdin.buffer.read(4)
    if not raw_len or len(raw_len) < 4:
        return None
    msg_len = struct.unpack('=I', raw_len)[0]
    if msg_len == 0:
        return None
    if msg_len > 1024 * 1024:  # 1MB 上限
        logger.error(f"消息过大: {msg_len}")
        return None
    return sys.stdin.buffer.read(msg_len)


def _write_message(data: str | bytes):
    """向 stdout 写一条 Native Message。"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    sys.stdout.buffer.write(struct.pack('=I', len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


async def _run():
    """主循环: stdin → WS → stdout 双向中继。"""
    import websockets

    logger.info(f"连接 desktop_editor WS: {WS_URL}")

    # 连接 WS，带重试
    ws = None
    for attempt in range(5):
        try:
            ws = await websockets.connect(WS_URL, max_size=2**20)
            logger.info("已连接到 desktop_editor")
            break
        except Exception as e:
            logger.warning(f"连接失败 ({attempt + 1}/5): {e}")
            if attempt < 4:
                await asyncio.sleep(1)
    if not ws:
        logger.error("无法连接到 desktop_editor，退出")
        return

    async def ws_to_stdout():
        """WS → stdout 方向。"""
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                _write_message(raw)
        except Exception:
            pass

    async def stdin_to_ws():
        """stdin → WS 方向。"""
        loop = asyncio.get_event_loop()
        while True:
            try:
                raw = await loop.run_in_executor(None, _read_message)
            except Exception:
                break
            if raw is None:
                break
            try:
                await ws.send(raw)
            except Exception:
                logger.error("WS 发送失败")
                break

    # 并发双工
    await asyncio.gather(
        stdin_to_ws(),
        ws_to_stdout(),
        return_exceptions=True,
    )

    try:
        await ws.close()
    except Exception:
        pass
    logger.info("退出")


def main():
    """入口: Native Messaging 模式。"""
    sys.stdout = open(sys.stdout.fileno(), 'w', buffering=1)
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
