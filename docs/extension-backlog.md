# Extension Backlog

## 1. setVar 支持  ✅ DONE (方案 B)

- [x] `extension_runner.py` 维护 `self.vars` 变量池
- [x] 支持 `${varName}` 和 `{{varName}}` 占位符替换（递归遍历 dict/list/str）
- [x] `setVar` 指令本地执行，不发送到扩展
- [x] `getText`/`getAttr`/`getValue` 提取结果支持 `saveToVar` 存入变量池
- [x] `extension_emitter.py` 将 `setVar` 加入支持类型列表

**变量引用格式**: `${varName}` 或 `{{varName}}`，可在任意 `extra` 字符串值中使用。

## BUG: Alt 组合键冲突

Current: `content_capture.js` 中 `keydown` 监听 `e.key === 'Alt'` 直接 `e.preventDefault()` 进入捕获模式。但浏览器/系统的 Alt+A（截图）、Alt+F4 等快捷键被拦截。

Fix needed:
- 仅当单独按下 Alt（无其他组合键）时进入捕获模式
- 或者改为双击 Alt、或 Alt 长按进入，释放 Alt 退出
- 确保 `e.preventDefault()` 只在真正进入捕获模式时调用

## 2. Merge element capture from browser_extension/  ✅ DONE

- [x] Locator candidate generation
- [x] Alt+click capture mode
- [x] Save to backend element library
- [x] background.js forwards captureElement to backend WS

## 3. 捕获元素确认弹窗 + 截图

Current: Alt+Click 后直接发送到后端保存，用户无法确认或编辑。

待实现:
- 捕获后弹出确认/编辑对话框（在页面内或扩展 popup）
- 对话框展示: 候选选择器列表（含分数、匹配数）、元素截图、特征信息
- 用户可手动选择/编辑 locator，确认后再保存
- 截图: 使用 `chrome.tabs.captureVisibleTab` 截取元素区域或全页
- 保存内容扩展到: candidates（完整列表）、matchCount、score、screenshot（base64）

## 4. 保存后前端元素库自动刷新

Current: 元素库页面（/elements）是静态列表，捕获新元素后不会自动显示。

待实现:
- 捕获元素保存到后端后，前端元素库页面实时刷新或推送更新
- 方案: WebSocket 广播 `elementCaptured` 事件，前端监听并刷新列表
- 或前端轮询 /api/elements

## 5. 扩展执行支持从空白页/受限页开始

Current: `_handleExecuteStep` 获取 active tab，如果当前是 `chrome://`、`edge://`、`about:blank` 等受限页面，`chrome.scripting.executeScript` 会报错 "Cannot access chrome:// and edge:// URLs"。

待实现:
- 检测当前 tab URL 是否为受限页面（chrome://, edge://, about:, chrome-extension://, file:// 等）
- 如果是受限页面:
  - `navigate` 步骤: 直接 `chrome.tabs.create({url})` 创建新标签页导航
  - 其他步骤: 报错提示 "请切换到普通网页标签页"
- 如果没有 active tab: 同样处理
