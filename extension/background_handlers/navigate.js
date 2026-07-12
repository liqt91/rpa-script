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

  // Re-inject content script after navigation
  await new Promise(r => setTimeout(r, 500));
  try { await agent._injectContentScript(tabId); } catch (e) {}

  return { tabId, windowId };
});
