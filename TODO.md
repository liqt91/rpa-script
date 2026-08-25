# 待办清单 / 项目路线图

> 更新：2026-08-25（项目审视后）｜当前版本 v0.2.3｜主线：DSH 原生工具交付可视化 RPA（一个流程 = 一个目录）

---

## 📋 项目审视 · 现状与未来方向

### 现状（一句话）
浏览器自动化平台：Chrome/Edge 扩展（MV3）+ FastAPI 后端 + React 编排器 + MCP + `rpa-dsh-plugin`。
命令 **82**、pytest **186**、ruff/结构测试通过；`feature_list` 大部分 `passes`，仅 `capture-unified-entry-storage` 差一个端到端测试。

### 已完成 / 成熟
- 工作流参数、并发锁、元素捕获重构、web 指令架构重构、MCP 服务器、DSH P0 异步导入/运行 —— 均已 `passes`。
- 指令生成工具链已闭环：`rpa_new_command` / `command_builder` / `--verify`（mock runner）/ Node 桩 / 免定位器定义驱动 / skill new-command v1.12。
- TODO A（旧流程迁移）、B（content 缺失 handler）、E（基础补全）—— 已完成。

### 风险 / 债务
- **架构文档与代码漂移**：`architecture.md` 层序（`types→…→mcp_server→ui`+`providers/`）与 `src/runtime/commands/*_commands` 指令系统对不上；`state.json` 停在 mvp/无风险；README 命令数 82≠72、electron 已删未更新。
- **插件运行时脆**：改 DSH 插件**服务端**需极度保守（`syncProjectSkills` 曾致 dsh 起不来，已回退）。
- **验证缺口（AI 建命令/流程不可靠的主因）**：后台 handler 无 Node 桩验证；真机 e2e 需手动重载扩展；改核心模块需重启后端。
- **免登录**：本机/开发 OK；一旦共享/发布是多用户安全风险。
- `capture-unified-entry-storage`：仅差「GUI 捕获→保存→元素库」端到端测试。

### 未来方向（按优先级）
- **P0｜AI 一句话 → 可运行工作流（主线）**：强化 `pre-generate-workflow` / `generate-workflow` + 元素库就绪 + 捕获。用户描述意图 → agent 自动拆解并建成**可运行**流程。TODO 原 C 块的向量匹配（C1-C4）已被这套 skill 驱动路线取代。
- **P0｜补验证缺口**：后台 handler 加 `chrome.*` mock 的 Node 桩验证；真机 e2e 免手动重载扩展（dev 扩展热重载/自动化）；改核心模块自动重启后端。
- **P1｜流程根集中 RPA_HOME + 统一管理页**：改路径模型，**不做旧兼容、不做复杂去重**；RPA_HOME 默认**用户可见目录**（非隐藏 `.dsh`，用户能在工作区/资源管理器直接打开）。
- **P1｜定时调度（D 块）**：做成无人值守周期自动化（枚举 `RPA_HOME` 下的流程）。
- **P1｜可靠性/发行准备**：桌面安装器（扩展拷到稳定目录）+ 内嵌扩展 + 一条命令跑；免登录的共享/发布风险评估。
- **P2｜清理与收尾**：更新 `architecture.md`/`state.json`/README；补 `capture-unified-entry-storage` e2e；命令目录 UI catalog 提交纪律。

---

## 待办（按优先级）

### P0
- [ ] **P0-AI｜一句话生成可运行工作流（主线强化）**
  - [ ] pre-generate-workflow / generate-workflow 与元素库就绪、捕获打通
  - [ ] agent 从自然语言 → 完整可运行流程（含元素捕获、参数、结果写回）
  - [ ] 验收：输入"采集知乎热搜前10条"→ 一键生成 + 运行成功
- [ ] **P0-验证｜后台 handler 的 Node 桩验证** —— `verify_web_handler.mjs` 加 `chrome.tabs.query`/`chrome.windows` 的 mock，让 getAllTabs/switchTab 等可走官方桩
- [ ] **P0-验证｜真机 e2e 免手动重载扩展** —— dev 扩展热重载 / 自动化刷新，让"重载扩展"不再是必备人工步
- [ ] **P0-验证｜改核心模块自动重启后端** —— extension_runner 等被改后自动重启，减少人工判断

