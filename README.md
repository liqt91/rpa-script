# RPA Script

浏览器自动化平台 — 以 **DSH 原生工具**为主线交付可视化 RPA 流程编排，支持 Chrome/Edge 扩展执行 + 桌面应用 + 元素捕获 + AI 自然语言生成。

> 主线路径：DSH 里的 RPA 工具（`rpa-dsh-plugin`），一个流程 = 一个目录（目录内 `workflow.json` / `elements.json` / `data.json` / `images/` / `run_logs/`）。

## 架构

```
rpa-script/
├── extension/            Chrome/Edge 扩展（MV3）
│   ├── dom_handlers_new/      页面内指令实现（一个指令一个 JS）
│   ├── background_handlers/   后台指令实现（launchBrowser/navigate/switchTab 等）
│   └── dom_shared/            共享基建（content_base.js 等）
├── src/
│   ├── runtime/          FastAPI 后端
│   │   ├── workflow/          指令编译器 + 运行器（extension_runner.py）+ emitter + handler registry
│   │   ├── commands/          指令 handler（extension/backend/desktop/control 四类）
│   │   ├── routers/           API 路由（含 projects 流程目录读写）
│   │   └── tests/             测试（runtime 196 通过）
│   ├── ui/workflow-editor/    React 编辑器（Vite + Tailwind，DB 模式 & 项目目录模式）
│   └── mcp_server/            MCP 适配器（可选旁路）
├── commands/             指令 JSON 定义（唯一定义源，82 个，含 $ref 共享参数）
├── rpa-dsh-plugin/       DSH 插件（工具面 + /rpa 斜杠命令 + rpa_bridge 免后端读写 + 捕获）
├── scripts/              构建/工具脚本（generate_commands / build_content_js / build_extension 等）
│   └── capture_gui/          元素捕获覆盖层（遮罩式统一捕获 web/桌面/UIA）
├── skills/               项目 skill（new-command / check-command / quality gate）
├── data/                 运行时数据（data.db）
└── dist/desktop/         扩展构建输出（Edge/Chrome 加载）
```

## 技术栈

| 层 | 技术 |
|------|------|
| 后端 | Python 3.12/3.13 + FastAPI + SQLAlchemy + SQLite |
| 前端 | React (Vite) + Tailwind CSS（DSH 内嵌 / workflow-editor） |
| 浏览器 | Chrome/Edge Extension (Manifest V3) |
| DSH 集成 | `rpa-dsh-plugin`（工具 + 斜杠命令 + 免后端读写） |
| 测试 | pytest（runtime 196 通过；含 mcp_server 需 fastmcp） |

> **认证**：本机**免登录**（`auth.py` 已简化，密码/登录功能移除，`get_current_user` 恒放行为 admin）。开发/本机使用无需登录。

## 快速开始

```bash
# 安装
npm install
pip install -r requirements.txt

# 开发模式（后端随机端口 8100-8199，RPA_PORT 可固定）
python -m src.runtime.main              # 后端
npm run dev                             # 前端开发服务器（可选，编辑器可走 DSH 内嵌）

# 运行测试
pytest -q                               # runtime 196 通过（mcp_server 需先装 fastmcp）

# 构建
python scripts/generate_commands.py     # 指令 JSON → handler 桩
python scripts/build_content_js.py      # 拼装 content.js
cd src/ui/workflow-editor && npm run build   # 前端产物（同步到插件 static）
```

## 指令系统

指令从 JSON 定义文件生成，一套定义同时产出 Python handler 和 JS handler。

```
commands/clickElement.json        ← 唯一定义
        ↓ python scripts/generate_commands.py
src/runtime/commands/extension_commands/clickElement.py  ← Python 注册（自动生成）
extension/dom_handlers_new/clickElement.js               ← 页面内 JS 实现
extension/background_handlers/clickElement.js            ← 后台 JS 实现（如需要）
```

### 指令分类（82 个）

| 目录 | 运行时 | 说明 |
|------|--------|------|
| `extension_commands` | extension | 页面指令（Python 注册，动作在 JS 实现） |
| `dom_handlers_new` | extension | 页面内动作 JS handler |
| `background_handlers` | extension | 后台动作 JS handler（launchBrowser/navigate 等） |
| `backend_commands` | backend | Python 后端执行（日志/wordToPdf/excelRead 等） |
| `desktop_commands` | backend | 桌面控件操作（Win32/UIA） |
| `control_commands` | control | 流程控制（if/for/while/try/break 等） |

### 新增指令（推荐：命令 + 质量门禁）

```bash
# 方式一：确定性命令（给定 definition 即全自动跑完，零 LLM）
#   对话里让模型调 rpa_new_command（DSH 工具）——写 JSON → generate_commands → build_content_js → 校验注册

# 方式二：手工
1. 在 commands/ 创建 <cmd>.json
2. python scripts/generate_commands.py      # 生成桩
3. python scripts/build_content_js.py       # extension 指令
4. 重启后端 → auto_register() 加载

# 生成后必跑质量门禁（源头防错）
python skills/scripts/check_command_quality.py <cmd>
python skills/scripts/check_command_quality.py --all   # 全量
```

> **指令质量门禁**：`skills/scripts/check_command_quality.py` 检查 def_required /
> def_fields / impl_exists / reg_params / extra_refs / sentinel / execute / emit /
> summary_tpl，AI 生成或新增指令后必跑，从源头避免规范问题。详见 `skills/new-command`。

## 元素捕获（统一入口）

遮罩式统一捕获（`rpa_capture`，web/桌面/UIA 合一），捕获结果写回流程目录
`elements.json`（`images/` 存截图）。详见 `docs/capture-unification-plan.md`。

## 常用命令

```bash
# DB 迁移
python scripts/migrate_workflow_types.py

# 校验指令
python -c "from src.runtime.workflow.handler_validator import validate_handler_sync; print(validate_handler_sync(r'dist/desktop/extension/content.js'))"
```
