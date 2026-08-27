# Architecture — rpa_script

This document is the source of truth for how code is organized. Any deviation
must be justified in an ADR under `.harness/docs/adr/`.

## Layer order (forward-only)

The structural test enforces the layer order declared in
`.harness/config.json` — see `npm run harness:check`.

```text
backend domain (root: src/):
  dtypes → config → repo → service → runtime → mcp_server

frontend domain (root: ui/):
  workflow-editor
```

Code in a higher layer may import from any lower layer. Code in a lower layer
**must not** import from a higher layer (or from the other domain).

## Layer responsibilities

| Layer        | Responsibility                                                              |
| ------------ | --------------------------------------------------------------------------- |
| `dtypes`     | Pure data shapes (Pydantic schemas). No I/O, no business logic, no framework imports. |
| `config`     | Static configuration (env loading, feature flags, constants).               |
| `repo`       | Persistence and external-system gateways. Returns plain values.             |
| `service`    | Business logic. Orchestrates `repo` calls. Pure where possible.             |
| `runtime`    | Framework adapters: HTTP routes, CLI commands, queue handlers, command registry. |
| `mcp_server` | MCP server: thin httpx adapter over the REST API (ADR-0011). 命名避开官方 `mcp` SDK 包名冲突。 |
| `ui/workflow-editor` | React 编辑器（Vite + Tailwind）：渲染、组件、展示逻辑。 |

## Cross-cutting concerns: `providers/` and `shared/`

Auth, telemetry, feature flags, observability — anything that would otherwise
cut across layers — enters through `providers/`. Each provider exposes a
single typed interface; consumers depend on the interface, not the
implementation.

Reusable pure helpers live in `src/shared/` (extraction engine, output parsing,
etc.). Prefer these over per-layer duplicates.

## Adding a new module

1. Decide which layers it touches.
2. Run `/inspect-module <existing-similar-module>` to mirror the pattern.
3. Create files under `src/{domain}/{layer}/`.
4. Write tests in the same layer.
5. Run the structural test. If it fails, do **not** disable it — fix the import.

## Recent decisions

(Most recent first. Created automatically by `/add-adr`.)

- `0012-remove-claude-code-adapter.md` — 移除 Claude Code 适配层，保留 kit 核心与技能（CLAUDE.md/agents/hooks/settings/memory 删除，backlog 迁 docs/，AGENTS.md 改写为内联自审）。
- `0011-mcp-server-adapter-layer.md` — MCP 服务器：新增顶层 mcp 层，REST 薄适配器（stdio+HTTP），新增 fastmcp 依赖。
- `0010-capture-unified-entry-and-storage.md` — 元素捕获统一入口 + 两维存储（element_type discriminants win32/uia/web），capture 进程就地写 elements.json。
- `0007-workflow-concurrency-lock.md` — 工作流全局并发锁（asyncio.Semaphore + 503/Retry-After）。
- `0006-capture-element-kind-redesign.md` — 捕获模块重构：显式 element_kind 区分 plain/anchor/child，子元素捕获必须基于 activeAnchor。
- `0005-gitea-update-check.md` — Gitea releases 作为桌面端 Plan A 更新源，仅检查/提示，不自动下载安装。
- `0004-css-xpath-selector-strategy.md` — CSS/XPath 选择器生成、校验、双向一致性与优先级策略。
- `0003-extension-handler-routing.md` — 指令使用 extension handler 的三条判定标准与映射规则。
- `0002-html-first-for-humans.md` — 人类可读交付物用 HTML，agent 文件用 Markdown。
- `0001-use-agent-harness-kit.md` — Adopt agent-harness-kit as the harness layer.
