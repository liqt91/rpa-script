/**
 * switchTab — background handler.
 *
 * Switches to a tab in the specified window.
 * Default: active tab. With urlPattern: first tab whose URL contains the pattern.
 */
registerBackgroundHandler('switchTab', async function(step, agent) {
  let windowId = agent.workWindowId;
  if (step.extra?.windowVar) {
    windowId = step.extra.windowVar.windowId || windowId;
  }
  if (!windowId) {
    throw new Error('没有可用的浏览器窗口，请先运行"打开浏览器"');
  }

  const urlPattern = step.extra?.urlPattern;
  let tab;

  if (urlPattern) {
    // Find tab by URL match (case-insensitive)
    const tabs = await chrome.tabs.query({ windowId });
    tab = tabs.find(t => t.url && t.url.toLowerCase().includes(urlPattern.toLowerCase()));
    if (!tab) {
      throw new Error('未找到匹配 URL 的标签页: ' + urlPattern);
    }
  } else {
    // Default: active tab
    const tabs = await chrome.tabs.query({ windowId, active: true });
    tab = tabs[0];
    if (!tab || !tab.id) {
      throw new Error('未找到活跃标签页');
    }
  }

  await chrome.windows.update(windowId, { focused: true });
  await chrome.tabs.update(tab.id, { active: true });

  agent.workWindowId = windowId;
  agent.workTabId = tab.id;

  await new Promise(r => setTimeout(r, 500));
  try { await agent._injectContentScript(tab.id); } catch (e) {}

  return { windowId, tabId: tab.id, url: tab.url };
});