### P1
- [ ] **P1-流程根｜集中流程根 RPA_HOME + 统一管理页**（改路径模型）
  - [ ] `RPA_HOME` 可配置；**默认用户可见目录**（如 `~/RPA脚本`，**非隐藏 `.dsh`**，用户能在资源管理器/工作区直接打开）
  - [ ] 一个流程 = `RPA_HOME/<流程目录>/`（内部 rpa.json/workflow.json/elements.json/data.json/images/run_logs 结构不变）
  - [ ] 所有流程只在 `RPA_HOME` 下；**旧散落目录不迁移、不兼容**，直接切新模型
  - [ ] 目录名 = 流程名，重名由 OS/自然命名处理（**不做复杂去重**）
  - [ ] 统一管理页枚举 `RPA_HOME/*/rpa.json`（名称/节点数/最近运行/状态 + 打开编辑器/运行/复制/重命名/归档/删除/加调度）
  - [ ] 会话/编辑器/运行路径改为"从 `RPA_HOME` 选流程"，**打破旧的"会话 cwd=当前流程"绑定**
  - [ ] 后续：定时调度（枚举 RPA_HOME）、AI 一句话生成（落到 `RPA_HOME/<新流程名>`）
- [ ] **P1-调度｜D1: 调度模型 — Schedules 表 + 迁移**（cron + 简单间隔，last/next run）
- [ ] **P1-调度｜D2: 调度 CRUD API**（`/api/workflows/{id}/schedules`，校验 cron）
- [ ] **P1-调度｜D3: 调度引擎 — asyncio 定时检查**（lifespan 后台任务，到期调 `run_workflow_extension()`）
- [ ] **P1-调度｜D4: 调度前端页面**（列表 + 新建/编辑/删除/启停）
- [ ] **P1-发行｜桌面安装器 + 内嵌扩展 + 一条命令跑**（插件 README P2：扩展拷稳定目录 + 写 External Extensions + 提示重启）

### P2
- [ ] **P2-清理｜更新 architecture.md / state.json / README**（层序/状态/命令数 82、移除 electron 残留）
- [ ] **P2-收尾｜capture-unified-entry-storage 端到端测试**
- [ ] 撤销 / 重做快捷键（Ctrl+Z / Ctrl+Y）
- [ ] 支持元素内部滚动（scrollContainer）
- [ ] 节点配置项联动（select 切换显隐）
- [ ] 桌面应用 IPC 通信
- [ ] 循环变量作用域设计

### 已完成（留档）
- [x] A1-A2：旧流程迁移到新指令架构（迁移脚本 + LEGACY_MAP 验证）
- [x] B1-B5：content.js 补充 waitFor/*/scroll/takeScreenshot/keyCombo/getPageTitle/getElementCount/clickIfExists
- [x] E1-E3：checkElementVisible/Exists 注册、handler_validator 路径修复、内建指令隐藏"添加字段"
- [x] 指令生成工具链闭环：rpa_new_command 极简用 + command_builder `--verify` + Node 桩 + 免定位器定义驱动 + skill v1.12
- [x] error/# MCP 服务器、web 指令架构重构、元素捕获重构、工作流并发锁、DSH 异步导入/运行

---

## 历史进度（2025-07-10，留档）

### 新指令架构 + AI 代码生成
- [x] 指令定义编辑器（4 列布局、多分类、图标/配色、参数编辑、删除）
- [x] 自注册 handler 目录（backend/extension/control_commands）
- [x] AI 代码生成：LLM API + scaffold 注入 + 分类表 + 旧 JSON 迁移
- [x] 数据库：data.db、ai_llm_configs、command_categories

> 注：AI 代码生成（AI 填 TODO 区）已被 DSH skill 驱动路线（agent 直接生成/复用）进一步取代，保留作历史。
