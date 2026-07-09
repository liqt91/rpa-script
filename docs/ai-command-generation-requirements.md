# 功能需求：AI 辅助的 JSON 指令定义与 Handler 代码生成

## 1. 背景与目标

项目正在从旧的硬编码指令体系迁移到新的 **JSON 指令定义体系**：

- 每条指令通过一个 JSON 文件定义（类型、显示名、分类、图标、参数、handler 类型等）。
- 向前：根据 JSON 定义自动生成 Python handler 代码、JS handler 代码、流程控制代码。
- 向后：根据 JSON 定义生成指令配置，供流程编辑器拖拽并配置参数。

本功能要求新增 **AI 配置模块**，让开发者可以在流程编辑器中配置 LLM（当前先支持 DeepSeek），并基于 JSON 指令定义一键生成后端 Python handler 代码。

## 2. 功能范围

### 2.1 AI 配置侧边栏入口

- 在工作流编辑器的左侧边栏新增「AI 配置」入口。
- 页面路径：`/#/ai-config`。
- 配置项：
  - 服务商：当前仅 DeepSeek。
  - 模型：可选 `deepseek-v4-flash`、`deepseek-v4-pro`。
  - API Key：文本框，保存时 trim 前后空格。
  - 启用开关。
  - 使用场景列表：当前至少支持「指令代码生成」，后续可扩展。
  - 每个场景可编辑 Prompt（带默认值），Prompt 支持 `{{definition}}`、`{{type}}`、`{{label}}`、`{{category}}`、`{{ClassName}}` 占位符。

### 2.2 指令定义编辑器标签页

在「指令定义」页面（`/#/commands/definitions`）为每条指令提供 4 个标签页：

1. **指令配置**：编辑 JSON 定义（基本信息、Handler 类型、参数列表）。
2. **JSON 预览**：实时显示当前 JSON。
3. **Python 代码**：显示/编辑 `handlers_new/{type}.py`，支持：
   - 点击「AI 生成」调用 LLM 生成代码。
   - 保存代码到 `src/runtime/workflow/handlers/handlers_new/{type}.py`。
   - 仅 backend 类型指令可用。
4. **JS 代码**：占位页（后续扩展）。

## 3. 后端要求

### 3.1 数据模型

新增 `ai_llm_configs` 表（单例）：

```sql
id INTEGER PRIMARY KEY
provider VARCHAR(16) DEFAULT 'deepseek'
model VARCHAR(64) DEFAULT 'deepseek-v4-flash'
api_key VARCHAR(256) DEFAULT ''
scenarios TEXT DEFAULT '[]'   -- JSON 数组
enabled INTEGER DEFAULT 1
created_at DATETIME
updated_at DATETIME
```

需通过 `src/repo/migrations.py` 的 migration 系统自动添加该表/列。

### 3.2 API

- `GET /api/ai/llm-config`：返回当前配置（API Key 不脱敏，仅内部使用）。
- `PUT /api/ai/llm-config`：更新配置和场景。
- `POST /api/ai/llm-config/scenarios/{scenario_id}/generate`：用指定场景的 Prompt 调用 LLM，payload 为 `{"definition": {...}}`。
  - 请求 DeepSeek OpenAI 兼容接口 `https://api.deepseek.com/v1/chat/completions`。
  - 自动清洗 LLM 返回的 Markdown 代码块。
  - 对 Python 代码做 `compile()` 语法校验。
  - 失败时返回 502/400，成功返回 `{"code": "..."}`。
- `GET /api/commands/definitions/{type}/source`：读取 `handlers_new/{type}.py` 内容。
- `POST /api/commands/definitions/{type}/save-handler`：保存 Python handler 代码，保存前用 `compile()` 校验语法。

### 3.3 日志

AI 生成接口需在后端控制台打印：

- 请求的 scenario、model。
- LLM 返回的原始内容。
- 提取后的代码。
- 语法错误时的完整代码。

## 4. 前端要求

### 4.1 AI 配置页

- 表单布局清晰，分「模型配置」和「使用场景 & Prompt」两块。
- 提供「测试生成」按钮，可基于示例 JSON 定义测试 Prompt。
- 保存成功后给出提示。

### 4.2 指令定义页

- 左侧指令列表不变。
- 右侧顶部显示指令名称、类型、保存按钮。
- 下方 4 个标签页切换。
- Python 标签页：
  - 非 backend 类型禁用编辑，提示用户切换执行环境。
  - backend 类型显示文件路径、代码编辑器、AI 生成按钮、保存按钮。
  - AI 生成按钮点击后，代码直接填充到编辑器，可二次修改后再保存。

## 5. Prompt 设计

默认「指令代码生成」Prompt 必须包含：

- 项目实际的 handler 模板：`from ..registry import register_handler, Param`。
- 正确的 `@register_handler` 用法。
- 正确的 `execute(runner, cmd_type, step_id, instr)` 签名。
- 从 `instr.get("extra")` 读取参数。
- `runner.vars`、`runner._emit`、`_send_and_wait` 等上下文说明。
- 禁止输出 Markdown 代码块和额外说明文字。
- 要求业务逻辑真实可执行，不写占位代码。

## 6. 非功能要求

- 新指令不需要兼容旧指令体系，但在流程编辑器中要能明确区分新旧指令（后续迭代）。
- 所有修改必须通过 `npm run build` 和 `npm run harness:check`。
- 后端新增单元测试覆盖 LLM config 的 CRUD。
- 数据库迁移必须走 `src/repo/migrations.py`，不能依赖手动改库。

## 7. 验收标准

- [ ] 侧边栏有「AI 配置」入口，点击进入可配置 DeepSeek Key、模型、Prompt。
- [ ] 在「指令定义」选择 backend 类型指令，切换到 Python 标签页，点击「AI 生成」能生成符合项目规范的 Python handler 代码。
- [ ] 修改代码后点击「保存」能写入 `handlers_new/{type}.py`。
- [ ] 切换标签页不丢失未保存的 JSON 定义编辑。
- [ ] `npm run build` 通过。
- [ ] `npm run harness:check` 通过。
- [ ] `pytest src/runtime/tests/test_ai.py` 通过。
