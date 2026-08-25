/**
 * getAllTabs — background handler.
 *
 * 获取指定浏览器窗口（或所有窗口）中打开的全部标签页列表。
 * 结果写回变量走 runner 约定：返回 { value: [...], count }，runner 把 value（数组）写入 resultVar。
 *
 * 目标窗口解析：
 *   - windowVar 提供且解析为窗口对象（{windowId, tabId}）→ 只取该窗口的标签页；
 *   - 否则使用当前工作窗口（agent.workWindowId）；
 *   - 两者都没有 → 返回所有窗口的全部标签页（"所有打开的网页标签页"的兜底）。
 */
registerBackgroundHandler('getAllTabs', async function(step, agent) {
  const extra = step.extra || {};
  const onlyWebPages = extra.onlyWebPages !== false;

  let query = {};
  const wv = extra.windowVar;
  if (wv && typeof wv === 'object' && wv.windowId != null) {
    query.windowId = wv.windowId;
  } else if (agent.workWindowId) {
    query.windowId = agent.workWindowId;
  }
  // query 为空对象 → chrome.tabs.query({}) 返回所有窗口的所有标签页

  let tabs = await chrome.tabs.query(query);

  if (onlyWebPages) {
    tabs = tabs.filter(t => t.url && /^https?:/i.test(t.url) && !/^chrome-extension:/i.test(t.url));
  }

  const items = tabs.map(t => ({
    index: t.index,
    id: t.id,
    windowId: t.windowId,
    title: t.title || '',
    url: t.url || '',
    active: !!t.active,
    pinned: !!t.pinned,
    discarded: !!t.discarded,
  }));

  // 跨窗口按窗口 id、窗口内按 index 排序，保证结果确定、可预期
  items.sort((a, b) => (a.windowId - b.windowId) || (a.index - b.index));

  return { value: items, count: items.length };
});
