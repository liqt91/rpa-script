# Architecture — rpa_script

This document is the source of truth for how code is organized. Any deviation
must be justified in an ADR under `.harness/docs/adr/`.

## Layer order (forward-only)

```
types → config → repo → service → runtime → ui
```

Code in a higher layer may import from any lower layer. Code in a lower layer
**must not** import from a higher layer. The structural test enforces this
mechanically — see `.harness/config.json` and the
`npm run harness:check` command.

## Layer responsibilities

| Layer       | Responsibility                                                              |
| ----------- | --------------------------------------------------------------------------- |
| `types`     | Pure data shapes. No I/O, no business logic, no framework imports.          |
| `config`    | Static configuration (env loading, feature flags, constants).               |
| `repo`      | Persistence and external-system gateways. Returns plain values.             |
| `service`   | Business logic. Orchestrates `repo` calls. Pure where possible.             |
| `runtime`   | Framework adapters: HTTP routes, CLI commands, queue handlers.              |
| `ui`        | Rendering, components, presentation logic.                                  |

## Cross-cutting concerns: `providers/`

Auth, telemetry, feature flags, observability — anything that would otherwise
cut across layers — enters through `providers/`. Each provider exposes a
single typed interface; consumers depend on the interface, not the
implementation.

## Adding a new module

1. Decide which layers it touches.
2. Run `/inspect-module <existing-similar-module>` to mirror the pattern.
3. Create files under `src/{domain}/{layer}/`.
4. Write tests in the same layer.
5. Run the structural test. If it fails, do **not** disable it — fix the import.

## Recent decisions

(Most recent first. Created automatically by `/add-adr`.)

- `0006-capture-element-kind-redesign.md` — 捕获模块重构：显式 element_kind 区分 plain/anchor/child，子元素捕获必须基于 activeAnchor。
- `0005-gitea-update-check.md` — Gitea releases 作为桌面端 Plan A 更新源，仅检查/提示，不自动下载安装。
- `0004-css-xpath-selector-strategy.md` — CSS/XPath 选择器生成、校验、双向一致性与优先级策略。
- `0003-extension-handler-routing.md` — 指令使用 extension handler 的三条判定标准与映射规则。
- `0001-use-agent-harness-kit.md` — Adopt agent-harness-kit as the harness layer.
