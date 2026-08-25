/**
 * getPageInfo — 获取页面元信息。
 * 返回 { title, url, lang, description, keywords, ogTitle }（单对象）；
 * 同时以 value / extracted 暴露，便于「保存到变量」。
 */
registerHandler('getPageInfo', async function getPageInfo({ locator, selectorFamily, extra }) {
    const includeMeta = extra?.includeMeta === true || extra?.includeMeta === 'true' ||
        (extra?.includeMeta !== false && extra?.includeMeta !== 'false');

    const meta = {};
    if (includeMeta) {
        for (const m of document.querySelectorAll('meta')) {
            const key = m.getAttribute('name') || m.getAttribute('property') || '';
            const content = m.getAttribute('content') || '';
            if (key && content) meta[key] = content;
        }
    }

    const info = {
        title: (document.title || '').trim(),
        url: (typeof document.URL === 'string' && document.URL) ? document.URL
            : (window.location && window.location.href) || '',
        lang: (document.documentElement && document.documentElement.lang) || '',
        description: meta.description || '',
        keywords: meta.keywords || '',
        ogTitle: meta['og:title'] || '',
    };

    return {
        value: info,
        extracted: info,
        items: info,
        count: 1,
        matchedCount: 1,
    };
});
