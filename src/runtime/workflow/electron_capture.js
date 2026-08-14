/* Electron 元素捕获注入脚本 — 通过 CDP Runtime.evaluate 注入到目标页面。

监听 Alt+Click：高亮目标 → 生成选择器（CSS 优先，XPath 兜底）写入
window.__rpaCaptureResult；Alt+Esc 取消写入 window.__rpaCaptureCancelled。
外部通过轮询这两个全局变量获取结果。
*/
(() => {
  if (window.__rpaCaptureInstalled) return { installed: true };
  window.__rpaCaptureInstalled = true;
  window.__rpaCaptureResult = null;
  window.__rpaCaptureCancelled = false;

  // 高亮框
  const hl = document.createElement('div');
  hl.style.cssText = 'position:fixed;z-index:2147483647;pointer-events:none;'
    + 'border:2px solid #ff4d4f;background:rgba(255,77,79,0.08);'
    + 'border-radius:2px;display:none;';
  document.documentElement.appendChild(hl);

  let current = null;
  function highlight(el) {
    if (!el || el === document || el === document.body) { hl.style.display = 'none'; return; }
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) { hl.style.display = 'none'; return; }
    hl.style.display = 'block';
    hl.style.left = r.left + 'px';
    hl.style.top = r.top + 'px';
    hl.style.width = r.width + 'px';
    hl.style.height = r.height + 'px';
  }

  // CSS 选择器生成：优先 id → 类路径 → 标签路径；过长退 XPath
  function cssSelector(el) {
    const parts = [];
    let node = el;
    while (node && node !== document.body && parts.length < 8) {
      if (node.id) {
        parts.unshift('#' + CSS.escape(node.id));
        break;
      }
      let sel = node.tagName.toLowerCase();
      const cls = (typeof node.className === 'string' ? node.className : '')
        .split(/\s+/).filter(Boolean).slice(0, 2);
      if (cls.length) sel += '.' + cls.map(c => CSS.escape(c)).join('.');
      const parent = node.parentElement;
      if (parent) {
        const same = [...parent.children].filter(c => c.tagName === node.tagName
          && ((typeof c.className === 'string' ? c.className : '') === (typeof node.className === 'string' ? node.className : '')));
        if (same.length > 1) sel += ':nth-of-type(' + ([...parent.children].indexOf(node) + 1) + ')';
      }
      parts.unshift(sel);
      node = parent;
    }
    const s = parts.join(' > ');
    return s.length <= 160 ? s : null;
  }

  function xpathSelector(el) {
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && parts.length < 10) {
      let idx = 1;
      let sib = node.previousElementSibling;
      while (sib) { if (sib.tagName === node.tagName) idx++; sib = sib.previousElementSibling; }
      parts.unshift(node.tagName.toLowerCase() + '[' + idx + ']');
      node = node.parentElement;
    }
    return 'xpath://' + parts.join('/');
  }

  function genSelector(el) {
    const css = cssSelector(el);
    return css || xpathSelector(el);
  }

  // 高亮跟随
  document.addEventListener('mousemove', e => {
    if (window.__rpaCaptureResult || window.__rpaCaptureCancelled) return;
    current = e.target;
    highlight(e.target);
  }, true);

  // Alt+Click 确认
  document.addEventListener('click', e => {
    if (!e.altKey) return;
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    const el = e.target;
    hl.style.display = 'none';
    window.__rpaCaptureResult = {
      selector: genSelector(el),
      tag: el.tagName,
      text: (el.innerText || '').trim().slice(0, 60),
      cls: (typeof el.className === 'string' ? el.className : '').slice(0, 80),
    };
  }, true);

  // Alt+Esc 取消
  document.addEventListener('keydown', e => {
    if (e.altKey && e.key === 'Escape') {
      e.preventDefault();
      window.__rpaCaptureCancelled = true;
      hl.style.display = 'none';
    }
  }, true);

  return { installed: true };
})()
