/**
 * getCurrentUrl — background handler.
 *
 * 直接在后台读取当前工作标签页的 URL，不经过 content.js，
 * 避免导航刚发生时 content 未注入/重注入的竞争超时。
 */
registerBackgroundHandler('getCurrentUrl', async function(step, agent) {
  const tabId = await agent._ensureWorkTab(step);
  const tab = await chrome.tabs.get(tabId);
  return { url: tab.url || '', title: tab.title || '' };
});
