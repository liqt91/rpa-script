/**
 * switchTab — background handler.
 *
 * Switches the active tab in the specified window and injects content script.
 * Updates agent.workWindowId and agent.workTabId to point to the new tab.
 */
registerBackgroundHandler('switchTab', async function(step, agent) {
  let windowId = agent.workWindowId;

  if (step.extra?.windowVar) {
    windowId = step.extra.windowVar.windowId || windowId;
  }

  if (!windowId) {
    throw new Error('没有可用的浏览器窗口，请先运行"打开浏览器"');
  }

  // Get the active tab in the target window
  const tabs = await chrome.tabs.query({ windowId, active: true });
  const tab = tabs[0];
  if (!tab || !tab.id) {
    throw new Error('未找到活跃标签页');
  }

  // Focus the window and tab
  await chrome.windows.update(windowId, { focused: true });
  await chrome.tabs.update(tab.id, { active: true });

  agent.workWindowId = windowId;
  agent.workTabId = tab.id;

  await new Promise(r => setTimeout(r, 500));
  try { await agent._injectContentScript(tab.id); } catch (e) {}

  return { windowId, tabId: tab.id, url: tab.url };
});
