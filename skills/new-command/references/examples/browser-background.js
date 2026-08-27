// browser-background 黄金样例（照抄改 cmd 名与逻辑）
// 放 extension/background_handlers/myCmd.js；JSON 定义 handler.source 指向它
// （或 rpa_new_command 给 runtime="extension" + handlerKind="background" 自动落对）。

registerBackgroundHandler('myCmd', async (step, agent) => {
  // 可直接用 chrome.tabs.* / chrome.windows.*，以及 agent.workWindowId / agent.workTabId
  const tabs = await chrome.tabs.query({});
  const urls = tabs.map(t => t.url).filter(Boolean);

  // 返回 dict；value 会被 runner 写回 resultVar
  return { value: urls, count: urls.length };
});
