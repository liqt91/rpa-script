# ADR 0011 — MCP 服务器：src/mcp_server 顶层适配器（stdio + HTTP）

- **Status:** accepted
- **Date:** 2026-08-10
- **Deciders:** project owner

## Context

需要让 AI 客户端（Claude Desktop / Claude Code / 自定义 agent）通过标准 MCP 协议
管理、运行这套 RPA 系统，并能实时操作浏览器扩展（agentic RPA）。现状是调用方要
手写 REST + JWT + SSE，门槛高。约束：

1. 结构测试只识别 `LAYER_ORDER` 内的目录，新模块必须显式登记层，否则测试无法
   推理其依赖（违反 golden principle：不写结构测试无法推理的代码）。
2. 扩展连接是单实例资源（workflow_lock 容量 1），浏览器实时指令与运行中流程
   会争用同一 WebSocket 连接。
3. MCP 无服务端推送，进度需要轮询/资源化。
4. 新增 `fastmcp` 依赖（纯 Python，无原生绑定）。
5. 包名不能叫 `mcp`——任何把 `src/` 放上 sys.path 的工具（pytest 收集、打包）
   都会让 `import mcp` 命中我们的包，遮蔽官方 MCP SDK（实测 pytest 收集即炸）。

## Decision

新增顶层 `mcp_server` 层与 MCP 服务器，作为现有 REST API 的薄适配器：

- 层序变为 `dtypes → config → repo → service → runtime → mcp_server`，同步更新
  `.harness/config.json` 与 `.harness/scripts/ast_structural_check.py`。
- `src/mcp_server/` 通过 httpx 调 REST 接口，只依赖 `config` 层读取设置；不 import
  runtime/service，保持可独立部署、独立测试。
- 双传输：stdio（默认，`python -m src.mcp_server.server`）+ streamable HTTP
  （`python -m src.mcp_server.http`，独立进程独立端口，不改 main.py，避免
  runtime→mcp_server 反向依赖）。
- 后端仅新增 2 个端点：`POST /api/extension/exec`（单指令执行，复用
  ext_manager 的 requestId/future 模式，与运行中工作流互斥 409）与
  `GET /api/extension/commands`（透出 handler 注册表，供 MCP 自动生成浏览器工具
  schema）。
- 认证：stdio 进程从 env 读 `RPA_API_TOKEN`（或 RPA_USERNAME/RPA_PASSWORD 登录
  换 token）；HTTP 传输由独立端口 + token 保护。
- 工具按风险分档（read/write/run/browser），env `RPA_MCP_TOOLS` 白名单可裁剪。

## Consequences

Positive: 后端几乎零侵入；MCP 服务器可独立部署/测试；浏览器工具 schema 跟随
指令注册表自动演进；层序机械可验证。

Negative: 双跳（MCP→REST→扩展）增加延迟；进度推送缺失，运行进度靠轮询；
fastmcp 版本演进需跟进；HTTP 传输的远程鉴权较粗（单 token）。

## Alternatives considered

- 内嵌进 FastAPI（/mcp 挂载）：进度实时、单进程，但 runtime→mcp_server 反向
  依赖，破坏层序；改动核心 app 生命周期。拒绝。
- 直接 import runtime 内部函数（run_workflow_extension/ext_manager）：
  耦合最深、无法独立部署，MCP 进程崩溃会拖垮后端。拒绝。
- 用官方 mcp 底层 SDK 手写 transport：工作量大且无收益，fastmcp 已覆盖
  stdio/streamable-http。拒绝。
