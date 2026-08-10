# PLAN — mcp-server

新增顶层 `src/mcp_server/` MCP 服务器（ADR-0011，命名避开官方 mcp SDK 包名冲突），作为现有 REST API 的薄适配器：
httpx + JWT 调后端，工具分四组——工作流只读（P1）、流程创作（P2）、运行控制
（P3）、浏览器实时代理（P5）。后端仅新增 `POST /api/extension/exec`（单指令
执行，复用 ext_manager requestId/future 模式）与 `GET /api/extension/commands`
（透出 handler 注册表供工具 schema 自动生成）。传输双通道：stdio 默认 + 独立
进程 streamable HTTP。依赖新增 fastmcp。里程碑顺序：骨架(health) → 后端两端点
→ P1 → P2 → P3 → P5 → HTTP → 门禁（结构测试/ruff/pytest）→ PROGRESS。
