# Plan: 锚点优先的相对元素捕获

## Context
用户反馈当前“先捕获子元素、再选择锚点”的顺序不自然，希望改为**先在侧板选择已有元素作为锚点，再捕获其内部元素**，相对选择器在捕获时自动生成。

## Goals
1. 侧板顶部提供锚点选择下拉。
2. 选定锚点后，页面持续高亮该锚点，并保持激活直到手动清除或切换流程。
3. Alt+点击捕获时，自动从激活锚点计算相对选择器，随 `captureElement` payload 上报。
4. 保留全局捕获（无锚点）和捕获后修改锚点的兼容能力。
5. 后端模型不变，复用现有 `anchor_element_name` / `relative_selector` / `anchor_selector`。

## Design decisions
- 锚点选择器放在侧板 `workflowSelect` 旁，作为全局捕获模式切换。
- `content_capture.js` 维护 module-level `activeAnchor` 状态，收到 `setActiveAnchor` 后解析并持久高亮。
- 捕获时若 `activeAnchor` 存在，找到包含被点击元素的那个锚点实例，调用 `buildRelativeCss` / `buildRelativeXPath` 生成相对选择器。
- `anchorMode` 新增 `'anchor-first'`，与现有 `'auto'` / `'manual'` / `'none'` 共存。
- 激活锚点**不随单次捕获清除**，方便连续捕获同一锚点下的多个子元素。

## Implementation

### 1. extension/sidepanel.html
在 workflow-row 右侧或 name-row 上方增加：
- `<select id="activeAnchorSelect">`：选择已有元素。
- 锚点名称 pill / 清除按钮 `<button id="btnClearActiveAnchor">`。
- 无锚点时显示“全局捕获”。

### 2. extension/background.js
新增消息分支：
- `setActiveAnchor`：sidepanel → content_capture，payload `{ anchorSelector, anchorElementName, tabId }`。
- 转发方式同现有 `computeRelativeFromAnchor` / `verifyElement`。

### 3. extension/content_capture.js
新增：
- `let activeAnchor = null`，形状 `{ name, selector, family, elements }`。
- `setActiveAnchor` 消息处理器：
  - 用 `resolveAllForVerify` / `splitSelectorPrefix` 解析选择器。
  - 用 `highlightSelectorMatches` 持久高亮（与 3 秒校验高亮区分，单独 class/数组管理）。
  - 向 sidepanel 回发 `activeAnchorUpdated`。
- `performCapture()` 中：
  - 若 `activeAnchor` 存在，找到包含 `el` 的锚点实例。
  - 若未包含，回退为全局捕获并给出提示。
  - 调用 `buildRelativeCss(anchorEl, el)`，失败再试 `buildRelativeXPath`。
  - 生成的 payload 中 `relativeSelector`、`anchorSelector`、`anchorElementName` 直接填充，`anchorMode: 'anchor-first'`。
- sidepanel 关闭 / 切换流程 / 页面 unload 时调用清除高亮。

### 4. extension/sidepanel.js
新增：
- `activeAnchorName` / `activeAnchorSelector` 状态。
- `loadWorkflowElements()` 后渲染 `activeAnchorSelect` 选项。
- `activeAnchorSelect` change：发送 `setActiveAnchor`。
- 接收 `activeAnchorUpdated` 广播，更新 UI pill 与高亮数量提示。
- `btnClearActiveAnchor`：发送 `setActiveAnchor(null)`，清空本地状态。
- 切换 workflow 时自动清空 active anchor。
- 保存后不清除 active anchor，方便继续捕获同锚点下其他子元素。
- 保留下方 `anchorCard` 的重新计算 / 校验功能，作为捕获后微调。

### 5. 后端 / 导出器
无需改动：元素库中 `anchor_element_name` 已存在；导出器已支持按名称匹配循环自动相对解析。

## Verification
1. 打开侧板，选择流程，从顶部下拉选 `comment_card` 作为锚点。
2. 确认页面所有 `comment_card` 被持久高亮。
3. Alt+点击 `.author-name`，侧板弹出后相对选择器已自动生成。
4. 保存，检查数据库 `anchor_element_name='comment_card'`，`relative_selector` 非空。
5. 不关闭侧板，继续 Alt+点击 `.comment-content`，确认仍相对同一锚点生成。
6. 点击清除锚点，Alt+点击其他元素，确认恢复全局捕获。
7. 切换流程，确认 active anchor 自动清空。
8. 运行 `python .harness/scripts/ast_structural_check.py`、ruff、pytest、UI build。

## Critical files
- `extension/sidepanel.html`
- `extension/sidepanel.js`
- `extension/background.js`
- `extension/content_capture.js`

## Notes
- 若锚点选择器匹配多个 DOM 项，高亮全部；相对路径以实际包含被点击元素的那个实例为准。
- 若被点击元素不在任何锚点实例内部，视为全局捕获并给出提示，避免误操作。
- 页面刷新后 active anchor 不会自动恢复（避免状态漂移），用户需重新选择。
