# 指令类别与落点（浏览器类见 browser-dom / browser-background）

共四类 runtime；桌面指令在 JSON 里 **runtime 也是 `backend`**，靠 `handler.source` 指向 `desktop_commands/` 区分。

| 类别 | runtime | kind | 实现文件 | JS? |
|---|---|---|---|---|
| 浏览器页面（DOM） | `extension` | `extension` | `dom_handlers_new/<cmd>.js` | 有（见 browser-dom.md） |
| 浏览器后台 | `extension` | `extension` | `background_handlers/<cmd>.js` | 有（见 browser-background.md） |
| Python 逻辑 | `backend` | `backend` | `backend_commands/<cmd>.py` | 无 |
| 桌面 Win32/UIA | `backend` | `backend` | `desktop_commands/<cmd>.py` | 无 |
| 流程控制 | `control` | `control` | `control_commands/<cmd>.py`（`evaluate()` 非 execute） | 无 |

## 桌面指令（desktop）专属

- JSON 里 `runtime: "backend"`、`handler.kind: "backend"`、`handler.source` 指向 `src/runtime/commands/desktop_commands/<cmd>.py`。
- 底层能力放 helper（`execute` 里 `from ._xxx import ...`）：
  - `_win32.py` — Win32 API 封装（FindWindowW/SendMessageW/SetForegroundWindow 等）。
  - `_uia.py` — UIA 封装（UI Automation）。
  - `_desktop_ref.py` — Win32/UIA 统一路由引用（`make_win32_ref` / `make_uia_ref`，供「自动选择」类指令 `*Auto` 用）。
- 判断：调 Win32/UIA → `desktop_commands/`；纯 Python → `backend_commands/`。

## 最小 JSON 模板（照抄改）

```json
{
  "cmd": "myCommand", "label": "我的指令", "runtime": "backend",
  "category": "分类中文名", "categories": ["slug"], "icon": "fa-cog",
  "iconColor": "text-blue-500", "bgColor": "bg-blue-50",
  "categoryOrder": 50, "commandOrder": 10, "description": "指令描述",
  "params": [{"name": "paramName", "label": "参数显示名", "type": "string", "required": true}],
  "handler": {"kind": "backend", "source": "src/runtime/commands/backend_commands/myCommand.py"}
}
```

- backend/desktop/control：`handler.source` 指向 `.py`；
- 浏览器 DOM：`handler.source` 指向 `extension/dom_handlers_new/<cmd>.js`；
- 浏览器后台：`handler.source` 指向 `extension/background_handlers/<cmd>.js`（或走 `rpa_new_command` 的 `handlerKind="background"` 自动落对）。

## 修改已有指令

改 JSON 后跑 `command_builder.py <cmd>`：extension 桩被覆盖、backend/desktop 已存在则 KEEP（保留手写实现）。**改 JSON 后参数不会自动回填到手写文件**，需手动保持 JSON 与 `@register_handler` 一致（generate_commands 对已存在文件 KEEP）。
