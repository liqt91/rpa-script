/**
 * getLinksByRegex — 获取页面上所有匹配正则表达式的链接。
 *
 * 扫描页面全部带 href 的锚点，按给定正则过滤（可匹配链接地址 href /
 * 链接文本 / 两者任一），可选仅保留可见链接、按地址去重。
 * 返回 { href, text } 对象数组；同时以 extracted / value / items 三个键
 * 暴露同一份数组，便于「保存到变量」与 forEachElement 循环复用。
 */
registerHandler('getLinksByRegex', async function getLinksByRegex({ locator, selectorFamily, extra }) {
    const pattern = (extra?.pattern ?? '').trim();
    const matchField = extra?.matchField ?? 'href';
    const onlyVisible = extra?.onlyVisible === true || extra?.onlyVisible === 'true';
    const deduplicate = extra?.deduplicate === true || extra?.deduplicate === 'true' ||
        (extra?.deduplicate !== false && extra?.deduplicate !== 'false');

    let regex = null;
    if (pattern) {
        try {
            regex = new RegExp(pattern);
        } catch (err) {
            return {
                value: [], extracted: [], items: [], count: 0, matchedCount: 0,
                error: `无效正则表达式: ${err.message}`,
            };
        }
    }

    const anchors = Array.from(document.querySelectorAll('a[href], [href]'));
    const seen = new Set();
    const links = [];

    for (const el of anchors) {
        const rawHref = (el.getAttribute('href') || '').trim();
        // el.href 是解析后的绝对 URL（对 // 协议相对、./ 相对、# 锚点都能正确展开）
        const href = (typeof el.href === 'string' && el.href) ? el.href : rawHref;
        const text = (el.innerText || el.textContent || '').trim();

        if (!href && !text) continue;

        if (onlyVisible && !checkVisibility(el, 'visible')) continue;

        let matched = true;
        if (regex) {
            if (matchField === 'href') {
                matched = regex.test(href) || regex.test(rawHref);
            } else if (matchField === 'text') {
                matched = regex.test(text);
            } else {
                matched = regex.test(href) || regex.test(rawHref) || regex.test(text);
            }
        }

        if (!matched) continue;

        if (deduplicate) {
            if (seen.has(href)) continue;
            seen.add(href);
        }

        links.push({ href, text });
    }

    return {
        value: links,
        extracted: links,
        items: links,
        count: links.length,
        matchedCount: links.length,
    };
});
