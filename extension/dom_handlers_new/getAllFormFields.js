/**
 * getAllFormFields — 获取页面上所有表单控件清单。
 * 扫描 input/textarea/select，返回 { tag, name, type, value, placeholder, label, id }；
 * 同时以 value / extracted / items 三个键暴露同一份数组，便于「保存到变量」与 forEachElement 循环。
 */
registerHandler('getAllFormFields', async function getAllFormFields({ locator, selectorFamily, extra }) {
    const includeHidden = extra?.includeHidden === true || extra?.includeHidden === 'true';
    const includeSelect = extra?.includeSelect === true || extra?.includeSelect === 'true' ||
        (extra?.includeSelect !== false && extra?.includeSelect !== 'false');

    const fields = [];
    for (const el of document.querySelectorAll('input, textarea, select')) {
        const tag = el.tagName.toLowerCase();
        if (el.type === 'hidden' && !includeHidden) continue;
        if (tag === 'select' && !includeSelect) continue;

        // 关联 label：优先 label[for=id]，其次祖先 label
        let label = '';
        const id = el.getAttribute('id') || '';
        if (id) {
            for (const lab of document.querySelectorAll('label') || []) {
                if (lab.getAttribute('for') === id) {
                    label = (lab.innerText || lab.textContent || '').trim();
                    break;
                }
            }
        }
        if (!label) {
            let p = el.parentElement;
            while (p) {
                if (p.tagName && p.tagName.toLowerCase() === 'label') {
                    label = (p.innerText || p.textContent || '').trim();
                    break;
                }
                p = p.parentElement;
            }
        }

        fields.push({
            tag,
            name: el.getAttribute('name') || '',
            type: (el.type || (tag === 'select' ? 'select' : tag)),
            value: (typeof el.value === 'string' ? el.value : ''),
            placeholder: el.getAttribute('placeholder') || '',
            label,
            id,
        });
    }

    return {
        value: fields,
        extracted: fields,
        items: fields,
        count: fields.length,
        matchedCount: fields.length,
    };
});
