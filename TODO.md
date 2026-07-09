# 待办清单

## 夜间任务池（每任务独立完成、验收明确、预计<30分钟）

### A. 旧流程迁移到新指令架构

- [x] **A1: DB 迁移脚本 — 旧 type 名批量更新**
  - 写 `scripts/migrate_workflow_types.py`，扫描 `workflow_nodes` 表的 `type` 字段
  - 将已知旧名替换为新名（如 `click`→`clickElement`、`input`→`inputText` 等）
  - 只改 `type`，不动 `extra` 和 `parent_id`
  - 验收：运行脚本后，DB 中所有旧 type 名消失，`grep -rn '"click"' data/` 无结果

- [x] **A2: 旧流程验证 — 跑通新架构的 end-to-end 测试**
  - 确保 LEGACY_MAP 覆盖所有旧 type → handler 的映射
  - 写一个测试：从 DB 加载一个旧流程，`build_instructions()` 不丢节点
  - 验收：`test_legacy_workflow.py` 通过

### B. content.js 补充缺失 handler（13 个 ❌ + 若干内部辅助）

- [x] **B1: waitForElement / waitForElementHide**
  - content.js 实现，用 MutationObserver 或 polling 检测元素出现/消失
  - 验收：测试确认元素出现后立即返回，超时抛异常

- [x] **B2: waitForLoad / waitForUrl / waitForText**
  - waitForLoad: `document.readyState === 'complete'` + 可选额外延迟
  - waitForUrl: polling `location.href` 变化
  - waitForText: 检测页面上包含指定文本是否出现
  - 验收：各写一个测试

- [x] **B3: scrollToTop / scrollOneScreen / scrollBy**
  - content.js 实现，基于 `window.scrollBy` / `document.querySelector(locator).scrollIntoView`
  - 验收：测试确认滚动后页面位置变化

- [x] **B4: takeScreenshot**
  - content.js 调用 `chrome.tabs.captureVisibleTab`，base64 回传 Python 存为 PNG
  - 需要 background.js 配合声明权限
  - 验收：工作流中添加截图指令，运行后 data/ 目录生成 PNG

- [x] **B5: keyCombo / getPageTitle / getElementCount / clickIfExists**
  - keyCombo: 模拟组合键 Ctrl+C 等
  - getPageTitle: `document.title`
  - getElementCount: `document.querySelectorAll(locator).length`
  - clickIfExists: 元素存在则点击，不存在则跳过（不报错）
  - 验收：每个各写一个测试

### C. AI 自然语言生成流程

- [ ] **C1: 指令向量化 — 将 71 个 handler 转为向量索引**
  - 提取每个 handler 的 `label` + `description` + `params` 为文本
  - 用 sentence-transformers（或 OpenAI embedding）生成向量
  - 存为 `data/command_embeddings.json`
  - 验收：`scripts/build_embeddings.py` 运行后生成 JSON，`len == 71`

- [ ] **C2: 自然语言 → 指令匹配**
  - 用户输入"打开百度，搜索RPA，等待3秒"，分词后匹配 handler
  - "打开" → openBrowser，"百度" → navigate url=baidu.com，"搜索" → clickElement + inputText
  - 返回匹配的指令列表及置信度
  - 验收：`test_nl_match.py` 测试 "打开百度搜索RPA" → [openBrowser, navigate, clickElement, inputText]

- [ ] **C3: 指令序列 → 工作流节点生成**
  - 根据匹配的指令列表，生成节点树（含 parent_id、order、extra 默认值）
  - 处理容器指令的配对（forList+endFor 等）
  - 验收：`test_nl_to_nodes.py` 输入自然语言 → 返回可直接插入 DB 的节点列表

- [ ] **C4: AI 生成前端入口**
  - 在 WorkflowList 添加"AI 生成"按钮
  - 弹出一个对话框：输入自然语言描述 → 显示匹配的指令序列预览 → 确认后创建工作流
  - 验收：输入"采集知乎热搜前10条"，生成含 openBrowser+navigate+forEachElement+getText+writeTableRow 的工作流

### D. 定时调度器

- [ ] **D1: 调度模型 — Schedules 表 + 迁移**
  - 新增 `schedules` 表：id, workflow_id, cron_expr, enabled, last_run_at, next_run_at
  - 支持 cron 表达式和简单间隔（每 N 分钟/小时/天）
  - 验收：迁移脚本执行后表存在，CRUD API 可用

- [ ] **D2: 调度 CRUD API**
  - GET/POST/PUT/DELETE `/api/workflows/{id}/schedules`
  - 验证 cron 表达式合法性
  - 验收：curl 测试 CRUD 四个操作

