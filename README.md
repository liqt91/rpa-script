# RPA Script

浏览器自动化平台 — 用可视化工作流编排 RPA 任务，支持 Chrome 扩展执行 + 桌面应用 + AI 自然语言生成。

## 架构

```
rpa-script/
├── extension/           Chrome 扩展（content.js + background.js）
│   └── handlers/        浏览器端指令实现（一个 handler 一个文件）
├── src/
│   ├── runtime/          FastAPI 后端
│   │   ├── workflow/
│   │   │   ├── handlers/  指令系统（extension 35 / backend 18 / flow 20）
│   │   │   └── extension_emitter.py  节点树 → 指令序列编译器
│   │   ├── routers/      API 路由
│   │   └── tests/        测试（88/89 通过）
│   └── ui/workflow-editor/  React 前端（Vite 构建）
├── commands/             指令 JSON 定义（唯一定义源）
├── scripts/              工具脚本
│   ├── generate_commands.py  JSON → .py/.js 生成器
│   └── build_content_js.py   拼接 content.js
├── data/                 运行时数据（data.db）
└── dist/desktop/          桌面应用打包输出
```

## 技术栈

| 层 | 技术 |
|------|------|
| 后端 | Python 3.14 + FastAPI + SQLAlchemy + SQLite |
| 前端 | React (Vite) + Tailwind CSS |
| 浏览器 | Chrome Extension (Manifest V3) |
| 桌面 | pywebview |
| 测试 | pytest (88/89 通过) |

## 快速开始

```bash
# 安装
npm install
pip install -r requirements.txt

# 开发模式
npm run dev          # 前端开发服务器
python src/desktop.py --debug  # 桌面应用（后端 + 窗口）

# 运行测试
pytest src/runtime/tests/

# 构建
cd src/ui/workflow-editor && npm run build
python scripts/build_content_js.py
```

## 指令系统

指令从 JSON 定义文件生成，一套定义同时产出 Python handler 和 JS handler。

```
commands/clickElement.json    ← 唯一定义
        ↓ generate_commands.py
handlers/extension/clickElement.py   ← Python 注册（自动生成）
extension/handlers/clickElement.js   ← JS 实现（自动生成）
```

### Handler 三种类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `delegate` | 委托现有 JS 函数，无需手写代码 | `clickElement → doClick` |
| `custom` | 手写 JS 实现复杂浏览器逻辑 | `waitForElement` |
| `backend` | Python 后端执行（变量/网络/文件） | `setVar` |

详细说明见：`commands/` 下各 JSON 文件的 `description` 字段，或前端"指令定义"页面。

### 精选指令集（47/73）

为提高 AI 匹配精度和编辑器可用性，当前精选 47 个指令。被裁剪的 26 个指令文件后缀为 `.curated_removed`，后续按需恢复。

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
2. python scripts/generate_commands.py   # 生成 .py + .js
3. python scripts/build_content_js.py    # 拼接 content.js
4. 前端"指令定义"页面可见

# DB 迁移
python scripts/migrate_workflow_types.py

# 指令校验
python -c "from src.runtime.workflow.handler_validator import validate_handler_sync; print(validate_handler_sync())"
```
