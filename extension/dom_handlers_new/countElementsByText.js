/**
 * countElementsByText — 统计页面上（或指定元素范围内）文本匹配指定内容的元素数量。
 *
 * 三种匹配方式：
 *   - contains: 元素文本包含指定子串（大小写敏感）
 *   - equals  : 元素文本去掉首尾空白后与指定文本完全相同
 *   - regex   : 元素文本匹配指定正则表达式（字符串构造，无 global 状态）
 *
 * 统计范围：
 *   - locator 为空 → 全页面（遍历 body 内所有元素，不含 body/html 本身）
 *   - locator 非空 → 在该已捕获元素内部的子孙元素中统计（不含范围元素本身）
 *
 * 返回 { value, extracted, count, matchedCount, items }，其中 count 即数量，
 * 由 extension_runner 写入 resultVar（value/extracted 均置为 count）。
 */
registerHandler('countElementsByText', async function countElementsByText({ locator, selectorFamily, extra }) {
  const needle = (extra?.text ?? '').trim();
  const matchType = extra?.matchType ?? 'contains';
  const onlyVisible = extra?.onlyVisible === true || extra?.onlyVisible === 'true';
  const mode = onlyVisible ? 'visible' : 'any';

  if (!needle) {
    return { value: 0, extracted: 0, count: 0, matchedCount: 0, items: [] };
  }

  let regex = null;
  if (matchType === 'regex') {
    try {
      regex = new RegExp(needle);
    } catch (e) {
      return {
        value: 0, extracted: 0, count: 0, matchedCount: 0, items: [],
        error: `无效正则表达式: ${e.message}`,
      };
    }
  }

  // 确定统计范围：locator 非空 → 在范围内元素的子孙元素中统计；否则全页面。
  let candidates = [];
  if (locator) {
    let root = null;
    try {
      root = findTarget(locator, selectorFamily, extra);
    } catch (e) {
      // 范围内的元素不存在 → 数量为 0（正常结果，不抛错）
      return { value: 0, extracted: 0, count: 0, matchedCount: 0, items: [] };
    }
    if (root && root.querySelectorAll) {
      candidates = Array.from(root.querySelectorAll('*'));
    }
  } else {
    const body = document.body || document.documentElement;
    if (body && body.querySelectorAll) {
      candidates = Array.from(body.querySelectorAll('*'));
    }
  }

  const matched = [];
  for (const el of candidates) {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) continue;
    const elText = (el.innerText || el.textContent || '').trim();
    if (!elText) continue;

    let hit = false;
    if (matchType === 'equals') {
      hit = elText === needle;
    } else if (matchType === 'regex') {
      regex.lastIndex = 0;
      hit = regex.test(elText);
    } else {
      hit = elText.includes(needle);
    }
    if (!hit) continue;
    if (mode === 'visible' && !checkVisibility(el, 'visible')) continue;

    matched.push(el);
  }

  const items = matched.map(el => ({
    text: (el.innerText || el.textContent || '').trim().slice(0, 500),
  }));
  const count = matched.length;

  return {
    value: count,
    extracted: count,
    count,
    matchedCount: count,
    searchText: needle,
    items,
  };
});
