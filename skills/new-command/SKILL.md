---
name: new-command
description: 创建新的 RPA 指令（command），包括 JSON 定义、handler 代码生成和注册验证。四类指令：extension（扩展端）、backend（本地执行）、desktop（桌面操作）、control（控制流）。
---

# 新增指令开发流程

## 四类指令

| 类型 | 目录 | Python | JS |
|---|---|---|---|
| **extension** | `src/runtime/commands/extension_commands/` | 注册桩（`@register_handler` + `Param`） | `extension/dom_handlers_new/<type>.js` handler 函数 |
| **backend** | `src/runtime/commands/backend_commands/` | 含 `execute()` 实现 | 无 |
| **desktop** | `src/runtime/commands/desktop_commands/` | 含 `execute()`，调 Win32 / UIA API | 无 |
| **control** | `src/runtime/commands/control_commands/` | 含 `execute()` 控制流逻辑 | 无 |

> desktop 在 JSON 中 `runtime` 设为 `"backend"`，`handler.source` 指向 `desktop_commands/` 目录。它是 backend 的子类，因涉及桌面 API 而独立目录。

## 开发流程

### 硬性约束

```
commands/<type>.json（唯一事实来源）
       │
       ▼
python scripts/generate_commands.py   ← 必须运行
       │
       ▼
在生成的桩文件基础上添加实现逻辑
       │
       ▼
python scripts/build_content_js.py    ← extension 指令必须运行
       │
       ▼
重启服务器 → auto_register() 加载 → 验证
```

> **禁止直接创建 handler 文件而不先建 JSON。禁止修改 JSON 后不运行 generate_commands.py。**

### 1. 创建 JSON 定义

在 `commands/<type>.json` 创建指令定义：

```json
{
  "cmd": "myCommand",
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
    {"name": "paramName", "label": "参数显示名", "type": "string", "required": true}
  ],
  "handler": {
    "kind": "backend",
    "source": "src/runtime/commands/backend_commands/myCommand.py"
  }
}
```

**handler.kind 取值：**
- `extension` — JS handler。有 `function` → delegate 一行转发；有 `source` → 复制 JS 文件
- `backend` — Python handler（Agent 手写实现），脚本跳过生成
- `control` — 控制流 handler（Agent 手写实现），脚本跳过生成

**runtime 取值：**

| runtime | handler.kind | 生成行为 | 文件目录 |
|---|---|---|---|
| `"extension"` | `"extension"` | 生成 Python 桩 + JS | `extension_commands/` + `dom_handlers_new/` |
| `"backend"` | `"backend"` | SKIP | `backend_commands/` 或 `desktop_commands/` |
| `"control"` | `"control"` | SKIP | `control_commands/` |

> desktop 指令 `runtime` 用 `"backend"`，但 `handler.source` 指向 `desktop_commands/`。
> 判断标准：调用了 Win32 / UIA API → `desktop_commands/`；纯 Python 逻辑 → `backend_commands/`。

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

> **注意：** 不要使用 `str-dropdown`、`bool-check` 等名称。

**字段分组（`group`）：** `主属性`（默认）、`advanced`（高级）、`output`（输出）、`input`（输入）、`anchor`

### 2. 运行 generate_commands.py 生成桩代码

```bash
python scripts/generate_commands.py
```

**哨兵注释：** 脚本生成的文件第一行包含：

```python
# AUTO-GENERATED from commands/xxx.json — DO NOT EDIT directly.
```

```js
// AUTO-GENERATED from commands/xxx.json — DO NOT EDIT directly.
```

**覆盖规则：**
- **有哨兵注释** → 覆盖（脚本安全重新生成）
- **无哨兵注释** → KEEP（视为已手写实现）

### 3. 在桩文件基础上添加实现逻辑

**extension 指令：**
- Python 桩：脚本已生成 `@register_handler` + `params`。此文件含哨兵注释，**不要直接编辑**（下次运行脚本会被覆盖）。如需 Python 侧前置逻辑，写到独立文件再导入。
- JS handler：首次生成后可直接编辑。在 `registerHandler` 回调中实现浏览器操作。

**backend / desktop / control 指令：**
- 脚本跳过生成，从零手写。参考现有 handler 照抄结构：

```python
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="xxx", label="xxx", category="xxx", runtime="backend", ...)
class XxxHandler:
    params = [...]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra", {})
        # 通过 extra.get("paramName") 读取参数
```

- desktop 指令多一步：从 `_win32.py` 或 `_uia.py` 导入底层 API。

### 4. 重新构建 JS（仅 extension）

```bash
python scripts/build_content_js.py
```

### 5. 验证

重启服务器 → `auto_register()` 自动发现新 handler。

```bash
curl -X POST http://localhost:xxxx/api/commands/sync-check
curl -X POST http://localhost:xxxx/api/commands/validate
```

## 修改已有指令

| 指令类型 | 改 JSON 后 | 需手动同步 |
|---------|-----------|-----------|
| extension | 运行脚本 → Python 桩自动覆盖；JS KEEP | JS 参数变化需手动同步 |
| backend | 脚本 SKIP | `@register_handler` 参数 |
| desktop | 脚本 SKIP | `@register_handler` 参数 |
| control | 脚本 SKIP | `@register_handler` 参数 |

之后运行 `build_content_js.py`（extension）并验证。

## 禁止行为

| 禁止 | 原因 |
|------|------|
| 直接创建 handler 文件而不先建 JSON | JSON 是唯一事实来源 |
| 修改 JSON 后不运行 `generate_commands.py` | `@register_handler` 不会自动同步 |
| 手写 `@register_handler(...)` + `Param` boilerplate | 应由脚本生成，手写易遗漏 |
| 编辑含哨兵注释的 Python 桩文件 | 下次运行脚本会被覆盖 |

## 现有 handler 参考

### extension
| 指令 | 特点 |
|---|---|
| `clickElement` | 注册桩，JS delegate 到 doClick |
| `inputElement` | 注册桩，JS delegate 到 doInput |
| `waitForElement` | 注册桩，JS 自定义实现 |
| `launchBrowser` | 完整 execute，浏览器启动 + 扩展通信 |

### backend
| 指令 | 特点 |
|---|---|
| `setVar` | 变量操作，含值类型转换 |
| `httpRequest` | HTTP 请求 |

### desktop（runtime=backend，调用 Win32/UIA API）
| 指令 | 特点 |
|---|---|
| `findWindow` | 查找窗口，Win32 API |
| `clickControl` | 点击控件 |
| `inputControl` | 控件输入，WM_SETTEXT + keybd_event 降级 |
| `clickMenu` | 点击菜单项，Win32 菜单 API |
| `openApp` | 打开软件，subprocess 启动 |
| `sendKey` | OS 级按键，keybd_event |
| `findChild` | 查找子控件 |
| `findSibling` | 查找兄弟控件 |
| `findParent` | 查找父窗口 |

### control
| 指令 | 特点 |
|---|---|
| `forEachElement` | 循环遍历元素 |

## 架构约束

- `@register_handler` 装饰器注册到 `_HANDLER_REGISTRY`
- `auto_register()` 在服务器 lifespan 中调用 → 触发 `__init__.py` 自发现导入（含 `desktop_commands`）
- **JSON 是唯一事实来源。** 变更指令定义必须先改 JSON，再运行 `generate_commands.py`
- handler 参数名必须与 JSON `params[].name` 一致（`execute` 中通过 `extra.get("paramName")` 读取）
- **不要编辑含哨兵注释（`AUTO-GENERATED`）的 Python 文件**，它们会被脚本覆盖
