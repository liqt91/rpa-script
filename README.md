# RPA Script

浏览器自动化平台 — 用可视化工作流编排 RPA 任务，支持 Chrome 扩展执行 + 桌面应用 + AI 自然语言生成。

## 架构

```
rpa-script/
├── extension/           Chrome/Edge 扩展（content_capture.js + background.js）
│   ├── dom_handlers_new/     页面内指令实现（一个指令一个 JS）
│   ├── background_handlers/  后台指令实现（launchBrowser/navigate/switchTab 等）
│   └── dom_shared/           共享基建（content_base.js 等）
├── src/
│   ├── runtime/          FastAPI 后端
│   │   ├── workflow/        指令序列编译器 + 运行器（extension_runner.py）
│   │   ├── commands/        生成后的指令 handler（extension/backend/control/desktop 四类）
│   │   ├── routers/         API 路由
│   │   └── tests/           测试（117 通过）
│   └── ui/workflow-editor/  React 前端（Vite 构建 + Electron 桌面壳）
├── commands/             指令 JSON 定义（唯一定义源，53 个）
├── scripts/              工具脚本
│   ├── build_extension.py  一键构建扩展（generate_commands → background → content）
│   └── capture_gui/         元素捕获覆盖层（overlay.py）
├── data/                 运行时数据（data.db）
└── dist/desktop/          扩展构建输出（Edge/Chrome 加载）
```

## 技术栈

| 层 | 技术 |
|------|------|
| 后端 | Python 3.12 + FastAPI + SQLAlchemy + SQLite |
| 前端 | React (Vite) + Tailwind CSS（Electron 桌面壳） |
| 浏览器 | Chrome/Edge Extension (Manifest V3) |
| 桌面 | Electron |
| 测试 | pytest (117 通过) |

## 快速开始

```bash
# 安装
npm install
pip install -r requirements.txt

# 开发模式
npm run dev               # 前端开发服务器
python -m src.runtime.main  # 后端（端口 8000）

# 运行测试
pytest -q

# 构建
cd src/ui/workflow-editor && npm run build
python scripts/build_extension.py   # 构建扩展（含指令生成）
```

## 指令系统

指令从 JSON 定义文件生成，一套定义同时产出 Python handler 和 JS handler。

```
commands/clickElement.json        ← 唯一定义
        ↓ python scripts/build_extension.py
src/runtime/commands/extension_commands/clickElement.py  ← Python 注册（自动生成）
extension/dom_handlers_new/clickElement.js               ← 页面内 JS 实现
extension/background_handlers/clickElement.js            ← 后台 JS 实现（如需要）
```

### 指令分类

| 目录 | 运行时 | 说明 |
|------|--------|------|
| `extension_commands` | extension | 页面指令（Python 注册，动作在 JS 实现） |
| `dom_handlers_new` | extension | 页面内动作 JS handler（一个指令一个文件） |
| `background_handlers` | extension | 后台动作 JS handler（launchBrowser/navigate 等） |
| `backend_commands` | backend | Python 后端执行（日志等） |
| `control_commands` | control | 流程控制（if/for/while/try 等） |
| `desktop_commands` | backend | 桌面控件操作（Win32/UIA） |

详细说明见：`commands/` 下各 JSON 文件的 `description` 字段，或前端"指令定义"页面。

### 指令集（53 个）

当前 `commands/*.json` 共 53 个指令定义。

## 待办清单

### 紧急

- [ ] **C1: 指令向量化** — handler label+description → embedding，存 `data/command_embeddings.json`
- [ ] **C2: 自然语言 → 指令匹配** — 输入"打开百度，搜索RPA" → 返回指令序列及置信度
- [ ] **C3: 指令序列 → 工作流节点** — 匹配结果生成节点树（含 parent_id、order、extra）
- [ ] **C4: AI 生成前端入口** — WorkflowList 加"AI 生成"按钮，对话框预览后创建

### 重要

- [ ] **D1-D4: 定时调度器** — Schedules 表 + CRUD API + asyncio 引擎 + 前端管理页
- [ ] **撤销/重做** — 编辑器 Ctrl+Z / Ctrl+Y
- [ ] **元素内部滚动** — scrollContainer 参数支持

### 低优

- [ ] 节点配置项联动（select 切换显隐）
- [ ] 桌面应用 IPC 通信
- [ ] 循环变量作用域设计

## 常用命令

```bash
# 新增指令
1. 在 commands/ 创建 xxx.json
2. python scripts/build_extension.py   # 生成 .py + 拼接 background/content.js
3. 前端"指令定义"页面可见

# DB 迁移
python scripts/migrate_workflow_types.py

# 指令校验
python -c "from src.runtime.workflow.handler_validator import validate_handler_sync; print(validate_handler_sync(r'dist/desktop/extension/content.js'))"
```
