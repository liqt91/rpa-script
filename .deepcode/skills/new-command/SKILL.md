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

**字段类型参考（JSON `params[].type` 和 Python `Param("name", ..., "type")` 使用相同的值）：**

| 类型 | 说明 | 示例 |
|---|---|---|
| `select` | 下拉选择（需配 `options`） | `"type": "select"` |
| `string` | 单行文本输入 | `"type": "string"` |
| `text` | 多行文本输入 | `"type": "text"` |
| `boolean` | 复选框 | `"type": "boolean"` |
| `number` | 数字输入 | `"type": "number"` |
| `int-number` | 整数输入 | `"type": "int-number"` |
| `str-var` | 变量引用（支持 `{{var}}` 语法） | `"type": "str-var"` |
| `element` | 元素选择器（已捕获的页面元素） | `"type": "element"` |

> **注意：** 不要使用 `str-dropdown`、`bool-check` 等名称，这些是旧文档中的错误写法。以实际代码中使用的为准。

**字段分组（`group`）：** `主属性`（默认）、`advanced`（高级）、`output`（输出）、`input`（输入）、`anchor`

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
| `launchBrowser` | extension | `extension_commands/launchBrowser.py` | 完整 execute 实现，有浏览器启动 + 扩展通信 |
| `setVar` | backend | `backend_commands/setVar.py` | 变量操作，含值类型转换 |
| `clickElement` | extension | `extension_commands/clickElement.py` | 注册桩，JS delegate 到 doClick |
| `inputElement` | extension | `extension_commands/inputElement.py` | 注册桩，JS delegate 到 doInput |
| `waitForElement` | extension | `extension_commands/waitForElement.py` | 注册桩，JS 自定义实现 |
| `findWindow` | backend | `desktop_commands/findWindow.py` | 桌面操作：查找窗口，含 Win32 API |
| `clickControl` | backend | `desktop_commands/clickControl.py` | 桌面操作：点击控件 |
| `inputControl` | backend | `desktop_commands/inputControl.py` | 桌面操作：控件输入，含 WM_SETTEXT + keybd_event 降级 |
| `clickMenu` | backend | `desktop_commands/clickMenu.py` | 桌面操作：点击菜单项，Win32 菜单 API |
| `openApp` | backend | `desktop_commands/openApp.py` | 桌面操作：打开软件，subprocess 启动 |
| `sendKey` | backend | `desktop_commands/sendKey.py` | 桌面操作：OS 级按键，keybd_event |
| `findChild` | backend | `desktop_commands/findChild.py` | 桌面操作：查找子控件 |
| `findSibling` | backend | `desktop_commands/findSibling.py` | 桌面操作：查找兄弟控件 |
| `findParent` | backend | `desktop_commands/findParent.py` | 桌面操作：查找父窗口 |

## 架构约束

- `@register_handler` 装饰器注册到 `_HANDLER_REGISTRY`
- `auto_register()` 在服务器 lifespan 中调用 → 触发 `__init__.py` 自发现导入
- JSON 是 source of truth → 变更后必须运行 `generate_commands.py`
- handler 参数名必须与 JSON `params[].name` 一致（handler `execute` 中通过 `extra.get("paramName")` 读取）
