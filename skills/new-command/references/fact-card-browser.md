# 浏览器指令事实卡

> 只对「新建浏览器指令（extension，含 DOM 与 background 两种形态）」生效。这些是**环境事实与禁令**，
> 读完照做，不必再 grep 源码验证；不确定时以本卡为准。

## ① 重载已自动化（勿手动重载扩展）

- `rpa_new_command` 在 build 完成后**自动**通过 WS 触发 `chrome.runtime.reload()`，扩展自行重载 + 重连，**不需要** agent 手动开 `edge://extensions` 点刷新。
- **有活跃流程时的守卫**：命令检测到后台有工作流正在运行时，返回 `needs_extension_reload` 标记而**不直接重载**（避免打断）。此时**必须用 `ask_user_question` 问用户**：
  - 「① 等待流程结束后再重载（默认推荐）② 立即重载（会打断当前运行）」
  - 选「等待」→ 轮询 `GET /api/workflows/runs/active` 直到 `count=0`，再 `POST /api/extension/command?action=reloadExtension&browser_type=edge`；
  - 选「立即」→ 直接 `POST /api/extension/command?action=reloadExtension&browser_type=edge`。
- 多浏览器：`command_builder.py` 自动遍历所有在线浏览器（chrome/edge）逐个重载，agent 无需管。

## ② 🚫 禁止 eval / new Function 动态执行 handler

- MV3 下 content script 隔离世界与 extension pages 的 CSP **都不允许 `unsafe-eval`**（只有 `wasm-unsafe-eval`）。
- 任何「运行时把 handler 源码字符串 eval / new Function 后注册」的方案都会被 CSP 拦截，报错：
  `'unsafe-eval' is not an allowed source of script: script-src 'self' 'wasm-unsafe-eval' ...`
- **新增/修改指令只走「编译期拼进 content.js / background.js」这条正规路**（已由命令自动化）。不要设计任何 eval 动态注入方案。

## ③ DOM 与 background 的生效差异

重载扩展（`chrome.runtime.reload()`）只更新扩展代码 + 重启 service worker；**已打开页面的 content script 仍是旧版**：

- **background 类**（launchBrowser / navigate / switchTab / getAllTabs…，跑在 service worker）：重载即生效，**无需刷新页面**。
- **DOM 类**（clickElement / getText / inputElement / 采集…，注入页面执行）：重载只更新扩展代码，
  **已打开页面里跑的还是旧 content script**。但流程里 DOM 指令前通常有 `launchBrowser`/`navigate`，
  它们会 `_injectContentScript` 注入**最新** content.js，所以**多数场景也无需手动刷页面**；
  仅当「在已开着且不重新导航的页面上直接测新 DOM 指令」时才需手动刷新那一个页面。

## ④ 编译是自动的，勿手动

`build_content_js.py` / `build_background_js.py` 由 `rpa_new_command` 内部执行。agent **绝不手动跑**这些脚本
（手动跑触发沙箱确认框），也**绝不手改** `dist/**/content.js`、`background.js`（编译产物，会被覆盖）。
