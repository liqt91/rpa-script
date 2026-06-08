# ADR 0003 — Extension Handler Routing

- **Status:** accepted
- **Date:** 2026-05-27
- **Deciders:** project owner

## Context

指令体系同时涉及后端（Python）和浏览器扩展（content.js）两个执行环境。
每条指令必须决定：
1. 是否声明 `runtimes.extension`
2. 如果声明，`local` 是 true（后端执行）还是 false（发给浏览器）
3. `handler` 映射到 content.js 中的哪个函数

早期没有明确标准，导致 26 条指令缺失 runtime 声明，admin 后台也没有配置入口。

## Decision

使用三条标准判定指令是否走 extension handler：

1. **浏览器原生能力约束** — 操作页面 DOM、读取当前标签页状态、使用浏览器专属 API 的指令，必须通过 extension 执行。
2. **本地不可模拟** — 后端即使能"模拟"结果，但状态以浏览器为准的指令（如当前 URL 可能被用户中途跳转），必须走 extension。
3. **反 RPA 检测收益** — 需要 humanLike 交互（拟人点击、滚动、输入）的指令，走 extension 的 content.js handler，利用已实现的视觉确认、贝塞尔曲线移动、随机间隔等机制降低被检测概率。

映射规则分层：

| 类型 | runtime | handler | 示例 |
|---|---|---|---|
| 一对一映射 | enabled | content.js 同名函数 | click→click, navigate→navigate |
| 多对一映射 | enabled | 通用 handler + extra 字段区分 | getText/getAttr/getHtml→extract |
| 后端本地 | enabled, local=true | 任意（走 `_handle_local`） | setVar, httpRequest, callWorkflow |
| 不需要 runtime | disabled | — | 容器(if/for), 结构(endIf), 自定义(custom) |
| 待实现 | disabled（暂时） | — | doubleClick, takeScreenshot 等 |

## Consequences

Positive

- admin 后台新增 runtime 配置 UI，handler 下拉框自动从 content.js 解析，消除手写错误。
- 判定标准写进代码注释（commands.py:94）和 ADR，后续新增指令有明确 checklist。
- 反 RPA 能力集中到 content.js，避免后端和前端重复实现 humanLike 逻辑。

Negative

- 待实现指令（20 条）暂时没有 runtime，extension 模式下会被 emitter 静默跳过，需要后续补充 handler。
- 多对一映射（extract/scroll/wait）依赖 `_EXTRA_TRANSFORMS` 做字段转换，新增映射时需要同时改 emitter，容易遗漏。

## Alternatives considered

- **所有指令统一走后端 DrissionPage。** Rejected：后端无法感知用户中途的页面跳转、弹窗、AJAX 加载；且缺少 humanLike 交互能力，反 RPA 检测率低。
- **所有指令都写独立的 content.js handler。** Rejected：click/doubleClick/rightClick 等行为高度相似，独立 handler 会导致大量重复代码；当前采用"通用 handler + extra 区分"的多对一模式更紧凑。
