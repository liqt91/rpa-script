// ─── checkElementExists ─────────────────────────────────────────
// 后端 ifElementExists / whileCondition(elementExists) 的查询入口。
// 返回 {exists}；元素不存在是正常结果（不抛错），连接/解析失败才抛错。

registerHandler('checkElementExists', async function checkElementExistsHandler({ locator, selectorFamily, extra }) {
    if (!locator) return { exists: false };
    const mode = getVisibilityMode(extra);
    let el = null;
    try {
        if (extra?.contextLocator || extra?.sourceLocator) {
            el = reResolveWithContext(locator, selectorFamily, extra, mode);
        } else {
            el = resolveLocator(locator, selectorFamily, mode);
        }
    } catch (e) {
        // 循环项内未找到 = 不存在，不是错误
        if (e && e.contextNotFound) return { exists: false };
        throw e;
    }
    const exists = !!el && el !== document && checkVisibility(el, mode);
    return { exists };
});
