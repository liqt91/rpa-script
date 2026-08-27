# 浏览器后台指令（background handler）

> 部分浏览器指令需要 **chrome.\* API**（`chrome.tabs.query`、`chrome.windows`、窗口会话），
> content script 访问不到，须走 **background handler**。先读 `fact-card-browser.md`，再读本文件。

## 放哪 / 怎么触发

- 实现文件：`extension/background_handlers/<cmd>.js`，`handler.source` 必须指向 `extension/background_handlers/<cmd>.js`（**不是** dom_handlers_new）。
- 用 `rpa_new_command` 时给 `runtime="extension"` + `handlerKind="background"`，**工具自动把 source 落对，并自动 `build background.js`**——不用手改 JSON、不用手动跑构建。

## 签名

```js
registerBackgroundHandler('cmd', async (step, agent) => {
  // 可直接用 chrome.tabs.* / chrome.windows.*，以及 agent.workWindowId / agent.workTabId
  return { value: [...] };   // value 写回 resultVar
});
```

## 关键点

- 需要 manifest 的 `tabs`/`windows` 权限（项目已有，无需改 manifest）。
- **可用 Node 桩验证**：`scripts/verify_web_handler.mjs` 已 stub `chrome.tabs.query/update/get` 与 `chrome.windows.update`，并按 `(step, agent)` 调用后台 handler——`rpa_new_command(cmd, verify={...})` 会自动检测 `background_handlers/` 并跑桩（无需重载扩展）。
- **写回变量约定同 DOM handler**：返回 `{ value: [...] }` → runner 把数组写入 resultVar（`extracted`→`navigatedTo`→`value`→整 dict）。

## 注意

自包含后台 handler 可直接桩验证；依赖 `background_base.js` 共享 helper（如 switchTab 的 `findTabByUrlPattern`）的，桩里需另行 stub（当前桩未覆盖 base helper）。
