# ADR 0007: 工作流全局并发锁

## Status

Accepted

## Context

当前后端是单进程 asyncio FastAPI 服务，工作流通过 `POST /api/workflows/{wf_id}/run/extension` 同步执行（请求内 `await run_workflow_extension()`）。
`ExtensionManager` 目前只保留**每个浏览器类型一个** WebSocket 扩展连接。多个工作流同时触发会共享同一条浏览器通道，且 `_active_runners`、`_step_futures` 等全局状态都没有加锁，存在并发安全隐患。

## Decision

引入一个**进程内全局 `asyncio.Semaphore`** 作为工作流执行锁。

- 默认容量 `MAX_CONCURRENT_WORKFLOWS=1`。
- 超限时请求阻塞等待，超时后返回 HTTP 503 并带 `Retry-After`。
- 不持久化：单进程 uvicorn 重启后锁自然释放；后续若改为多 worker 再替换为 Redis/DB 锁。

## Consequences

- 同一时刻最多只有 1 个浏览器扩展工作流真正占用浏览器通道。
- 请求量超过容量时会排队或快速失败，避免无限堆积。
- 需要同步加固 `_active_runners`、`_step_futures`、`_queues` 等全局状态的访问。
- 纯本地（无浏览器）工作流也会被锁阻塞，后续可按需优化为“按浏览器类型取锁”或“本地流程跳过”。

## Theoretical concurrency

**理论最大值：1 个浏览器扩展工作流同时执行。**

瓶颈不是 Python 协程数，而是浏览器扩展 WebSocket 单连接：

1. `ExtensionManager` 每个浏览器类型只维护一条 WebSocket 连接。
2. `ExtensionRunner._send_and_wait()` 发送一个 `executeStep` 后必须等待返回，无法流水线。
3. 因此即使把容量调到 `N > 1`，多余的流程也只是在 WebSocket 处串行等待，不会提升真实吞吐量。

若同时连接了 Chrome 和 Edge 两个扩展，真实并发也只能到 2，但当前默认仍建议保持 1，等扩展多实例支持后再上调。
