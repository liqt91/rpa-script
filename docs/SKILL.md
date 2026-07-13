---
name: rpa-command-dev
description: |
  Develop new commands for the RPA browser automation system.
  Use when the user asks to create, modify, or debug RPA workflow commands.
  Covers JSON definitions, JS/Python handlers, and the build pipeline.
version: 1.0.0
---

# RPA Command Development Guide

## Quick Start

```bash
# Add a command in 4 steps:
# 1. Create JSON definition → commands/<cmdName>.json
# 2. Create handler → extension/dom_handlers_new/<cmdName>.js  (or bg/backend/control)
# 3. Build → python scripts/build_extension.py
# 4. Restart server + reload extension
```

## Architecture

```
commands/<cmd>.json          ← JSON 定义（参数、分类、图标…）
    │
    ├─ generate_commands.py  → src/runtime/commands/<runtime>/<cmd>.py  (自动生成桩)
    │
    ├─ build_content_js.py   → dist/desktop/extension/content.js  (DOM handler 打包)
    └─ build_background_js.py → dist/desktop/extension/background.js  (BG handler 打包)
    │
    ├─ runner: extension_runner.py  (调度引擎)
    └─ frontend: workflow-editor  (NodeForm 读 fields 渲染表单)
```

## Command Types

| Runtime | 执行位置 | Handler 位置 | Python 文件 |
|---------|---------|-------------|------------|
| `extension` (bg) | 扩展后台 | `extension/background_handlers/<cmd>.js` | `extension_commands/<cmd>.py` (自动生成) |
| `extension` (DOM) | 页面 content script | `extension/dom_handlers_new/<cmd>.js` | `extension_commands/<cmd>.py` (自动生成) |
| `backend` | Python 后端 | `src/runtime/commands/backend_commands/<cmd>.py` | 手工编写 |
| `control` | Python 后端（容器） | `src/runtime/commands/control_commands/<cmd>.py` | 手工编写 |

## Step 1: JSON Definition

文件：`commands/<cmdName>.json`

```json
{
  "cmd": "myCommand",           // 唯一标识，驼峰命名
  "label": "我的指令",           // 前端显示名
  "runtime": "extension",       // extension | backend | control
  "category": "页面操作",        // 分类（旧字段，用于旧 API）
  "icon": "fa-star",            // Font Awesome 图标
  "iconColor": "text-blue-500", // Tailwind 颜色
  "bgColor": "bg-blue-50",
  "categoryOrder": 40,          // 分类内排序权重
  "commandOrder": 10,
  "description": "指令说明",
  "enabled": true,
  "params": [
    {
      "name": "elementName",    // 参数名（驼峰）
      "label": "目标元素",
      "type": "element",        // 类型见 value_types.json
      "isPrimaryElement": true, // 标记为主元素（前端特殊渲染）
      "required": true,
      "group": "主属性"          // 主属性 | advanced | output | anchor | condition
    },
    {
      "name": "resultVar",
      "label": "保存到变量",
      "type": "string",
      "default": "result1",
      "group": "output"
    }
  ],
  "categories": ["page"],       // 新分类（slug 数组），对应 categories.json
  "handler": {
    "kind": "extension",        // extension | backend | control
    "source": "extension/dom_handlers_new/myCommand.js"  // JS 文件路径
  }
}
```

### Params 类型（部分）

| type | 说明 | 前端渲染 |
|------|------|---------|
| `string` | 文本输入 | input |
| `number` | 数字输入 | input type=number |
| `boolean` | 开关 | checkbox |
| `select` | 下拉（需配 options） | select |
| `element` | 单元素选择器 | 元素选择器 |
| `element-list` | 多元素选择器 | 元素列表 |

### 分类体系

`src/runtime/commands/types/categories.json`:
```json
{"categories": [
  {"slug": "browser", "name": "浏览器", "icon": "fa-chrome"},
  {"slug": "page", "name": "页面操作", "icon": "fa-mouse-pointer"},
  {"slug": "data", "name": "数据提取", "icon": "fa-table"},
  {"slug": "variable", "name": "变量", "icon": "fa-code"},
  {"slug": "logic", "name": "逻辑", "icon": "fa-code-branch"}
]}
```

JSON 的 `categories` 数组填 slug（如 `["data"]`），显示时映射到 name。

## Step 2: Handler

### 后台 handler（浏览器操作：打开/关闭/标签页）

`extension/background_handlers/myCommand.js`:
```javascript
registerBackgroundHandler('myCommand', async function(step, agent) {
    // agent 提供:
    //   agent.workTabId, agent.workWindowId
    //   agent._send('stepResult', {stepId, result})
    //   agent._send('stepError', {stepId, error})
    //   await chrome.tabs/windows API

    const tabId = /* ... */;
    return { myResult: true };
});
```

### DOM handler（页面操作：点击/输入/提取）

