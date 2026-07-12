/**
 * newTab — background handler.
 *
 * Opens a new tab in the specified browser window.
 * Called by background.js router via registerBackgroundHandler.
 */
registerBackgroundHandler('newTab', async function(step, agent) {
  const url = step.extra?.url || 'about:blank';
  const active = step.extra?.active !== false;

  // Determine target window — use agent's work window if windowVar not specified
  let windowId = agent.workWindowId;
  if (step.extra?.windowVar) {
    // windowVar contains {windowId, tabId} from caller
    windowId = step.extra.windowVar.windowId || windowId;
  }

  if (!windowId) {
    throw new Error('没有可用的浏览器窗口，请先运行"打开浏览器"');
  }

  const newTab = await chrome.tabs.create({ url, active, windowId });
  agent.workTabId = newTab.id;

  await new Promise(r => setTimeout(r, 500));
  try { await agent._injectContentScript(newTab.id); } catch (e) {}

  return { windowId, tabId: newTab.id };
});
