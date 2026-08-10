// ─── checkElementVisible ────────────────────────────────────────
// 后端 ifElementVisible 的查询入口。返回 {visible}。

registerHandler('checkElementVisible', async function checkElementVisibleHandler({ locator, selectorFamily, extra }) {
    if (!locator) return { visible: false };
    const mode = getVisibilityMode(extra);
    let el = null;
    try {
        if (extra?.contextLocator || extra?.sourceLocator) {
            el = reResolveWithContext(locator, selectorFamily, extra, mode);
        } else {
            el = resolveLocator(locator, selectorFamily, mode);
        }
    } catch (e) {
        if (e && e.contextNotFound) return { visible: false };
        throw e;
    }
    const visible = !!el && el !== document && checkVisibility(el, mode);
    return { visible };
});
