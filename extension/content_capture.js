/**
 * RPA Script Browser Agent — Element Capture Mode
 *
 * Alt+click to capture elements with auto-generated locators.
 * Sends captured elements to backend via WebSocket (through background.js).
 */

(function () {
  'use strict';
  if (window.__rpaCaptureInjected) return;
  window.__rpaCaptureInjected = true;

  // ─── State ───────────────────────────────────────────────────────
  let captureMode = false;
  let lastHoveredEl = null;
  let lockedElement = null;
  let lockedCandidates = [];
  let lockedLocator = '';
  let lockedLocatorType = '';
  let highlightHost = null;
  let highlightCanvas = null;
  let highlightCtx = null;
  let capturedScreenshot = null;
  let altPressed = false;
  let altComboUsed = false;

  // ─── Helpers: stability scoring ──────────────────────────────────

  function isStableId(id) {
    if (!id || id.length > 50) return false;
    if (/^:[Rr][a-z0-9]*:$/.test(id)) return false;
    if (/^css-[a-z0-9]{4,}$/i.test(id)) return false;
    if (/^(mui|chakra|ant|ember|ng|vue|svelte)[-_][a-z0-9]{4,}/i.test(id)) return false;
    if (/^[a-f0-9]{10,}$/i.test(id)) return false;
    const hashSegs = (id.match(/_[a-f0-9]{6,}/g) || []).length;
    if (hashSegs >= 2) return false;
    return /^[a-zA-Z][a-zA-Z0-9_\-:]*$/.test(id);
  }

  function isStableClass(cls) {
    if (!cls || cls.length < 2) return false;
    if (/^orch-/i.test(cls)) return false;
    if (/_{2,}[a-z0-9]{4,}/i.test(cls)) return false;
    if (/^css-[a-z0-9]{4,}$/i.test(cls)) return false;
    if (/^_[a-f0-9]{6,}$/i.test(cls)) return false;
    return true;
  }

  function getDirectText(el) {
    let t = '';
    for (const node of el.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) t += node.textContent;
    }
    return t.trim().replace(/\s+/g, ' ');
  }

  function buildFeatureSnapshot(element) {
    if (!element || element.nodeType !== Node.ELEMENT_NODE) return {};
    const EXCLUDE = [/^data-v-[a-f0-9]+$/i, /^data-react/i, /^v-/i, /^_ng/i, /^style$/i, /^class$/i, /^id$/i];
    const attrs = {};
    try {
      for (const attr of element.attributes) {
        if (EXCLUDE.some(p => p.test(attr.name))) continue;
        attrs[attr.name] = attr.value?.length > 200 ? attr.value.slice(0, 200) + '…' : attr.value;
      }
    } catch (e) {}
    let innerText = '';
    try { innerText = (element.innerText || '').trim().slice(0, 200); } catch (e) {}
    return {
      tag: element.tagName.toLowerCase(),
      id: element.id || '',
      classes: element.classList ? Array.from(element.classList).filter(c => !/^orch-/i.test(c)) : [],
      attrs,
      direct_text: getDirectText(element),
      inner_text: innerText,
    };
  }

  function attrValNeedsCssFallback(v) {
    return /[@'"\n\r\t]/.test(v) || v.includes('=');
  }

  function escapeAttrVal(v) {
    return v.replace(/\n/g, ' ').trim();
  }

  function cssEscape(v) {
    return v.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  }

  function getOldCssSelector(element) {
    if (!element || element === document.body) return 'body';
    if (element.id && /^[a-zA-Z][a-zA-Z0-9_-]*$/.test(element.id)) return '#' + element.id;
    const dataAttrs = ['data-testid', 'data-id', 'data-key', 'data-name', 'data-e2e'];
    for (const attr of dataAttrs) {
      const val = element.getAttribute(attr);
      if (val) return `[${attr}="${val}"]`;
    }
    if (element.classList && element.classList.length > 0) {
      const classes = Array.from(element.classList)
        .filter(c => c.length > 2 && !c.includes('_') && !/^orch-/i.test(c))
        .slice(0, 2);
      if (classes.length > 0) return '.' + classes.join('.');
    }
    const parent = element.parentElement;
    if (parent) {
      const siblings = Array.from(parent.children).filter(c => c.tagName === element.tagName);
      const idx = siblings.indexOf(element) + 1;
      const tag = element.tagName.toLowerCase();
      return siblings.length === 1 ? tag : `${tag}:nth-child(${idx})`;
    }
    return element.tagName.toLowerCase();
  }

  function getElementXPath(element) {
    if (!element || element === document.body) return '/html/body';
    const segs = [];
    let el = element;
    while (el && el.nodeType === Node.ELEMENT_NODE && el !== document.body) {
      const parent = el.parentElement;
      if (!parent) break;
      const sameTag = Array.from(parent.children).filter(c => c.tagName === el.tagName);
      const idx = sameTag.indexOf(el) + 1;
      const tag = el.tagName.toLowerCase();
      segs.unshift(sameTag.length === 1 ? tag : `${tag}[${idx}]`);
      el = parent;
      if (segs.length > 6) break;
    }
    return '//body/' + segs.join('/');
  }

  function convertToCssForTest(syntax, type) {
    try {
      switch (type) {
        case 'id': return syntax;
        case 'class': return syntax;
        case 'data-attr':
        case 'aria':
        case 'name': {
          const m = syntax.match(/^@([\w\-:]+)=(.+)$/);
          if (!m) return null;
          return `[${m[1]}="${cssEscape(m[2])}"]`;
        }
        case 'tag_text': {
          const m = syntax.match(/^tag:(\w+)@text\(\)=(.+)$/);
          if (!m) return null;
          return `${m[1]}:contains("${cssEscape(m[2])}")`;
        }
        case 'text': {
          const m = syntax.match(/^text=(.+)$/);
          if (!m) return null;
          return `*:contains("${cssEscape(m[1])}")`;
        }
        case 'tag_attr': {
          const m = syntax.match(/^tag:(\w+)@(\w+)=(.+)$/);
          if (!m) return null;
          return `${m[1]}[${m[2]}="${cssEscape(m[3])}"]`;
        }
        case 'tag_class': {
          const m = syntax.match(/^tag:(\w+)@class=(.+)$/);
          if (!m) return null;
          return `${m[1]}.${m[2]}`;
        }
        case 'multi_attr': {
          const parts = syntax.match(/@@class:([^@]+)/g);
          if (!parts) return null;
          return parts.map(p => '.' + p.replace('@@class:', '')).join('');
        }
        case 'css': return syntax.replace(/^css:/, '');
        case 'xpath': return null;
        default: return syntax;
      }
    } catch (e) { return null; }
  }

  function verifyLocator(syntax, type) {
    if (type === 'xpath') {
      const xp = syntax.replace(/^xpath:/, '');
      try {
        const r = document.evaluate(xp, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        return r.snapshotLength;
      } catch (e) { return -1; }
    }
    const css = convertToCssForTest(syntax, type);
    if (!css) return -1;
    try { return document.querySelectorAll(css).length; } catch (e) { return -1; }
  }

  function getSimpleAncestorSelector(el) {
    if (!el || el === document.body) return null;
    if (el.id && isStableId(el.id)) return '#' + el.id;
    const dataAttrs = ['data-testid', 'data-test', 'data-id', 'data-name', 'data-key', 'data-e2e'];
    for (const a of dataAttrs) {
      const v = el.getAttribute(a);
      if (v && v.length < 80 && !attrValNeedsCssFallback(v)) {
        return `[${a}="${cssEscape(v)}"]`;
      }
    }
    const tag = el.tagName.toLowerCase();
    if (['header', 'main', 'footer', 'nav', 'aside', 'article', 'section'].includes(tag)) return tag;
    if (el.classList) {
      const stable = Array.from(el.classList).filter(isStableClass);
      if (stable.length > 0) return '.' + stable[0];
    }
    return null;
  }

  function buildStructuralCss(element) {
    if (!element || element === document.body) return null;
    const segs = [];
    let cur = element;
    while (cur && cur !== document.body && segs.length < 8) {
      const parent = cur.parentElement;
      if (!parent) break;
      const tag = cur.tagName.toLowerCase();
      const sameTagSiblings = Array.from(parent.children).filter(c => c.tagName === cur.tagName);
      const myIdx = sameTagSiblings.indexOf(cur) + 1;
      const stableClasses = cur.classList ? Array.from(cur.classList).filter(isStableClass) : [];
      let seg;
      if (cur.id && isStableId(cur.id)) {
        seg = '#' + cur.id;
      } else if (stableClasses.length > 0) {
        seg = sameTagSiblings.length === 1
          ? `${tag}.${stableClasses[0]}`
          : `${tag}.${stableClasses[0]}:nth-of-type(${myIdx})`;
      } else {
        seg = sameTagSiblings.length === 1 ? tag : `${tag}:nth-of-type(${myIdx})`;
      }
      segs.unshift(seg);
      const trial = segs.join(' > ');
      try { if (document.querySelectorAll(trial).length === 1) return trial; } catch (e) {}
      if (seg.startsWith('#')) break;
      cur = parent;
    }
    return segs.length ? segs.join(' > ') : null;
  }

  function getElementCssPath(element) {
    if (!element || element === document.body) return 'body';
    const segs = [];
    let cur = element;
    while (cur && cur !== document.body && segs.length < 10) {
      const parent = cur.parentElement;
      if (!parent) break;
      const tag = cur.tagName.toLowerCase();
      const sameTag = Array.from(parent.children).filter(c => c.tagName === cur.tagName);
      const idx = sameTag.indexOf(cur) + 1;
      const stableClasses = cur.classList ? Array.from(cur.classList).filter(isStableClass) : [];
      let seg;
      if (cur.id && isStableId(cur.id)) {
        seg = '#' + cur.id;
      } else if (stableClasses.length > 0) {
        seg = `${tag}.${stableClasses[0]}:nth-of-type(${idx})`;
      } else {
        seg = `${tag}:nth-of-type(${idx})`;
      }
      segs.unshift(seg);
      if (seg.startsWith('#')) break;
      cur = parent;
    }
    return segs.join(' > ');
  }

  function generateLocators(element) {
    if (!element || element === document.body) {
      return [{ syntax: 'tag:body', label: 'body', type: 'tag', score: 10, matchCount: 1 }];
    }
    const tag = element.tagName.toLowerCase();
    const candidates = [];

    // 1. id
    const id = element.id;
    if (id) {
      const stable = isStableId(id);
      candidates.push({ syntax: '#' + id, label: 'id: ' + id, type: 'id', score: stable ? 100 : 35 });
    }

    // 2. data-*
    const dataAttrs = ['data-testid', 'data-test', 'data-test-id', 'data-cy', 'data-qa', 'data-e2e', 'data-id', 'data-key', 'data-name'];
    for (const attr of dataAttrs) {
      const v = element.getAttribute(attr);
      if (!v || v.length > 80) continue;
      if (attrValNeedsCssFallback(v)) {
        candidates.push({ syntax: `css:[${attr}="${cssEscape(v)}"]`, label: `${attr}=${v} (css)`, type: 'css', score: 92 });
      } else {
        candidates.push({ syntax: `@${attr}=${escapeAttrVal(v)}`, label: `${attr}=${v}`, type: 'data-attr', score: 95 });
      }
    }

    // 3. semantic attrs
    const semanticAttrs = [
      { name: 'aria-label', score: 88, type: 'aria' },
      { name: 'name', score: 85, type: 'name' },
      { name: 'role', score: 60, type: 'aria' },
      { name: 'placeholder', score: 65, type: 'aria' },
      { name: 'title', score: 60, type: 'aria' },
    ];
    for (const { name, score, type } of semanticAttrs) {
      const v = element.getAttribute(name);
      if (!v || v.length > 80) continue;
      if (attrValNeedsCssFallback(v)) {
        candidates.push({ syntax: `css:[${name}="${cssEscape(v)}"]`, label: `${name}=${v} (css)`, type: 'css', score: score - 5 });
      } else {
        candidates.push({ syntax: `@${name}=${escapeAttrVal(v)}`, label: `${name}=${v}`, type, score });
      }
    }

    // 4. direct text
    const directText = getDirectText(element);
    if (directText && directText.length > 0 && directText.length < 30 && !/['"]/.test(directText)) {
      candidates.push({ syntax: `tag:${tag}@text()=${directText}`, label: `${tag} + 文本: "${directText}"`, type: 'tag_text', score: 82 });
      candidates.push({ syntax: `text=${directText}`, label: `text: "${directText}"`, type: 'text', score: 75 });
    }

    // 5. type attr
    if (tag === 'input' || tag === 'button') {
      const typeAttr = element.getAttribute('type');
      if (typeAttr) {
        candidates.push({ syntax: `tag:${tag}@type=${typeAttr}`, label: `${tag}[type=${typeAttr}]`, type: 'tag_attr', score: 50 });
      }
    }

    // 6. class
    if (element.classList && element.classList.length > 0) {
      const stableClasses = Array.from(element.classList).filter(isStableClass);
      if (stableClasses.length === 1) {
        const c = stableClasses[0];
        candidates.push({ syntax: '.' + c, label: 'class: .' + c, type: 'class', score: 65 });
        candidates.push({ syntax: `tag:${tag}@class=${c}`, label: `${tag}.${c}`, type: 'tag_class', score: 70 });
      } else if (stableClasses.length >= 2) {
        const top2 = stableClasses.slice(0, 2);
        candidates.push({ syntax: `@@class:${top2[0]}@@class:${top2[1]}`, label: `class 包含: ${top2[0]} & ${top2[1]}`, type: 'multi_attr', score: 72 });
        candidates.push({ syntax: '.' + top2[0], label: 'class: .' + top2[0], type: 'class', score: 55 });
      } else if (element.classList.length > 0) {
        const first = Array.from(element.classList).find(c => !/^orch-/i.test(c));
        if (first) {
          candidates.push({ syntax: '.' + first, label: 'class(弱): .' + first.slice(0, 30), type: 'class', score: 25 });
        }
      }
    }

    // 7. xpath & css path fallbacks
    candidates.push({ syntax: 'xpath:' + getElementXPath(element), label: 'xpath (路径)', type: 'xpath', score: 15 });
    candidates.push({ syntax: 'css:' + getElementCssPath(element), label: 'css (完整结构)', type: 'css', score: 16 });
    candidates.push({ syntax: 'css:' + getOldCssSelector(element), label: 'css (原算法)', type: 'css', score: 12 });

    // 8. verify & sort
    candidates.forEach(c => { c.matchCount = verifyLocator(c.syntax, c.type); });

    // ancestor narrowing
    const hasCssUnique = candidates.some(c => c.type !== 'xpath' && c.matchCount === 1);
    if (!hasCssUnique && element !== document.body) {
      const seenBase = new Set();
      const bases = [];
      for (const c of candidates) {
        if (c.type === 'xpath' || c.matchCount === 0) continue;
        const css = convertToCssForTest(c.syntax, c.type);
        if (css && !seenBase.has(css)) { seenBase.add(css); bases.push(css); }
      }
      let cur = element.parentElement;
      let depth = 0;
      let foundUnique = false;
      while (cur && cur !== document.body && depth < 6 && !foundUnique) {
        const ancSel = getSimpleAncestorSelector(cur);
        if (ancSel) {
          for (const base of bases) {
            const combined = `${ancSel} ${base}`;
            let count = -1;
            try { count = document.querySelectorAll(combined).length; } catch (e) {}
            if (count >= 1) {
              candidates.push({ syntax: `css:${combined}`, label: `${combined} (祖先收窄)`, type: 'css', score: count === 1 ? 78 : 28, matchCount: count });
              if (count === 1) foundUnique = true;
            }
          }
        }
        cur = cur.parentElement;
        depth++;
      }
    }

    // structural css fallback
    const stillNoCssUnique = !candidates.some(c => c.type !== 'xpath' && c.matchCount === 1);
    if (stillNoCssUnique && element !== document.body) {
      const struct = buildStructuralCss(element);
      if (struct) {
        let count = -1;
        try { count = document.querySelectorAll(struct).length; } catch (e) {}
        if (count >= 1) {
          candidates.push({ syntax: 'css:' + struct, label: struct + ' (结构路径)', type: 'css', score: count === 1 ? 76 : 22, matchCount: count });
        }
      }
    }

    return candidates
      .filter(c => c.matchCount !== 0)
      .sort((a, b) => {
        const aUnique = a.matchCount === 1 ? 2 : (a.matchCount === -1 ? 1 : 0);
        const bUnique = b.matchCount === 1 ? 2 : (b.matchCount === -1 ? 1 : 0);
        if (aUnique !== bUnique) return bUnique - aUnique;
        return b.score - a.score;
      });
  }

  // ─── Canvas Highlight ────────────────────────────────────────────

  function initHighlightCanvas() {
    if (highlightHost) return;
    highlightHost = document.createElement('div');
    highlightHost.id = 'rpa-capture-highlight-host';
    highlightHost.style.cssText = 'all:initial;position:fixed;top:0;left:0;width:100%;height:100%;z-index:2147483647;pointer-events:none;';
    const shadow = highlightHost.attachShadow({ mode: 'open' });
    shadow.innerHTML = `
      <style>:host { all: initial; } canvas { display: block; }</style>
      <canvas id="rpa-hl-canvas" style="position:fixed;top:0;left:0;pointer-events:none;"></canvas>
    `;
    document.body.appendChild(highlightHost);
    highlightCanvas = shadow.getElementById('rpa-hl-canvas');
    highlightCtx = highlightCanvas.getContext('2d');
    resizeHighlightCanvas();
    window.addEventListener('resize', resizeHighlightCanvas);
    window.addEventListener('scroll', () => { if (captureMode) { resizeHighlightCanvas(); redrawHighlight(); } }, true);
  }

  function resizeHighlightCanvas() {
    if (!highlightCanvas) return;
    highlightCanvas.width = window.innerWidth * (window.devicePixelRatio || 1);
    highlightCanvas.height = window.innerHeight * (window.devicePixelRatio || 1);
    highlightCanvas.style.width = window.innerWidth + 'px';
    highlightCanvas.style.height = window.innerHeight + 'px';
  }

  function redrawHighlight() {
    if (!highlightCtx || !highlightCanvas) return;
    highlightCtx.clearRect(0, 0, highlightCanvas.width, highlightCanvas.height);
    if (!lockedElement || !document.body.contains(lockedElement)) return;
    const rect = lockedElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    highlightCtx.save();
    highlightCtx.strokeStyle = '#ff4444';
    highlightCtx.lineWidth = 2 * dpr;
    highlightCtx.fillStyle = 'rgba(255, 68, 68, 0.08)';
    highlightCtx.fillRect(rect.left * dpr, rect.top * dpr, rect.width * dpr, rect.height * dpr);
    highlightCtx.strokeRect(rect.left * dpr, rect.top * dpr, rect.width * dpr, rect.height * dpr);
    // label
    const tag = lockedElement.tagName.toLowerCase();
    const cls = lockedElement.className && typeof lockedElement.className === 'string'
      ? lockedElement.className.trim().split(/\s+/).filter(Boolean).slice(0, 3).join('.')
      : '';
    const text = tag + (lockedElement.id ? '#' + lockedElement.id : '') + (cls ? '.' + cls : '');
    highlightCtx.font = (11 * dpr) + 'px monospace';
    const tw = highlightCtx.measureText(text).width;
    const pad = 3 * dpr;
    highlightCtx.fillStyle = '#ff4444';
    highlightCtx.fillRect((rect.left + 2) * dpr, (rect.top - 16) * dpr, tw + pad * 2, 14 * dpr);
    highlightCtx.fillStyle = '#fff';
    highlightCtx.fillText(text, (rect.left + 2 + pad) * dpr, (rect.top - 5) * dpr);
    highlightCtx.restore();
  }

  // ─── Capture Mode ────────────────────────────────────────────────

  function enterCaptureMode() {
    if (captureMode) return;
    captureMode = true;
    initHighlightCanvas();
    document.addEventListener('mousemove', onCaptureMouseMove);
    document.addEventListener('click', onCaptureClick, true);
    console.log('[RPA Capture] 进入捕获模式');
    showToast('捕获模式：Alt+Click 捕获元素，Esc 退出');
  }

  function exitCaptureMode() {
    if (!captureMode) return;
    captureMode = false;
    document.removeEventListener('mousemove', onCaptureMouseMove);
    document.removeEventListener('click', onCaptureClick, true);
    lockedElement = null;
    lastHoveredEl = null;
    capturedScreenshot = null;
    if (highlightHost) {
      highlightHost.remove();
      highlightHost = null;
      highlightCanvas = null;
      highlightCtx = null;
    }
    console.log('[RPA Capture] 退出捕获模式');
  }

  function onCaptureMouseMove(e) {
    if (!captureMode) return;
    const stack = document.elementsFromPoint(e.clientX, e.clientY);
    const target = stack.find(el => el !== document.body && el !== document.documentElement && !el.closest('#rpa-capture-highlight-host'));
    if (!target) return;
    if (target === lastHoveredEl) {
      redrawHighlight();
      return;
    }
    lastHoveredEl = target;
    lockedElement = target;
    lockedCandidates = generateLocators(target);
    if (lockedCandidates.length > 0) {
      lockedLocator = lockedCandidates[0].syntax;
      lockedLocatorType = lockedCandidates[0].type;
    }
    redrawHighlight();
  }

  async function onCaptureClick(e) {
    if (!captureMode || !e.altKey) return;
    e.preventDefault();
    e.stopPropagation();
    if (!lockedElement || lockedCandidates.length === 0) {
      showToast('没有可捕获的元素');
      return;
    }
    showConfirmModal();
  }

  // ─── Confirm Modal ───────────────────────────────────────────────

  function showConfirmModal() {
    const features = buildFeatureSnapshot(lockedElement);
    const best = lockedCandidates[0];
    let selectedIdx = 0;

    const overlay = document.createElement('div');
    overlay.id = 'rpa-capture-modal';
    overlay.style.cssText = `
      position: fixed; top: 0; left: 0; width: 100%; height: 100%;
      background: rgba(0,0,0,0.5); z-index: 2147483646;
      display: flex; align-items: center; justify-content: center;
      font-family: system-ui, sans-serif;
    `;

    const card = document.createElement('div');
    card.style.cssText = `
      background: #fff; border-radius: 8px; width: 520px; max-width: 90vw;
      max-height: 80vh; overflow-y: auto; box-shadow: 0 10px 40px rgba(0,0,0,0.3);
      display: flex; flex-direction: column;
    `;

    // Header
    const header = document.createElement('div');
    header.style.cssText = 'padding: 16px 20px; border-bottom: 1px solid #eee; font-weight: 600; font-size: 15px; color: #333;';
    header.textContent = '确认捕获元素';
    card.appendChild(header);

    // Body
    const body = document.createElement('div');
    body.style.cssText = 'padding: 16px 20px; flex: 1; overflow-y: auto;';

    // Element info
    const info = document.createElement('div');
    info.style.cssText = 'margin-bottom: 12px; padding: 10px; background: #f5f5f5; border-radius: 6px; font-size: 12px; color: #555;';
    const cls = features.classes?.slice(0, 3).join('.') || '';
    info.innerHTML = `
      <div><b>标签:</b> ${features.tag}${features.id ? '#' + features.id : ''}${cls ? '.' + cls : ''}</div>
      <div><b>文本:</b> ${features.inner_text?.slice(0, 60) || '无'}</div>
      <div><b>页面:</b> ${window.location.href.slice(0, 60)}</div>
    `;
    body.appendChild(info);

    // Element name input
    const nameWrap = document.createElement('div');
    nameWrap.style.cssText = 'margin-bottom: 12px;';
    const nameLabel = document.createElement('label');
    nameLabel.textContent = '元素名称';
    nameLabel.style.cssText = 'display: block; font-size: 12px; font-weight: 500; color: #333; margin-bottom: 4px;';
    const nameInput = document.createElement('input');
    nameInput.type = 'text';
    // Build a readable default name: tag + id or text
    let defaultName = features.tag;
    if (features.id) {
      defaultName += '_' + features.id;
    } else if (features.inner_text) {
      const text = features.inner_text.trim().replace(/\s+/g, '_').slice(0, 20);
      if (text) defaultName += '_' + text;
    }
    nameInput.value = defaultName;
    nameInput.style.cssText = 'width: 100%; padding: 6px 8px; border: 1px solid #d9d9d9; border-radius: 4px; font-size: 13px; box-sizing: border-box;';
    nameWrap.appendChild(nameLabel);
    nameWrap.appendChild(nameInput);
    body.appendChild(nameWrap);

    // Element screenshot
    const screenshotWrap = document.createElement('div');
    screenshotWrap.style.cssText = 'margin-bottom: 12px;';
    const screenshotLabel = document.createElement('div');
    screenshotLabel.textContent = '元素截图';
    screenshotLabel.style.cssText = 'font-size: 12px; font-weight: 500; color: #333; margin-bottom: 4px;';
    const screenshotBox = document.createElement('div');
    screenshotBox.style.cssText = 'width: 100%; background: #f5f5f5; border-radius: 6px; overflow: hidden; min-height: 60px; display: flex; align-items: center; justify-content: center; color: #999; font-size: 12px;';
    screenshotBox.textContent = '正在截图...';
    screenshotWrap.appendChild(screenshotLabel);
    screenshotWrap.appendChild(screenshotBox);
    body.appendChild(screenshotWrap);

    // Request element screenshot from background.js
    const rect = lockedElement.getBoundingClientRect();
    chrome.runtime.sendMessage({
      action: 'captureElementScreenshot',
      rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
      dpr: window.devicePixelRatio || 1,
    }, (resp) => {
      if (resp?.dataUrl) {
        capturedScreenshot = resp.dataUrl;
        const img = document.createElement('img');
        img.src = resp.dataUrl;
        img.style.cssText = 'display: block; max-width: 100%; height: auto; margin: 0 auto;';
        screenshotBox.innerHTML = '';
        screenshotBox.style.minHeight = '';
        screenshotBox.appendChild(img);
      } else {
        screenshotBox.textContent = '截图失败';
      }
    });

    // Locator input
    const inputWrap = document.createElement('div');
    inputWrap.style.cssText = 'margin-bottom: 12px;';
    const inputLabel = document.createElement('label');
    inputLabel.textContent = '定位器';
    inputLabel.style.cssText = 'display: block; font-size: 12px; font-weight: 500; color: #333; margin-bottom: 4px;';
    const inputEl = document.createElement('input');
    inputEl.type = 'text';
    inputEl.value = best.syntax;
    inputEl.style.cssText = 'width: 100%; padding: 6px 8px; border: 1px solid #d9d9d9; border-radius: 4px; font-size: 13px; font-family: monospace; box-sizing: border-box;';
    inputWrap.appendChild(inputLabel);
    inputWrap.appendChild(inputEl);
    body.appendChild(inputWrap);

    // Candidates list
    const listLabel = document.createElement('div');
    listLabel.textContent = '候选选择器';
    listLabel.style.cssText = 'font-size: 12px; font-weight: 500; color: #333; margin-bottom: 6px;';
    body.appendChild(listLabel);

    const list = document.createElement('div');
    list.style.cssText = 'border: 1px solid #eee; border-radius: 6px; overflow: hidden;';
    lockedCandidates.slice(0, 6).forEach((c, idx) => {
      const row = document.createElement('div');
      row.style.cssText = `
        padding: 8px 10px; font-size: 12px; cursor: pointer; border-bottom: 1px solid #f0f0f0;
        display: flex; align-items: center; gap: 8px;
        ${idx === 0 ? 'background: #e6f7ff;' : ''}
      `;
      const uniqueBadge = c.matchCount === 1
        ? '<span style="background:#52c41a;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;white-space:nowrap;">唯一</span>'
        : `<span style="background:#f0f0f0;color:#666;font-size:10px;padding:1px 5px;border-radius:3px;white-space:nowrap;">${c.matchCount} 匹配</span>`;
      row.innerHTML = `
        <input type="radio" name="rpa-cand" ${idx === 0 ? 'checked' : ''} style="margin:0;">
        <span style="flex:1;min-width:0;">
          <span style="color:#333;font-weight:500;">${c.label}</span>
          <span style="color:#999;margin-left:6px;font-size:11px;">score:${c.score}</span>
        </span>
        ${uniqueBadge}
      `;
      row.addEventListener('click', () => {
        selectedIdx = idx;
        inputEl.value = c.syntax;
        Array.from(list.children).forEach((r, i) => {
          r.style.background = i === idx ? '#e6f7ff' : '';
          r.querySelector('input').checked = i === idx;
        });
      });
      list.appendChild(row);
    });
    body.appendChild(list);

    card.appendChild(body);

    // Footer
    const footer = document.createElement('div');
    footer.style.cssText = 'padding: 12px 20px; border-top: 1px solid #eee; display: flex; justify-content: flex-end; gap: 8px;';

    const btnCancel = document.createElement('button');
    btnCancel.textContent = '取消';
    btnCancel.style.cssText = 'padding: 6px 16px; border: 1px solid #d9d9d9; background: #fff; border-radius: 4px; cursor: pointer; font-size: 13px;';
    btnCancel.addEventListener('click', () => overlay.remove());

    const btnOk = document.createElement('button');
    btnOk.textContent = '确认捕获';
    btnOk.style.cssText = 'padding: 6px 16px; border: none; background: #1677ff; color: #fff; border-radius: 4px; cursor: pointer; font-size: 13px;';
    btnOk.addEventListener('click', async () => {
      const sel = lockedCandidates[selectedIdx];
      const customSyntax = inputEl.value.trim() || sel.syntax;
      const payload = {
        action: 'captureElement',
        payload: {
          name: nameInput.value.trim() || defaultName,
          locator: customSyntax,
          locatorType: sel.type,
          score: sel.score,
          matchCount: sel.matchCount,
          tag: features.tag,
          text: features.inner_text?.slice(0, 50) || '',
          pageUrl: window.location.href,
          candidates: lockedCandidates.slice(0, 5).map(c => ({ syntax: c.syntax, type: c.type, score: c.score, matchCount: c.matchCount })),
          features,
          screenshot: capturedScreenshot,
        },
      };
      overlay.remove();
      try {
        console.log('[RPA Capture] sending payload:', JSON.stringify(payload.payload));
        await chrome.runtime.sendMessage(payload);
        // 延迟广播，等后端保存完成
        setTimeout(() => {
          console.log('[RPA Capture] sending broadcast after 500ms');
          chrome.runtime.sendMessage({
            action: 'notifyElementCaptured',
            payload: { name: nameInput.value.trim() || defaultName },
          }).catch((err) => console.warn('[RPA Capture] broadcast send failed:', err));
        }, 500);
        showToast(`已捕获: ${sel.label} (${sel.matchCount === 1 ? '唯一' : sel.matchCount + ' 匹配'})`);
      } catch (err) {
        console.error('[RPA Capture] send failed:', err);
        showToast('发送失败: ' + err.message);
      }
    });

    footer.appendChild(btnCancel);
    footer.appendChild(btnOk);
    card.appendChild(footer);

    overlay.appendChild(card);
    document.body.appendChild(overlay);
  }

  // ─── Toast ───────────────────────────────────────────────────────

  function showToast(message) {
    const existing = document.getElementById('rpa-capture-toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.id = 'rpa-capture-toast';
    toast.style.cssText = `
      position: fixed; bottom: 20px; right: 20px; z-index: 2147483647;
      background: rgba(0,0,0,0.8); color: #fff; padding: 10px 16px;
      border-radius: 6px; font-size: 13px; font-family: system-ui, sans-serif;
      max-width: 400px; word-break: break-word; pointer-events: none;
      transition: opacity 0.3s;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 3000);
  }

  // ─── Keyboard shortcuts ──────────────────────────────────────────

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Alt') {
      altPressed = true;
      altComboUsed = false;
      e.preventDefault();
      enterCaptureMode();
    } else if (altPressed && e.key !== 'Alt') {
      altComboUsed = true;
    } else if (e.key === 'Escape') {
      exitCaptureMode();
    }
  });

  document.addEventListener('keyup', (e) => {
    if (e.key === 'Alt') {
      altPressed = false;
      if (altComboUsed && captureMode) {
        exitCaptureMode();
      } else if (captureMode) {
        exitCaptureMode();
      }
    }
  });

  // ─── Listen for cross-tab broadcast from background.js ───────────
  // Use window.postMessage to notify page main world (bypasses CSP)

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'elementCaptured') {
      console.log('[RPA Capture] received broadcast, posting to page');
      window.postMessage(
        { source: 'rpa-extension', type: 'elementCaptured', detail: message.payload },
        '*'
      );
      sendResponse({ dispatched: true });
    }
  });

  console.log('[RPA Capture] 捕获模块已加载，按 Alt 进入捕获模式');
})();
