/**
 * closeTab — background handler.
 *
 * Closes a tab by URL pattern, index, or the current work tab.
 */
registerBackgroundHandler('closeTab', async function(step, agent) {
  let windowId = agent.workWindowId;
  if (step.extra?.windowVar && typeof step.extra.windowVar === 'object') {
    windowId = step.extra.windowVar.windowId || windowId;
  }
  if (!windowId) {
    throw new Error('没有可用的浏览器窗口，请先执行打开浏览器指令');
  }

  const urlPattern = step.extra?.urlPattern;
  const tabIndex = step.extra?.tabIndex;
  let tabId;

  if (urlPattern) {
    // Close by URL match (case-insensitive), gets the FIRST match
    const tabs = await chrome.tabs.query({ windowId });
    const tab = tabs.find(t => t.url && t.url.toLowerCase().includes(urlPattern.toLowerCase()));
    if (!tab) {
      throw new Error('未找到匹配 URL 的标签页: ' + urlPattern);
    }
    tabId = tab.id;
  } else if (tabIndex !== undefined && tabIndex !== null && tabIndex !== '') {
    // Close by index in window
    const tabs = await chrome.tabs.query({ windowId });
    const idx = Number(tabIndex);
    if (idx < 0 || idx >= tabs.length) {
      throw new Error(`标签页序号 ${idx} 超出范围 (共 ${tabs.length} 个)`);
    }
    tabId = tabs[idx].id;
  } else {
    // Close current work tab
    tabId = agent.workTabId;
    if (!tabId) {
      const tabs = await chrome.tabs.query({ windowId, active: true });
      if (!tabs[0]?.id) throw new Error('没有可关闭的标签页');
      tabId = tabs[0].id;
    }
  }

  await chrome.tabs.remove(tabId);

  if (tabId === agent.workTabId) {
    agent.workTabId = null;
    agent._lastTabUrl = null;
  }

  return { closedTabId: tabId };
});
