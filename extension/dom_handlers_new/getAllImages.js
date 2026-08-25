/**
 * getAllImages — 获取页面上所有图片的链接地址。
 *
 * 扫描页面全部 <img>（含懒加载 data-src 类属性、srcset 多尺寸候选），可选纳入
 * CSS background-image。可仅保留可见图片、按地址去重。
 * 返回 { src, alt, source, naturalWidth, naturalHeight, width, height } 对象数组；
 * 同时以 value / extracted / items 三个键暴露同一份数组，便于「保存到变量」
 * 与 forEachElement 循环复用。
 */
registerHandler('getAllImages', async function getAllImages({ locator, selectorFamily, extra }) {
    const onlyVisible = extra?.onlyVisible === true || extra?.onlyVisible === 'true';
    const deduplicate = extra?.deduplicate === true || extra?.deduplicate === 'true' ||
        (extra?.deduplicate !== false && extra?.deduplicate !== 'false');
    const includeSrcset = extra?.includeSrcset === true || extra?.includeSrcset === 'true' ||
        (extra?.includeSrcset !== false && extra?.includeSrcset !== 'false');
    const includeCssBackground = extra?.includeCssBackground === true || extra?.includeCssBackground === 'true';

    const results = [];
    const seen = new Set();

    // 解析为绝对地址（对 // 协议相对、./ 相对、# 锚点都能正确展开）
    function resolve(url) {
        if (!url) return '';
        const raw = String(url).trim();
        if (!raw) return '';
        try {
            return new URL(raw, document.baseURI).href;
        } catch (err) {
            return raw;
        }
    }

    function push(url, info = {}) {
        const absolute = resolve(url);
        if (!absolute) return;
        if (absolute === 'javascript:' || absolute === 'about:blank') return;
        if (deduplicate) {
            if (seen.has(absolute)) return;
            seen.add(absolute);
        }
        results.push({ src: absolute, ...info });
    }

    // ---- <img> 元素 ----
    const imgs = Array.from(document.querySelectorAll('img'));
    for (const img of imgs) {
        if (onlyVisible && !checkVisibility(img, 'visible')) continue;

        const alt = (img.alt || '').trim();
        const info = {
            alt,
            naturalWidth: img.naturalWidth || 0,
            naturalHeight: img.naturalHeight || 0,
            width: img.width || 0,
            height: img.height || 0,
        };

        // 当前实际使用的地址：解析后的 img.src 已是绝对地址，currentSrc 仅在有 srcset 时更精确
        const srcAttr = img.getAttribute('src');
        const src = (typeof img.src === 'string' && img.src) ? img.src
                  : (typeof img.currentSrc === 'string' && img.currentSrc) ? img.currentSrc
                  : (srcAttr || '');
        if (src) push(src, { ...info, source: 'img-src' });

        // 懒加载 / 常用框架的 data-* 地址
        for (const attr of ['data-src', 'data-original', 'data-lazy-src', 'data-url']) {
            const v = img.getAttribute(attr);
            if (v) push(v, { ...info, source: 'img-' + attr });
        }

        // srcset 多尺寸候选
        if (includeSrcset) {
            const srcset = img.getAttribute('srcset') || img.getAttribute('data-srcset');
            if (srcset) {
                for (const part of srcset.split(',')) {
                    const url = part.trim().split(/\s+/)[0];
                    if (url) push(url, { ...info, source: 'srcset' });
                }
            }
        }
    }

    // ---- CSS background-image（可选，默认关闭避免大页面遍历开销） ----
    if (includeCssBackground) {
        const all = document.querySelectorAll('*');
        for (let i = 0; i < all.length; i++) {
            let bg = '';
            try {
                bg = getComputedStyle(all[i]).backgroundImage;
            } catch (err) {
                continue;
            }
            if (!bg || bg === 'none') continue;
            const matches = bg.match(/url\((['"]?)([^'")]+)\1\)/g);
            if (!matches) continue;
            for (const m of matches) {
                const url = m.replace(/^url\(\s*['"]?/, '').replace(/['"]?\s*\)$/, '');
                if (url) push(url, { alt: '', source: 'css-background' });
            }
        }
    }

    return {
        value: results,
        extracted: results,
        items: results,
        count: results.length,
        matchedCount: results.length,
    };
});
