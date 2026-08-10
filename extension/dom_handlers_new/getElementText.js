// ─── getElementText ─────────────────────────────────────────────
// 后端 ifTextEquals / ifTextContains 的查询入口。返回 {text}；
// 元素未命中时返回空串（不抛错）。

registerHandler('getElementText', async function getElementTextHandler({ locator, selectorFamily, extra }) {
    if (!locator) return { text: '' };
    const mode = getVisibilityMode(extra);
    let el = null;
    try {
        if (extra?.contextLocator || extra?.sourceLocator) {
            el = reResolveWithContext(locator, selectorFamily, extra, mode);
        } else {
            el = resolveLocator(locator, selectorFamily, mode);
        }
    } catch (e) {
        if (e && e.contextNotFound) return { text: '' };
        throw e;
    }
    if (!el || el === document) return { text: '' };
    const text = (el.innerText || el.textContent || '').trim();
    return { text };
});
