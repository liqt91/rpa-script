# Repro: openBrowser 后 navigate 报 "窗口变量 'browser1' 未定义"

## Environment
- Branch: `feat/browser-extension-agent`
- File: `src/runtime/workflow/extension_runner.py`
- Commit before fix: `254edc5`

## Steps
1. 新建一个流程，包含两个步骤：
   - 步骤 A：`openBrowser`，保存窗口对象到变量 `browser1`（默认值）。
   - 步骤 B：`navigate`，打开任意网址，窗口变量选择 `browser1`。
2. 执行该流程。

## Expected
- `openBrowser` 成功启动浏览器并创建/复用窗口。
- `navigate` 能读取到 `browser1` 变量，在对应窗口内打开网址。

## Actual
- `openBrowser` 成功。
- `navigate` 步骤失败，报错：`窗口变量 'browser1' 未定义，请先执行打开浏览器指令`。

## Root cause
`openBrowser` 是本地命令 (`@register_local("openBrowser")`)，由 `_local_openBrowser` 处理。该函数调用扩展创建窗口后会得到 `{windowId, tabId}` 结果，但没有根据指令的 `saveToVar` 字段将其写入 `runner.vars`。后续 `navigate` 等需要 `windowVar` 的步骤因此找不到 `browser1`。

## Fix location
`src/runtime/workflow/extension_runner.py:1719-1727` — 在 `_local_openBrowser` 收到扩展返回结果后，将窗口对象持久化到 `runner.vars[save_to_var]`。

## Verification
- 结构测试：`python .harness/scripts/ast_structural_check.py` → PASSED
- 修复后重新执行上述流程，`navigate` 应能正确读取 `browser1` 并在已打开窗口中导航。
