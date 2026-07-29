# RPA 指令体系现状总结

## 一、整体架构

新指令体系采用 **JSON 定义 + 代码生成** 模式：

```
commands/<cmd>.json          ← 唯一事实来源（类型、参数、handler 指向）
       │
       ▼
scripts/generate_commands.py  ← 根据 JSON 生成 Python 注册桩
       │
       ▼
src/runtime/commands/
  ├── backend_commands/      ← 本地端操作指令（Python execute 实现）
  ├── extension_commands/    ← 扩展端执行指令（Python 注册桩）
  ├── control_commands/      ← 流程控制指令（if / for / while）
  └── desktop_commands/      ← 桌面操作指令（Win32 / UIA）
       │
       ▼
scripts/build_content_js.py  ← 构建浏览器扩展 content.js
```

## 二、52 个指令分类

### 1. extension（15 个）— 浏览器扩展执行

| 指令 | 功能 | 代码位置 |
|------|------|---------|
| `launchBrowser` | 启动浏览器 | `extension_commands/` + `background_handlers/` |
| `navigate` | 页面导航 | 同上 |
| `clickElement` | 点击元素 | `extension_commands/` + `dom_handlers_new/` |
| `inputElement` | 输入文本 | 同上 |
| `getText` | 获取文本 | 同上 |
| `getElementLink` | 获取链接 | 同上 |
| `hover` | 鼠标悬停 | 同上 |
| `waitForElement` | 等待元素 | 同上 |
| `scrollIntoView` | 滚动到元素 | 同上 |
| `takeScreenshot` | 截图 | 同上 |
| `pressKey` | 按键 | 同上 |
| `newTab` | 新建标签页 | `extension_commands/` + `background_handlers/` |
| `switchTab` | 切换标签页 | 同上 |
| `closeTab` | 关闭标签页 | 同上 |
| `closeBrowser` | 关闭浏览器 | 同上 |

特点：Python 端只有 `@register_handler` 注册桩，实际逻辑在浏览器扩展的 JS 中执行。

### 2. backend（30 个）— 后端 Python 执行

| 子类 | 指令 | 代码位置 |
|------|------|---------|
| 基础 | `setVar`, `log`, `wait` | `backend_commands/` |
| 桌面 Win32 | `findWindowWin32`, `findChildWin32`, `findParentWin32`, `findSiblingWin32`, `clickControlWin32`, `clickMenuWin32`, `inputControlWin32`, `sendKeyWin32`, `closeWindowWin32`, `openAppWin32`, `waitWin32`, `pickFromPathWin32` | `desktop_commands/` |
| 桌面 UIA | `findWindowUia`, `clickElementUia`, `inputElementUia`, `pickElementUia` | `desktop_commands/` |
| 桌面通用 | `findWindow`, `findChild`, `findParent`, `findSibling`, `clickControl`, `clickMenu`, `inputControl`, `openApp`, `sendKey`, `closeWindow`, `pickFromPath` | `desktop_commands/` |

特点：完整的 `execute()` 实现，直接在 Python 后端运行。

### 3. control（7 个）— 流程控制

| 指令 | 功能 |
|------|------|
| `forEachElement` | 循环遍历元素 |
| `forList` | 循环列表 |
| `forRange` | 循环范围 |
| `whileCondition` | 条件循环 |
| `ifElementVisible` | 条件判断 |
| `break` | 跳出循环 |
| `continue` | 跳过本次 |
| `endLoop` | 结束标记 |

特点：由 emitter 展开，不产生实际运行时指令，只控制流程结构。

## 三、指令依赖关系

### 上下文依赖
- **窗口变量**：`launchBrowser` 产生 `windowVar`，后续所有浏览器指令依赖它
- **元素库**：`clickElement` / `getText` 等依赖预先捕获的 `elementName`
- **循环上下文**：`forEachElement` 内部的 `child` 元素依赖外层循环

### 典型流程
```
launchBrowser → navigate → waitForElement → clickElement → getText → closeBrowser
```

### 容器指令
```
forEachElement
  ├── getText (child)
  ├── getElementLink (child)
  └── writeTableRow
```

## 四、当前测试手段

| 层级 | 方式 | 现状 |
|------|------|------|
| L1 单指令沙盒 | `POST /api/commands/definitions/{type}/test` | backend 可直接执行，extension 需浏览器连接 |
| L2 测试流程模板 | 指令 JSON 中 `testTemplates` 字段 | 仅 `clickElement`、`setVar` 有示例 |
| L3 AI 生成测试流程 | `POST /api/commands/definitions/{type}/generate-test-flow` | 依赖 LLM，质量不稳定 |
| L4 单元测试 | `pytest src/runtime/tests/` | 127 个测试，主要覆盖 handler 逻辑和 emitter |

## 五、测试痛点

1. **依赖链**：`forEachElement` 没有子节点没意义，`clickElement` 没有浏览器和元素跑不了
2. **上下文获取**：`windowVar`、元素选择器、循环变量都是运行时动态产生，静态填不出来
3. **参数组合爆炸**：每个指令多个参数，手动配置测试流程成本高
4. **验证困难**：很多指令是副作用操作（点击、输入），难以自动断言结果
