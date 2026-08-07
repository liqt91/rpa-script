/**
 * navigate — background handler.
 *
 * Navigates the active tab in the specified window to a new URL.
 */
registerBackgroundHandler('navigate', async function(step, agent) {
  const url = step.extra?.url;
  if (!url) throw new Error('缺少目标网址参数');

  // Determine target — reuse workTabId or find active tab in window
  let tabId = agent.workTabId;
  let windowId = agent.workWindowId;

  if (step.extra?.windowVar) {
    windowId = step.extra.windowVar.windowId || windowId;
  }

  if (!tabId && windowId) {
    const tabs = await chrome.tabs.query({ windowId, active: true });
    tabId = tabs[0]?.id;
  }
  if (!tabId) throw new Error('没有可用的标签页');

  await chrome.tabs.update(tabId, { url });

  if (step.extra?.waitLoad !== false) {
    // Wait for page load
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => resolve(), 30000);
      const listener = (updatedTabId, info) => {
        if (updatedTabId === tabId && info.status === 'complete') {
          clearTimeout(timeout);
          chrome.tabs.onUpdated.removeListener(listener);
          resolve();
        }
      };
      chrome.tabs.onUpdated.addListener(listener);
    });
  }

  // 确认 tab.url 已提交为新 URL：waitLoad 的 complete 事件与 tabs API 中
  // url 字段的更新存在时序差异，不确认就返回会让随后的 switchTab/closeTab
  // 按 URL 匹配时偶发查不到。轮询至多 5s，超时照常返回（由匹配侧重试兜底）。
  const targetHosts = (() => {
    try {
      const u = new URL(url);
      return new Set([u.host, u.host.replace(/^www\./, '')]);
    } catch (_) {
      return null;
    }
  })();
  if (targetHosts) {
    for (let i = 0; i < 25; i++) {
      try {
        const t = await chrome.tabs.get(tabId);
        if (t && t.url) {
          const h = new URL(t.url).host;
          if (targetHosts.has(h) || targetHosts.has(h.replace(/^www\./, ''))) {
            break;
          }
        }
      } catch (_) {}
      await new Promise(r => setTimeout(r, 200));
    }
  }

  // Re-inject content script after navigation
  await new Promise(r => setTimeout(r, 500));
  try { await agent._injectContentScript(tabId); } catch (e) {}

  return { tabId, windowId };
});
