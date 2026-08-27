# PLAN — P0 主线：AI 一句话 → 可运行工作流

当前主线（替代已归档的 mcp-server 计划）：强化 `pre-generate-workflow` /
`generate-workflow` + 元素库就绪 + 捕获，让用户描述意图 → agent 自动拆解并建成**可运行**流程。

## 现状

- 小红书搜索已实战跑通（199/199 步，saveJsonFile 落盘 30 条），见 TODO.md P0-AI。
- 待验收：同模式验证「采集知乎热搜前 10 条」。

## 里程碑

1. **元素捕获与存储已就绪** — `capture-unified-entry-storage`（ADR-0010，passes）。
2. **skill 驱动生成链路已闭环** — `pre-generate-workflow` / `generate-workflow` / `new-command`。
3. **验证缺口补齐（P0）** — background handler Node 桩（✅）、真机 e2e 免手动重载（✅）、
   改核心模块自动重启后端（未做，见 feature `core-module-auto-restart`）。
4. **验收** — 「采集知乎热搜前 10 条」一键生成 + 运行成功（feature `ai-one-shot-workflow`）。

## 后续（P1）

- 定时调度（`scheduler-d1-d4`）、发行（`installer-release`）。

## 相关

- 完整待办与优先级：`TODO.md`（2026-08-25 审视版）。
- harness 收拢设计：`tmp/harness-design-body.md`。
