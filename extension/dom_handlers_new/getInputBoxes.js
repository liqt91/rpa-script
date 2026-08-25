/**
 * getInputBoxes — 获取网页上所有输入框清单。
 * 扫描 input/textarea，返回 { tag, name, id, type, value, placeholder, label }；
 * 同时以 value / extracted / items 三个键暴露同一份数组，便于「保存到变量」与 forEachElement 循环复用。
 */
registerHandler('getInputBoxes', async function getInputBoxes({ locator, selectorFamily, extra }) {
    const includeTextarea = extra?.includeTextarea === true || extra?.includeTextarea === 'true' ||
        (extra?.includeTextarea !== false && extra?.includeTextarea !== 'false');
    const includeHidden = extra?.includeHidden === true || extra?.includeHidden === 'true';

    // 限定在可选的外层元素内扫描（若提供了元素选择器）
    let root = document;
    if (locator) {
        try {
            let base = null;
            if (selectorFamily === 'xpath') {
                base = document.evaluate(locator, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            } else {
                base = document.querySelector(locator);
            }
            if (base) root = base;
        } catch (err) {
            // 忽略定位失败，回退到全页面
        }
    }

    const inputs = [];

    function resolveLabel(el) {
        // 关联 label：优先 label[for=id]，其次祖先 label
        const id = el.getAttribute('id') || '';
        if (id) {
            for (const lab of document.querySelectorAll('label')) {
                if (lab.getAttribute('for') === id) {
                    return (lab.innerText || lab.textContent || '').trim();
                }
            }
        }
        let p = el.parentElement;
        while (p) {
            if (p.tagName && p.tagName.toLowerCase() === 'label') {
                return (p.innerText || p.textContent || '').trim();
            }
            p = p.parentElement;
        }
        return '';
    }

    // 输入类 type 集合；type 非文本类的也会被收集（readonly/disabled 等由调用方判断）
    for (const el of root.querySelectorAll('input, textarea')) {
        const tag = el.tagName.toLowerCase();
        if (el.type === 'hidden' && !includeHidden) continue;
        if (tag === 'textarea' && !includeTextarea) continue;

        const id = el.getAttribute('id') || '';
        const name = el.getAttribute('name') || '';

        inputs.push({
            tag,
            name,
            id,
            type: (el.type || tag),
            value: (typeof el.value === 'string' ? el.value : ''),
            placeholder: el.getAttribute('placeholder') || '',
            label: resolveLabel(el),
        });
    }

    return {
        value: inputs,
        extracted: inputs,
        items: inputs,
        count: inputs.length,
        matchedCount: inputs.length,
    };
});
