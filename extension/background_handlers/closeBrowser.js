/**
 * closeBrowser — background handler.
 *
 * Closes the browser window associated with the given window variable.
 * Called by background.js router via registerBackgroundHandler.
 */
registerBackgroundHandler('closeBrowser', async function(step, agent) {
  let windowId = agent.workWindowId;
  // If the extra has a windowId directly (resolved by runner), use it
  if (step.extra?.windowId) {
    windowId = step.extra.windowId;
  }
  // If the windowVar was sent as a resolved dict with windowId
  if (step.extra?.windowVar && typeof step.extra.windowVar === 'object') {
    windowId = step.extra.windowVar.windowId || windowId;
  }
  if (!windowId) {
    throw new Error('没有可关闭的窗口，请先执行打开浏览器指令');
  }
  try {
    await chrome.windows.remove(Number(windowId));
    if (windowId === agent.workWindowId) {
      agent.workWindowId = null;
      agent.workTabId = null;
      agent._lastTabUrl = null;
    }
    return { closedWindowId: windowId };
  } catch (e) {
    throw new Error('关闭窗口失败: ' + e.message);
  }
});
