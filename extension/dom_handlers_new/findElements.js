// ─── findElements ───────────────────────────────────────────────
// 后端 forEachElement 的查询入口。返回 {items, matchedCount}。
// item 只携带 text——循环项锚定由后端按「循环选择器 + 序号对齐」注入
// （每步实时重解析，对动态页面的 DOM 重渲染更稳健；冻结 xpath 会迅速过期）。

registerHandler('findElements', async function findElementsHandler({ locator, selectorFamily, extra }) {
    if (!locator) return { items: [], matchedCount: 0 };
    const mode = getVisibilityMode(extra);

    let matches = [];
    const ctxLocator = extra?.contextLocator;
    const ctxLocatorType = extra?.contextLocatorType;
    const ctxIndex = extra?.contextIndex ?? 0;

    if (ctxLocator) {
        // 嵌套循环：先解析外层循环项，再在其内部查找本轮元素。
        const parents = resolveAllLocators(ctxLocator, ctxLocatorType);
        const parent = parents[ctxIndex];
        if (!parent) return { items: [], matchedCount: 0 };
        if (extra?.useRelative && extra?.relativeLocator) {
            matches = resolveAllRelativeInContext(
                extra.relativeLocator, extra.relativeSelectorFamily, parent);
        } else {
            matches = resolveAllLocatorsInContext(locator, selectorFamily, parent);
        }
    } else {
        matches = resolveAllLocators(locator, selectorFamily);
    }

    if (mode !== 'any') {
        matches = matches.filter(e => checkVisibility(e, mode));
    }

    const items = matches.map(el => ({
        text: (el.innerText || el.textContent || '').trim().slice(0, 500),
    }));
    return { items, matchedCount: items.length };
});