`extension/dom_handlers_new/myCommand.js`:
```javascript
/**
 * myCommand — DOM handler.
 */
registerHandler('myCommand', async function({ locator, selectorFamily, extra }) {
    // locator: 已解析的元素选择器（css/xpath）
    // selectorFamily: "css" | "xpath"
    // extra: { humanLike, timeout, scope, ... }

    const el = findTarget(locator, selectorFamily);
    // el -> DOM Element

    // 模拟人工操作时返回 viewport 坐标供 runner 移动真实鼠标
    if (extra?.humanLike ?? true) {
        const rect = el.getBoundingClientRect();
        const viewX = Math.round(rect.left + rect.width / 2);
        const viewY = Math.round(rect.top + rect.height / 2);
        _ensureCalibrationCapture();  // 自动标定

        // 读标定偏移
        let cal = null;
        try {
            const raw = sessionStorage.getItem('_rpaHoverCal');
            if (raw) cal = JSON.parse(raw);
        } catch (_) {}

        if (cal) {
            const dpr = window.devicePixelRatio || 1;
            return {
                myResult: true, viewX, viewY,
                screenX: Math.round((cal.offX + viewX) * dpr),
                screenY: Math.round((cal.offY + viewY) * dpr),
            };
        }
        return { myResult: true, viewX, viewY,
            dpr: window.devicePixelRatio || 1, _needsCalib: true };
    }

    // humanLike=false: 合成事件
    // el.click(); el.dispatchEvent(new MouseEvent(...));
    return { myResult: true };
});
```

### 常用 content script 函数

| 函数 | 用途 |
|------|------|
| `findTarget(locator, family)` | 查找元素（找不到抛异常） |
| `resolveLocator(loc, fam, mode)` | 解析定位器（含循环上下文） |
| `_ensureCalibrationCapture()` | 注册 mousemove 标定监听 |
| `sleep(ms)` | 等待 |
| `randNormal(mean, stddev)` | 随机延迟（正态分布） |

### Backend handler（本地执行：变量/日志）

`src/runtime/commands/backend_commands/myCommand.py`:
```python
from ...workflow.handlers.registry import register_handler, Param

@register_handler(cmd="myCommand", label="我的指令",
    category="数据提取", runtime="backend",
    icon="fa-star", icon_color="text-blue-500",
    bg_color="bg-blue-50",
    category_order=40, command_order=10)
class MyCommandHandler:
    params = [
        Param("someParam", "参数名", "string", default=""),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        # runner.vars: 变量字典
        # runner._emit({"type": "stepComplete", ...})
        # runner._find_elements / runner._check_element_exists ...

        result = {"someResult": "done"}
        runner.completed += 1
        await runner._emit({
            "type": "stepComplete",
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "result": result,
        })
        return True
```

### Control handler（容器/循环）

`src/runtime/commands/control_commands/myLoop.py`:
```python
from ...workflow.handlers.registry import register_handler, Param
from ...workflow.extension_runner import LoopBreak, LoopContinue

@register_handler(cmd="myLoop", label="我的循环",
    category="循环", runtime="control",
    is_container=True, closes_with="endLoop")
class MyLoopHandler:
    params = [...]

    @staticmethod
    async def execute(runner, cmd_type, instr, extra):
        body = instr.get("body", [])
        for item in items:
            if runner._stopped: break
            try:
                if not await runner._run_body(body):
                    return False
            except LoopBreak: break
            except LoopContinue: continue
        runner.completed += 1
        await runner._emit({...})
        return True
```

## Step 3: Build & Test

```bash
# 构建扩展（打包 JS + 生成 Python 桩）
python scripts/build_extension.py

# 如果你的指令是 DOM handler，改动在 content.js
# 如果是 BG handler，改动在 background.js

# 启动后端
python -m src.runtime.main

# 刷新 Chrome 扩展
# chrome://extensions → 刷新按钮

# 前端热更新自动，或手动构建
cd src/ui/workflow-editor && npm run build
```

## 常见模式

### 元素操作 + 真实鼠标

任何操作元素（点击/悬停/输入）且 `humanLike=true`，应返回 `viewX/viewY` 坐标。Runner 自动处理鼠标移动+标定。

```javascript
// 返回格式（有标定）
return { clicked: true, viewX, viewY, screenX, screenY };

// 返回格式（无标定，runner 会自动两阶段标定）
return { clicked: true, viewX, viewY, dpr, _needsCalib: true };

// humanLike=false 时只返回结果，不触发鼠标移动
return { clicked: true };
```

### 提取数据

复用 `doExtract`：
```javascript
registerHandler('myExtract', async (args) => {
    args.extra = { ...(args.extra || {}), action: 'getAttr', attribute: 'src' };
    return doExtract(args);  // → { value, text, extracted }
});
```

### 结果字段约定

| 字段 | 前端显示 |
|------|---------|
| `result.clicked` | "点击成功" |
| `result.input` | "输入: xxx" |
| `result.extracted` | "提取: xxx" |
| `result.scrolled` | "滚动: true" |
| `result.hovered` | "悬停成功" |
| `result.pressed` | "按键: xxx" |
| `result.log` | "📝 xxx" |

## 调试技巧

- **Content script 日志**：F12 → Console → 选 content script 上下文
- **Background 日志**：chrome://extensions → Service Worker 链接
- **后端日志**：看终端输出，带 `[ExtensionRunner]` 前缀
- **前端 Network**：看 `/api/workflows/commands-new` 和 `/api/commands/definitions`
