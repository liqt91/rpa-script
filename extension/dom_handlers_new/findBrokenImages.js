/**
 * findBrokenImages — 检测页面上加载失败的图片。
 * naturalWidth===0（未能解码尺寸）或 complete===false（尚未加载完成）判为失败。
 * 返回 { src, alt, naturalWidth }；同时以 value / extracted / items 三个键暴露。
 */
registerHandler('findBrokenImages', async function findBrokenImages({ locator, selectorFamily, extra }) {
    const deduplicate = extra?.deduplicate === true || extra?.deduplicate === 'true' ||
        (extra?.deduplicate !== false && extra?.deduplicate !== 'false');

    const seen = new Set();
    const broken = [];
    for (const img of document.querySelectorAll('img')) {
        const srcAttr = img.getAttribute('src');
        const src = srcAttr || (typeof img.currentSrc === 'string' && img.currentSrc) || '';
        if (!src) continue;

        const failed = img.naturalWidth === 0 || img.complete === false;
        if (!failed) continue;

        if (deduplicate) {
            if (seen.has(src)) continue;
            seen.add(src);
        }
        broken.push({ src, alt: (img.alt || '').trim(), naturalWidth: img.naturalWidth || 0 });
    }

    return {
        value: broken,
        extracted: broken,
        items: broken,
        count: broken.length,
        matchedCount: broken.length,
    };
});
