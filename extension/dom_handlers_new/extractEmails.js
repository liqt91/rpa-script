/**
 * extractEmails — 提取页面上的邮箱地址。
 * 来源：a[href^=mailto] 链接、链接文本、以及整页正文文本；可选自定义正则。
 * 返回 { email, source }（source ∈ mailto|text）；同时以 value / extracted / items 三个键暴露。
 */
registerHandler('extractEmails', async function extractEmails({ locator, selectorFamily, extra }) {
    const pattern = (extra?.pattern || '').trim();
    const deduplicate = extra?.deduplicate === true || extra?.deduplicate === 'true' ||
        (extra?.deduplicate !== false && extra?.deduplicate !== 'false');

    let regex;
    if (pattern) {
        try {
            regex = new RegExp(pattern, 'g');
        } catch (err) {
            return { value: [], extracted: [], items: [], count: 0, matchedCount: 0, error: `无效正则: ${err.message}` };
        }
    } else {
        // 内置邮箱正则（宽松匹配，去首尾标签括号与常见后缀标点）
        regex = /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/g;
    }

    const seen = new Set();
    const emails = [];
    const add = (raw, source) => {
        const e = String(raw || '').trim()
            .replace(/^[<\[(]+|[>\])\).,;:]+$/g, '');
        if (!e) return;
        if (deduplicate) {
            if (seen.has(e)) return;
            seen.add(e);
        }
        emails.push({ email: e, source });
    };

    // 1) mailto 链接
    for (const a of document.querySelectorAll('a[href]')) {
        const href = a.getAttribute('href') || '';
        if (/^mailto:/i.test(href)) {
            add(href.replace(/^mailto:/i, '').split(/[?&]/)[0], 'mailto');
        }
    }

    // 2) 链接文本
    for (const a of document.querySelectorAll('a[href]')) {
        const t = (a.innerText || a.textContent || '');
        for (const m of t.match(regex) || []) add(m, 'text');
    }

    // 3) 正文文本
    const bodyText = (document.body && (document.body.innerText || document.body.textContent)) || '';
    for (const m of bodyText.match(regex) || []) add(m, 'text');

    return {
        value: emails,
        extracted: emails,
        items: emails,
        count: emails.length,
        matchedCount: emails.length,
    };
});