- [ ] **D3: 调度引擎 — asyncio 定时检查**
  - 在 lifespan 启动一个后台任务，每分钟检查 pending schedules
  - 到达时间 → 调用 `run_workflow_extension()` 执行
  - 记录执行日志到 schedules 表
  - 验收：创建一个每分钟执行的工作流，观察日志确认执行了 3 次以上

- [ ] **D4: 调度前端页面**
  - Schedules.jsx 替换占位页
  - 列表显示所有计划任务（工作流名、cron、下次执行时间、状态）
  - 支持新建/编辑/删除/启停
  - 验收：页面可创建、启用、禁用一个调度

### E. 基础补全

- [x] **E1: content.js 补充 checkElementVisible / checkElementExists handler**
  - 这两个在 content.js 已有注册但 Python 端未声明
  - 在 extension/ 目录创建对应的 .py handler 文件
  - 验收：`handler_validator.py` 校验 ❌ 数量减少

- [x] **E2: handler_validator 默认路径修复**
  - `handler_validator.py` 的默认 content_js_path 指向了错误的项目根
  - 改为基于 `__file__` 计算相对于 REPO_ROOT 的路径
  - 验收：不传参数调用 `validate_handler_sync()` 能正确找到 content.js

- [x] **E3: CommandsPage 增加"添加字段"按钮仅对自定义指令生效**
  - 当前内建指令也可以加字段，但 handler 不认新字段
  - 对 `isBuiltin` 指令隐藏 "+ 添加字段" 按钮
  - 验收：选内建指令 → 看不到 + 添加字段；选自定义指令 → 可以看到

## 中优先级

- [ ] **撤销 / 重做快捷键（Ctrl+Z / Ctrl+Y）**
- [ ] **支持元素内部滚动** (scrollContainer)
- [ ] **节点配置项联动** (select 切换显隐)
- [ ] **桌面应用 IPC 通信**

## 已记录 / 低优先级

- [ ] **循环变量作用域设计**

---

## 2025-07-10 进度：新指令架构 + AI 代码生成

### 指令定义编辑器 (CommandEditor)
- [x] 4 列并排布局：指令配置 | JSON 预览 | Python Handler 预览 | JS Handler 预览
- [x] 3 种指令类型：扩展端执行 (extension) / 本地端操作 (backend) / 本地端控制 (emitter)
- [x] 分类改为多对多（`command_categories` 表），下拉多选
- [x] 图标选择：120+ Font Awesome 图标网格预览，颜色实时反映
- [x] 图标颜色 + 背景颜色：Tailwind 22 色调色板，点选
- [x] bgColor、commandOrder、enabled、isContainer、closesWith 等配置项
- [x] 参数编辑：name/label/type/group(下拉)/required/default/placeholder/description/options
- [x] 保存时过滤 UI 内部字段（_catOpen, _iconOpen 等）和旧 handler 字段
- [x] 删除指令（确认弹窗 → 删除 JSON + handler 文件）

### 新指令文件架构
```
src/runtime/commands/
  backend_commands/     ← 本地端操作指令 (Python handler, @register_handler + execute)
  extension_commands/   ← 扩展端执行指令 (Python 注册桩, @register_handler)
  control_commands/     ← 本地端控制指令 (emitter, 待搬入)
  tools/                ← handler_template.py 等代码生成工具
```
- [x] 自注册：`__init__.py` 扫描 .py 文件 → `importlib.import_module`
- [x] 启动时 `main.py` → `auto_register()`
- [x] 清理旧 `handlers_new/` 目录
- [x] API 读写路径指向 `commands/backend_commands/`

### AI 代码生成
- [x] AI 配置页 (`/#/ai-config`)：DeepSeek 配置、场景编辑、测试生成
- [x] LLM API：`POST /api/ai/llm-config/scenarios/{id}/generate`
- [x] Prompt 模板改为 scaffold 注入：后端预生成完整骨架代码，AI 只填 TODO 区域
- [x] `_build_handler_scaffold()`：从 JSON 定义生成 import/注册/params/参数读取/结果上报
- [x] 数据库 `ai_llm_configs` 表 + migration
- [x] 分类 `command_categories` 表 + migration + 8 个默认分类
- [x] 旧 JSON 文件迁移（category → categories slug）

### 数据库
- 路径：`C:\Users\Administrator\AppData\Roaming\RPA Script\data.db`
- Prompt 以数据库 `ai_llm_configs.scenarios` 为准，代码中 `DEFAULT_COMMAND_CODE_GEN_PROMPT` 仅首次种子
