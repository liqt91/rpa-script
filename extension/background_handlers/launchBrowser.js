/**
 * launchBrowser — background handler.
 *
 * Creates or reuses a browser window and returns {windowId, tabId}.
 * Called by background.js router via registerBackgroundHandler.
 */
registerBackgroundHandler('launchBrowser', async function(step, agent) {
  const url = step.extra?.url || 'about:blank';
  const state = step.extra?.windowState || 'normal';

  // ── Reuse an existing blank window (launched by backend) ──
  const allWins = await chrome.windows.getAll({ populate: true });
  for (const win of allWins.reverse()) {
    if (win.type !== 'normal') continue;
    const tab = win.tabs?.[0];
    if (tab && (tab.url === 'about:blank' || tab.url?.includes('newtab') || tab.url === 'edge://newtab/')) {
      agent.workWindowId = win.id;
      await chrome.tabs.update(tab.id, { url, active: true });
      await chrome.windows.update(win.id, { focused: true });
      agent.workTabId = tab.id;
      await new Promise(r => setTimeout(r, 500));
      try { await agent._injectContentScript(tab.id); } catch (e) {}
      return { windowId: win.id, tabId: tab.id };
    }
  }

  // ── No reusable window — create new ──
  const newWindow = await chrome.windows.create({ url, focused: true, state });
  agent.workWindowId = newWindow.id;
  const newTab = newWindow.tabs?.[0];
  if (newTab?.id) {
    agent.workTabId = newTab.id;
    await new Promise(r => setTimeout(r, 500));
    try { await agent._injectContentScript(newTab.id); } catch (e) {}
    return { windowId: newWindow.id, tabId: newTab.id };
  }
  throw new Error('Failed to create browser window');
});
