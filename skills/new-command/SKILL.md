---
name: new-command
description: 创建新的 RPA 指令（command），一次命令生成+校验+热重载。四类：extension（浏览器：DOM 页面操作 / background 后台）、backend（本地执行）、desktop（桌面操作）、control（控制流）。
---

# 新增指令

> ## ⚠️ 第 0 步（不可跳过，先做这个）：调用生成命令
>
> **生成任何指令前，第一步必须调用 `rpa_new_command`（DSH 工具）。**
>
> 这是**唯一**的生成方式。一次调用完成：写定义 → 生成桩 → 构建 JS → 质量门禁 → 后端热重载 + 校验。
>
> **复杂指令（要改底层 API / 填 handler 实现）也一样先走命令**：命令先生成骨架 + 注册 + 热重载
> （`ok=true`、实现可后续填）。**helper/execute 是第二步人工填的业务逻辑**，填完再跑一次
> `rpa_new_command(cmd, verify={...})` 复验。不能因为"要写业务实现"就跳过命令。
>
> **如果你发现自己做了下面任一件事，说明你走错了，立刻停下回到第 0 步：**
> - ❌ 手工跑 `generate_commands.py` / `build_content_js.py` / `build_background_js.py` / `POST /api/commands/reload`
> - ❌ 手工编辑 `commands/<cmd>.json` 之外的 handler 文件（generate_commands 已生成骨架）
> - ❌ 在写临时测试脚本（`_tmp*.py`/`_validate*.py`/`_selftest.py`）——用命令的 `verify` 替代
> - ❌ 在 shell 里手敲 `python`/`cmd` 跑 `command_builder.py`（会触发沙箱确认框；只在 `rpa_new_command` 工具内部执行）
>
> 下面所有内容只是**参数/目录参考**，先调用命令，再回头看这些。

## 快速分流

| 要建的指令 | 读 |
|---|---|
| 浏览器页面操作（DOM：点击/输入/采集） | `references/fact-card-browser.md` + `references/browser-dom.md` |
| 浏览器后台（chrome.tabs/windows） | `references/fact-card-browser.md` + `references/browser-background.md` |
| 桌面 Win32/UIA | `references/category-map.md`（desktop 段） |
| Python 本地逻辑 | `references/category-map.md`（backend 段） |
| 流程控制（if/for/while） | `references/category-map.md`（control 段） |

- 参数 type 白名单 → `references/fact-card-params.md`
- 黄金样例照抄改 → `references/examples/`

## 核心不变量（改了机制必须同步这里）

- **JSON 是唯一事实来源**：先改 `commands/<cmd>.json`，再跑 `command_builder.py`/`generate_commands.py`；参数名与 `params[].name` 一致。
- **新增/修改 extension 指令后，插件已自动重载**（`chrome.runtime.reload()`），**不必手动重载扩展**——详见 `references/fact-card-browser.md`。
- **改核心运行时模块（`extension_runner.py` 等）需重启后端**：`/api/commands/reload` 不重载已在 `sys.modules` 的模块；新增指令本身无需重启。

## 文件边界（防 glob 超时 · 必读）

**glob 必须显式传 `path` 收窄**（裸 glob 从仓库根整树扫会踩 `.venv/`(1.8万文件)、`src/`、`webrpa/` 等巨大目录而 30s 超时）：
- `glob(path:"<repo>/commands", pattern:"*.json")`
- `glob(path:"<repo>/src/runtime/commands/backend_commands", pattern:"*.py")`
- 禁止无 `path` 的裸 glob、禁止 `Get-ChildItem -Recurse` 全树统计。

**可写**：`commands/<cmd>.json`（唯一事实来源）· `src/runtime/commands/<dir>/<cmd>.py`（脚手架首建后 KEEP）· `extension/dom_handlers_new/<cmd>.js`（仅 browser-dom）· `extension/background_handlers/<cmd>.js`（仅 browser-background）· `src/runtime/commands/types/categories.json`（仅新增分类 slug）。

**勿碰**：extension Python 桩（`DO NOT EDIT` 哨兵，每次被覆盖）· `dist/**/content.js`、`background.js`（编译产物）· 前端 `static/workflow-editor/`（vite 产物）。

**绝对不碰**：`webrpa/` `WebRPA/` `.venv/` `node_modules/` `dist/` `build/` `tdSelector_1.2.7/` `rpa-dsh-plugin/python/` `data/*` `tmp/` `__pycache__/` `*.pyc` `.env`(密钥) `.private/` `.harness/` `*.log`。
