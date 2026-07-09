---
name: new-command
description: 创建新的 RPA 指令（command），包括 JSON 定义、handler 代码生成、AI prompt 选择和注册验证。三类指令：extension（扩展端）、backend（本地执行）、control（控制流）。
---

# 新增指令开发流程

## 三类指令

| 类型 | 目录 | Python | JS |
|---|---|---|---|
| **extension** | `src/runtime/commands/extension_commands/` | 注册桩（`@register_handler` + `Param`） | `extension/handlers/<type>.js` handler 函数 |
| **backend** | `src/runtime/commands/backend_commands/` | 含 `execute()` 实现 | 无 |
| **control** | `src/runtime/commands/control_commands/` | 含 `execute()` 控制流逻辑 | 无 |

## 开发流程

### 1. 创建 JSON 定义

在 `commands/<type>.json` 创建指令定义：

```json
{
  "type": "myCommand",
  "label": "我的指令",
  "runtime": "backend",
  "category": "分类名",
  "icon": "fa-cog",
  "iconColor": "text-blue-500",
  "bgColor": "bg-blue-50",
  "categoryOrder": 50,
  "commandOrder": 10,
  "description": "指令描述",
  "enabled": true,
  "isNew": true,
  "params": [
    {"name": "paramName", "label": "参数显示名", "type": "str-input", "required": true}
  ],
  "handler": {
    "kind": "backend",
    "source": "src/runtime/commands/backend_commands/myCommand.py"
  }
}
```

**handler.kind 取值：**
- `extension` — JS handler。有 `function` → delegate 一行转发；有 `source` → 复制 JS 文件
- `backend` — Python handler（手写或 AI 生成），跳过自动生成
- `control` — 控制流 handler（手写或 AI 生成），跳过自动生成

**字段类型参考：**
`str-input` `str-textarea` `str-var` `str-dropdown` `str-element` `int-number` `bool-check` `list-input` `dict-input` `any-expr` `any-input`

**字段分组：** `主属性` `advanced` `output` `input` `anchor`

### 2. 生成 handler 桩代码

```
POST /api/commands/definitions/build
```

实际执行：
- `python scripts/generate_commands.py` — 从 JSON 生成 `.py` 桩 + `.js` 桩
- `python scripts/build_content_js.py` — 合并所有 JS handler → `extension/content.js`

- extension 命令：生成 Python 注册桩 + JS handler 草图
- backend/control：**跳过**（标记为 hand-written）

### 3. AI 生成 handler 实现

运行 `python scripts/update_llm_prompt.py <data.db路径>` 更新 AI prompt 到数据库。

三个 prompt 场景（在 `scripts/update_llm_prompt.py` 中定义）：

| Scenario ID | 用途 | Prompt 变量 |
|---|---|---|
| `command_backend` | Python handler + execute() | `{{type}}` `{{label}}` `{{category}}` `{{ClassName}}` `{{definition}}` |
| `command_extension_js` | JS handler 函数 | 同上 |
| `command_control` | 控制流 Python handler | 同上 |

**调用方式：** 从 DB 的 `ai_llm_configs.scenarios` 读取对应 prompt，替换模板变量后发送给 AI。

### 4. 保存 handler 代码

```
POST /api/commands/definitions/{type}/save-handler
{"code": "<AI生成的代码>"}
```

Python 代码会在保存前做 `compile()` 语法检查。

### 5. 验证

重启服务器 → `auto_register()` 自动发现新 handler。
- extension handler: 检查 `extension/handlers/<type>.js` 是否存在
- Python handler: 检查 `src/runtime/commands/{backend,extension,control}_commands/<type>.py`

```
POST /api/commands/sync-check  → 检查 Python 与 JS handler 一致性
POST /api/commands/validate    → 运行指令注册表一致性校验
```

## 现有 handler 参考

| 指令 | 类型 | Handler 文件 | 特点 |
|---|---|---|---|
| `launchBrowser` | backend | `backend_commands/launchBrowser.py` | 完整 execute 实现，有浏览器启动 + 扩展通信 |
| `setVar` | backend | `backend_commands/setVar.py` | 变量操作，含值类型转换 |
| `clickElement` | extension | `extension_commands/clickElement.py` | 注册桩，JS delegate 到 doClick |
| `inputElement` | extension | `extension_commands/inputElement.py` | 注册桩，JS delegate 到 doInput |
| `waitForElement` | extension | `extension_commands/waitForElement.py` | 注册桩，JS 自定义实现 |

## 架构约束

- `@register_handler` 装饰器注册到 `_HANDLER_REGISTRY`
- `auto_register()` 在服务器 lifespan 中调用 → 触发 `__init__.py` 自发现导入
- JSON 是 source of truth → 变更后必须运行 `generate_commands.py`
- handler 参数名必须与 JSON `params[].name` 一致（handler `execute` 中通过 `extra.get("paramName")` 读取）
