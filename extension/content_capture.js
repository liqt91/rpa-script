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
  let captureEnabled = false;
  let lastCapturePayload = null;
  let activeCandidate = null;
  let lastMouseX = -1;
  let lastMouseY = -1;
  // Anchor-first capture: an existing element chosen as the active loop anchor
  // BEFORE capturing its inner children. Shape: { name, selector, family, elements }.
  let activeAnchor = null;

  // ─── Helpers: stability scoring (inspired by @medv/finder) ───────

  /** Check if a token looks like a human word, not a generated hash. */
  function wordLike(name) {
    if (!name || name.length < 3 || name.length > 50) return false;
    if (/^[a-f0-9]{8,}$/i.test(name)) return false; // pure hex hash
    const words = name.split(/[-_]/);
    for (const word of words) {
      if (word.length <= 2) return false;
      const lettersOnly = word.replace(/[0-9]/g, '');
      if (lettersOnly.length >= 4 && /[^aeiouAEIOU]{4,}/.test(lettersOnly)) return false;
      // 高数字比例通常是 hash（如 189h5o3）
      const digits = (word.match(/[0-9]/g) || []).length;
      if (digits > 0 && digits / word.length > 0.5) return false;
    }
    return true;
  }

  const CLASS_BLACKLIST = [
    /^css-[a-z0-9]{4,}$/i,          // CSS-in-JS
    /^_[a-f0-9]{6,}$/i,             // Emotion / CSS Modules hash
    /_{2,}[a-z0-9]{4,}/i,           // Scoped CSS
    /^orch-/i,                      // Orchestration markers
    /^mui-/, /^chakra-/, /^ant-/,   // Component lib prefixes
    /^v-[a-f0-9]{6,}$/i,            // Vue scoped
    /^[a-z]{1,2}_[a-zA-Z0-9]{5,}$/, // Short prefix + hash
    /^sc-[a-zA-Z]{4,}$/,            // styled-components generated
  ];

  function isBlacklistedClass(cls) {
    return CLASS_BLACKLIST.some(p => p.test(cls));
  }

  function isStableId(id) {
    if (!id || id.length > 50 || id.length < 4) return false;
    if (/^:[Rr][a-z0-9]*:$/.test(id)) return false;
    if (/^css-[a-z0-9]{4,}$/i.test(id)) return false;
    if (/^(mui|chakra|ant|ember|ng|vue|svelte)[-_][a-z0-9]{4,}/i.test(id)) return false;
    if (/^[a-f0-9]{8,}$/i.test(id)) return false;
    const digits = (id.match(/[0-9]/g) || []).length;
    if (digits > 0 && digits / id.length > 0.5) return false;
    return true;
  }

  function isStableClass(cls) {
    if (!cls || cls.length < 2) return false;
    if (isBlacklistedClass(cls)) return false;
    return wordLike(cls);
  }

  function containsUnstableClass(css) {
    const matches = css.match(/\.([a-zA-Z0-9_-]+)/g);
    if (!matches) return false;
    return matches.some(cls => isBlacklistedClass(cls.slice(1)));
  }

  /** Fragile attributes that change across renders or sessions. */
  const FRAGILE_ATTR_PATTERNS = [
    /^style$/i,
    /^on\w+$/i,                         // event handlers: onclick, onchange, ...
    /^data-react\w*$/i,                 // data-reactroot, data-reactid, data-react-checksum
    /^data-v-[a-f0-9]+$/i,              // Vue scoped style markers
    /^_ngcontent-[a-z0-9-]+$/i,         // Angular scoped style markers
    /^_nghost-[a-z0-9-]+$/i,
    /^aria-(owns|activedescendant|busy|live|relevant)$/i, // dynamic ARIA
  ];
  function isFragileAttr(name) {
    return FRAGILE_ATTR_PATTERNS.some(p => p.test(name));
  }

  function getDirectText(el) {
    let t = '';
    for (const node of el.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) t += node.textContent;
    }
    return t.trim().replace(/\s+/g, ' ');
  }

  function isRenderedVisible(el) {
    if (!el) return false;
    let node = el;
    let accumulatedOpacity = 1;
    while (node && node !== document.body && node !== document.documentElement) {
      if (node.getAttribute && node.getAttribute('aria-hidden') === 'true') return false;
      const style = getComputedStyle(node);
      if (style.visibility === 'hidden' || style.display === 'none') return false;
      if (style.pointerEvents === 'none') return false;
      const opacity = parseFloat(style.opacity);
      if (Number.isFinite(opacity)) accumulatedOpacity *= opacity;
      if (accumulatedOpacity <= 0.01) return false;
      node = node.parentElement;
    }
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return false;
    // ignore off-screen clones commonly used as decoys
    if (rect.bottom < 0 || rect.top > window.innerHeight || rect.right < 0 || rect.left > window.innerWidth) return false;
    // form controls: ignore disabled/readonly/unfocusable duplicates
    if (el.disabled === true || el.readOnly === true || el.getAttribute('tabindex') === '-1' || el.hasAttribute('inert')) return false;
    return true;
  }

  // ─── web-verse text fingerprint ──────────────────────────────────

  function generateVerseFingerprint(text) {
    if (!text || text.length < 5) return null;
    const sentences = text
      .split(/[。！？.!?;；\n\r]+/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    if (sentences.length === 0) return null;

    const first = sentences[0];
    const last = sentences[sentences.length - 1];

    function prefix3(sentence) {
      const words = sentence.split(/[^\w一-龥]+/).filter(Boolean);
      const chars = [];
      for (let i = 0; i < words.length && chars.length < 3; i++) {
        const w = words[i];
        // 纯中文按字拆分，避免整句只取1个字导致 fingerprint 过短
        if (/^[一-龥]+$/.test(w)) {
          for (const ch of w) {
            chars.push(ch);
            if (chars.length >= 3) break;
          }
        } else {
          const m = w.match(/[a-zA-Z一-龥]/);
          chars.push(m ? m[0].toLowerCase() : w.charAt(0).toLowerCase());
        }
      }
      return chars.join('');
    }

    const fp = prefix3(first) + prefix3(last);
    return fp.length >= 3 ? fp.slice(0, 6) : null;
  }

  function buildFeatureSnapshot(element) {
    if (!element || element.nodeType !== Node.ELEMENT_NODE) return {};
    const attrs = {};
    try {
      for (const attr of element.attributes) {
        if (attr.name === 'class' || attr.name === 'id' || isFragileAttr(attr.name)) continue;
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

  function isMeaningfulNode(el) {
    if (!el) return false;
    const tag = el.tagName.toLowerCase();
    if (el.id && isStableId(el.id)) return true;
    if (el.classList && Array.from(el.classList).some(isStableClass)) return true;
    for (const attr of el.attributes || []) {
      if (attr.name.startsWith('data-')) return true;
    }
    if (['header','main','footer','nav','aside','article','section','form'].includes(tag)) return true;
    return false;
  }

  function buildElementPath(element) {
    const path = [];
    let cur = element;
    while (cur && cur !== document.body && cur !== document.documentElement) {
      const parent = cur.parentElement;
      const tag = cur.tagName.toLowerCase();
      const attrs = {};
      const classes = [];
      for (const attr of cur.attributes || []) {
        try {
          if (attr.name === 'id') continue;
          if (attr.name === 'class') {
            classes.push(...(attr.value || '').split(/\s+/).filter(Boolean));
          } else if (!isFragileAttr(attr.name)) {
            let v = attr.value || '';
            if (v.length > 100) v = v.slice(0, 100) + '…';
            attrs[attr.name] = v;
          }
        } catch (e) {}
      }
      // 补充框架通过 IDL property 设置的值（attributes 集合中可能缺失）
      if (cur.href !== undefined && !attrs.href) attrs.href = cur.href;
      if (cur.src !== undefined && !attrs.src) attrs.src = cur.src;
      if (cur.value !== undefined && !attrs.value) attrs.value = String(cur.value);
      if (cur.checked !== undefined && !attrs.checked) attrs.checked = String(cur.checked);

      let index = 0;
      const childrenTags = [];
      let siblingInfo = [];
      let realIndex = 0;
      if (parent) {
        const siblings = Array.from(parent.children);
        childrenTags.push(...siblings.map((c) => c.tagName.toLowerCase()));
        const sameTag = siblings.filter((c) => c.tagName === cur.tagName);
        index = sameTag.indexOf(cur);
        realIndex = siblings.indexOf(cur);
        if (cur === element) {
          siblingInfo = siblings.map((sib) => ({
            tag: sib.tagName.toLowerCase(),
            id: sib.id || '',
            classes: sib.classList ? Array.from(sib.classList).filter((c) => !/^orch-/i.test(c)).slice(0, 4) : [],
          }));
        }
      }
      path.unshift({ tag, id: cur.id || '', classes, attrs, index, realIndex, childrenTags, siblings: siblingInfo });
      cur = parent;
      if (path.length > 15) break;
    }
    return path;
  }

  function attrValNeedsCssFallback(v) {
    return /[@'"\n\r\t]/.test(v) || v.includes('=');
  }

  function escapeAttrVal(v) {
    return v.replace(/\n/g, ' ').trim();
  }

  function cssEscape(v) {
    if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') {
      return CSS.escape(v);
    }
    return v.replace(/[\0-\x1f\x7f-\x9f!"#$%&'()*+,./:;<=>?@[\\\]^`{|}~]/g, (char) => '\\' + char);
  }

  /** Escape attribute value for CSS [attr="value"] — only quotes and backslashes. */
  function attrValueEscape(v) {
    return String(v).replace(/["\\]/g, '\\$&').replace(/\n/g, ' ');
  }

  /** Build an XPath string literal, handling both quote types. */
  function xpathLiteral(v) {
    if (typeof v !== 'string') v = String(v);
    if (!v.includes("'")) return "'" + v + "'";
    if (!v.includes('"')) return '"' + v + '"';
    return "concat('" + v.split("'").join("', \"'\", '") + "')";
  }

  function getOldCssSelector(element) {
    if (!element || element === document.body) return 'body';
    if (element.id && /^[a-zA-Z][a-zA-Z0-9_-]*$/.test(element.id)) return '#' + element.id;
    const dataAttrs = ['data-testid', 'data-id', 'data-key', 'data-name', 'data-e2e'];
    for (const attr of dataAttrs) {
      const val = element.getAttribute(attr);
      if (val) return `[${attr}="${attrValueEscape(val)}"]`;
    }
    if (element.classList && element.classList.length > 0) {
      const classes = Array.from(element.classList)
        .filter(isStableClass)
        .slice(0, 2);
      if (classes.length > 0) return '.' + classes.join('.');
    }
    const parent = element.parentElement;
    if (parent) {
      const siblings = Array.from(parent.children).filter(c => c.tagName === element.tagName);
      const idx = siblings.indexOf(element) + 1;
      const tag = element.tagName.toLowerCase();
      return siblings.length === 1 ? tag : `${tag}:nth-of-type(${idx})`;
    }
    return element.tagName.toLowerCase();
  }

  function getOldCssSelectorFromPath(path) {
    if (!path || path.length === 0) return 'body';
    const target = path[path.length - 1];
    const tag = target.tag;
    if (target.id && /^[a-zA-Z][a-zA-Z0-9_-]*$/.test(target.id)) return '#' + target.id;
    const dataAttrs = ['data-testid', 'data-id', 'data-key', 'data-name', 'data-e2e'];
    for (const attr of dataAttrs) {
      const val = target.attrs[attr];
      if (val) return `[${attr}="${attrValueEscape(val)}"]`;
    }
    const stableClasses = (target.classes || []).filter(isStableClass).slice(0, 2);
    if (stableClasses.length > 0) return '.' + stableClasses.join('.');
    const sameTagCount = (target.childrenTags || []).filter(t => t === tag).length;
    const idx = target.index + 1;
    return sameTagCount === 1 ? tag : `${tag}:nth-of-type(${idx})`;
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

  function getElementXPathFromPath(path) {
    if (!path || path.length === 0) return { selector: '/html/body', pathMapping: [] };
    const segs = [];
    const pathMapping = [];
    for (let i = path.length - 1; i >= 0; i--) {
      const node = path[i];
      const sameTagCount = (node.childrenTags || []).filter(t => t === node.tag).length;
      const seg = sameTagCount <= 1 ? node.tag : `${node.tag}[${node.index + 1}]`;
      segs.unshift(seg);
      pathMapping.unshift(i);
    }
    return { selector: '//body/' + segs.join('/'), pathMapping };
  }

  function convertToCssForTest(syntax, family) {
    try {
      switch (family) {
        case 'css': return syntax.replace(/^css:/, '');
        case 'xpath': return null;
        case 'drission': {
          if (syntax.startsWith('@')) {
            const m = syntax.match(/^@([\w\-:]+)=(.+)$/);
            if (!m) return null;
            return `[${m[1]}="${attrValueEscape(m[2])}"]`;
          }
          const m1 = syntax.match(/^tag:(\w+)@class=(.+)$/);
          if (m1) return `${m1[1]}.${m1[2]}`;
          const m2 = syntax.match(/^tag:(\w+)@([\w\-:]+)=(.+)$/);
          if (m2) return `${m2[1]}[${m2[2]}="${attrValueEscape(m2[3])}"]`;
          const parts = syntax.match(/@@class:([^@]+)/g);
          if (parts) return parts.map(p => '.' + p.replace('@@class:', '')).join('');
          return null;
        }
        default: return syntax;
      }
    } catch (e) { return null; }
  }

  function verifyLocator(syntax, family, visibleOnly = true) {
    if (family === 'xpath') {
      const xp = syntax.replace(/^xpath:/, '');
      try {
        const r = document.evaluate(xp, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        if (!visibleOnly) return r.snapshotLength;
        let count = 0;
        for (let i = 0; i < r.snapshotLength; i++) {
          if (isRenderedVisible(r.snapshotItem(i))) count++;
        }
        return count;
      } catch (e) { return -1; }
    }
    // verse / tag_text / text 依赖非 CSS 逻辑（XPath 或 fingerprint），
    // convertToCssForTest 对它们生成的是 jQuery :contains 或原始 syntax，
    // 原生 querySelectorAll 不支持，直接复用 resolveAllForVerify 计数。
    if (family === 'drission' && (syntax.startsWith('verse:') || syntax.startsWith('text=') || /^tag:\w+@text\(\)=/.test(syntax))) {
      let subType = 'text';
      if (syntax.startsWith('verse:')) subType = 'verse';
      else if (/^tag:\w+@text\(\)=/.test(syntax)) subType = 'tag_text';
      return resolveAllForVerify(syntax, subType).length;
    }
    const css = convertToCssForTest(syntax, family);
    if (!css) return -1;
    try {
      if (!visibleOnly) return document.querySelectorAll(css).length;
      return Array.from(document.querySelectorAll(css)).filter(isRenderedVisible).length;
    } catch (e) { return -1; }
  }

  function getSimpleAncestorSelector(el) {
    if (!el || el === document.body) return null;
    if (el.id && isStableId(el.id)) return '#' + el.id;
    const dataAttrs = ['data-testid', 'data-test', 'data-id', 'data-name', 'data-key', 'data-e2e'];
    for (const a of dataAttrs) {
      const v = el.getAttribute(a);
      if (v && v.length < 80 && !attrValNeedsCssFallback(v)) {
        return `[${a}="${attrValueEscape(v)}"]`;
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

  function findAnchor(element) {
    let cur = element.parentElement;
    while (cur && cur !== document.body) {
      if (cur.id && isStableId(cur.id)) return { el: cur, sel: '#' + cur.id };

      const dataAttrs = ['data-testid', 'data-test', 'data-id', 'data-name', 'data-key', 'data-e2e'];
      for (const attr of dataAttrs) {
        const v = cur.getAttribute(attr);
        if (v && v.length < 80 && !attrValNeedsCssFallback(v)) {
          return { el: cur, sel: `[${attr}="${attrValueEscape(v)}"]` };
        }
      }

      const role = cur.getAttribute('role');
      if (role) return { el: cur, sel: `[role="${attrValueEscape(role)}"]` };

      const ariaLabel = cur.getAttribute('aria-label');
      if (ariaLabel && ariaLabel.length < 80 && !attrValNeedsCssFallback(ariaLabel)) {
        return { el: cur, sel: `[aria-label="${attrValueEscape(ariaLabel)}"]` };
      }

      const tag = cur.tagName.toLowerCase();
      if (['header', 'main', 'footer', 'nav', 'aside', 'article', 'section'].includes(tag)) {
        return { el: cur, sel: tag };
      }

      cur = cur.parentElement;
    }
    return null;
  }

  function buildAnchorDescendantCandidates(element, candidates) {
    const anchor = findAnchor(element);
    if (!anchor) return;

    const tag = element.tagName.toLowerCase();
    const ancSel = anchor.sel;

    // 1) 简单后代: 锚点内直接用 tag
    const simpleSel = `${ancSel} ${tag}`;
    let count = verifyLocator(simpleSel, 'css');
    if (count === 1) {
      candidates.push({ syntax: 'css:' + simpleSel, label: simpleSel + ' (锚点)', family: 'css', score: 90, matchCount: 1 });
      return;
    }

    // 2) tag + class
    if (element.classList) {
      const stableClasses = Array.from(element.classList).filter(isStableClass);
      for (const c of stableClasses) {
        const sel = `${ancSel} ${tag}.${c}`;
        count = verifyLocator(sel, 'css');
        if (count === 1) {
          candidates.push({ syntax: 'css:' + sel, label: sel + ' (锚点)', family: 'css', score: 85, matchCount: 1 });
          return;
        }
      }
    }

    // 3) tag + data-*
    const dataAttrs = ['data-testid', 'data-test', 'data-test-id', 'data-cy', 'data-qa', 'data-e2e', 'data-id', 'data-key', 'data-name'];
    for (const attr of dataAttrs) {
      const v = element.getAttribute(attr);
      if (!v || v.length > 80 || attrValNeedsCssFallback(v)) continue;
      const sel = `${ancSel} ${tag}[${attr}="${attrValueEscape(v)}"]`;
      count = verifyLocator(sel, 'css');
      if (count === 1) {
        candidates.push({ syntax: 'css:' + sel, label: sel + ' (锚点)', family: 'css', score: 88, matchCount: 1 });
        return;
      }
    }

    // 4) tag + 语义属性
    const semanticAttrs = ['aria-label', 'name', 'placeholder', 'title', 'role'];
    for (const attr of semanticAttrs) {
      const v = element.getAttribute(attr);
      if (!v || v.length > 80) continue;
      const sel = `${ancSel} ${tag}[${attr}="${attrValueEscape(v)}"]`;
      count = verifyLocator(sel, 'css');
      if (count === 1) {
        candidates.push({ syntax: 'css:' + sel, label: sel + ' (锚点)', family: 'css', score: 82, matchCount: 1 });
        return;
      }
    }
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
      try { if (verifyLocator(trial, 'css') === 1) return trial; } catch (e) {}
      if (seg.startsWith('#')) break;
      cur = parent;
    }
    return segs.length ? segs.join(' > ') : null;
  }

  function buildStructuralCssFromPath(path) {
    if (!path || path.length === 0) return null;
    const segs = [];
    const pathMapping = [];
    for (let i = path.length - 1; i >= 0; i--) {
      const node = path[i];
      const sameTagCount = (node.childrenTags || []).filter(t => t === node.tag).length;
      const stableClasses = (node.classes || []).filter(isStableClass);
      let seg;
      if (node.id && isStableId(node.id)) {
        seg = '#' + cssEscape(node.id);
      } else if (stableClasses.length > 0) {
        seg = sameTagCount === 1
          ? `${node.tag}.${cssEscape(stableClasses[0])}`
          : `${node.tag}.${cssEscape(stableClasses[0])}:nth-of-type(${node.index + 1})`;
      } else {
        seg = sameTagCount === 1 ? node.tag : `${node.tag}:nth-of-type(${node.index + 1})`;
      }
      segs.unshift(seg);
      pathMapping.unshift(i);
      const trial = segs.join(' > ');
      try { if (verifyLocator(trial, 'css') === 1) return { selector: trial, pathMapping }; } catch (e) {}
      if (seg.startsWith('#')) break;
    }
    return { selector: segs.length ? segs.join(' > ') : null, pathMapping };
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
        seg = sameTag.length === 1
          ? `${tag}.${stableClasses[0]}`
          : `${tag}.${stableClasses[0]}:nth-of-type(${idx})`;
      } else {
        seg = `${tag}:nth-of-type(${idx})`;
      }
      segs.unshift(seg);
      if (seg.startsWith('#')) break;
      cur = parent;
    }
    return segs.join(' > ');
  }

  function getElementCssPathFromPath(path) {
    if (!path || path.length === 0) return { selector: 'body', pathMapping: [] };
    const segs = [];
    const pathMapping = [];
    for (let i = path.length - 1; i >= 0; i--) {
      const node = path[i];
      const sameTagCount = (node.childrenTags || []).filter(t => t === node.tag).length;
      const stableClasses = (node.classes || []).filter(isStableClass);
      let seg;
      if (node.id && isStableId(node.id)) {
        seg = '#' + cssEscape(node.id);
      } else if (stableClasses.length > 0) {
        seg = sameTagCount === 1
          ? `${node.tag}.${cssEscape(stableClasses[0])}`
          : `${node.tag}.${cssEscape(stableClasses[0])}:nth-of-type(${node.index + 1})`;
      } else {
        seg = `${node.tag}:nth-of-type(${node.index + 1})`;
      }
      segs.unshift(seg);
      pathMapping.unshift(i);
      if (seg.startsWith('#')) break;
    }
    return { selector: segs.join(' > '), pathMapping };
  }

  function computeScore(c) {
    let score = c.score;
    const syntax = c.syntax;

    // 1. nth-of-type / xpath[n] 惩罚：每个 -50 分（位置信息最后才用，Robula+ 原则）
    const nthCount = ((syntax.match(/:nth-of-type\(\d+\)/g) || []).length +
                      (syntax.match(/\[\d+\]/g) || []).length);
    score -= nthCount * 50;

    // 2. 深度惩罚：每多一层 > 或 / 减 10 分（层级越少越好）
    let depth = 0;
    if (syntax.startsWith('css:')) {
      const css = syntax.slice(4);
      depth = (css.match(/>/g) || []).length;
    } else if (syntax.startsWith('xpath:')) {
      const xp = syntax.slice(6);
      depth = (xp.match(/\//g) || []).length - 2;
    }
    score -= Math.max(0, depth - 1) * 10;

    // 3. 属性选择器惩罚：每个 -8 分（属性越少越好）
    const attrCount = (syntax.match(/\[[^\]]+\]/g) || []).length;
    score -= attrCount * 8;

    // 4. class 数量惩罚：超过 1 个的每个 -4 分
    const classCount = (syntax.match(/\./g) || []).length;
    score -= Math.max(0, classCount - 1) * 4;

    // 5. 简洁奖励：总长度越短分越高
    const clean = syntax.replace(/^(css:|xpath:|verse:|text=|tag:)/, '');
    if (clean.length < 15) score += 8;
    else if (clean.length < 25) score += 4;

    return Math.max(score, 1);
  }

  /** Try to remove intermediate levels from a unique CSS selector (finder optimize pattern). */
  function optimizeSelector(selector, element) {
    if (!selector.startsWith('css:')) return selector;
    let css = selector.slice(4);
    const segs = css.split(/\s*>\s*/);
    if (segs.length <= 2) return selector;

    for (let i = 1; i < segs.length - 1; i++) {
      const reduced = [...segs];
      reduced.splice(i, 1);
      const trial = reduced.join(' > ');
      try {
        const nodes = document.querySelectorAll(trial);
        if (nodes.length === 1 && nodes[0] === element) {
          return optimizeSelector('css:' + trial, element);
        }
      } catch (e) {}
    }
    return selector;
  }

  // ─── Finder-style level-combination search ───────────────────────

  function _levelCandidates(el) {
    const level = [];
    const elId = el.getAttribute('id');
    if (elId && isStableId(elId)) {
      level.push({ name: '#' + cssEscape(elId), penalty: 0 });
    }
    if (el.classList) {
      for (const c of Array.from(el.classList).filter(isStableClass)) {
        level.push({ name: '.' + cssEscape(c), penalty: 1 });
      }
    }
    const acceptedAttrs = new Set(['role', 'name', 'aria-label', 'rel', 'href']);
    for (const attr of el.attributes || []) {
      if (isFragileAttr(attr.name)) continue;
      if (acceptedAttrs.has(attr.name) || attr.name.startsWith('data-')) {
        if (attr.value && !attrValNeedsCssFallback(attr.value) && attr.value.length < 100) {
          level.push({ name: `[${cssEscape(attr.name)}="${attrValueEscape(attr.value)}"]`, penalty: 2 });
        }
      }
    }
    const tag = el.tagName.toLowerCase();
    level.push({ name: tag, penalty: 5 });
    const parent = el.parentElement;
    if (parent) {
      const sameTag = Array.from(parent.children).filter(c => c.tagName === el.tagName);
      const idx = sameTag.indexOf(el) + 1;
      if (sameTag.length > 1) {
        level.push({ name: `${tag}:nth-of-type(${idx})`, penalty: 10 });
      }
    }
    return level;
  }

  function _levelCandidatesFromNode(node) {
    const level = [];
    if (node.id && isStableId(node.id)) {
      level.push({ name: '#' + cssEscape(node.id), penalty: 0 });
    }
    if (node.classes) {
      for (const c of node.classes.filter(isStableClass)) {
        level.push({ name: '.' + cssEscape(c), penalty: 1 });
      }
    }
    const acceptedAttrs = new Set(['role', 'name', 'aria-label', 'rel', 'href']);
    for (const [name, value] of Object.entries(node.attrs || {})) {
      if (isFragileAttr(name)) continue;
      if (acceptedAttrs.has(name) || name.startsWith('data-')) {
        if (value && !attrValNeedsCssFallback(value) && value.length < 100) {
          level.push({ name: `[${cssEscape(name)}="${attrValueEscape(value)}"]`, penalty: 2 });
        }
      }
    }
    level.push({ name: node.tag, penalty: 5 });
    const sameTagCount = (node.childrenTags || []).filter(t => t === node.tag).length;
    if (sameTagCount > 1) {
      level.push({ name: `${node.tag}:nth-of-type(${node.index + 1})`, penalty: 10 });
    }
    return level;
  }

  function* _combinations(stack, path = []) {
    if (stack.length > 0) {
      for (const node of stack[0]) {
        yield* _combinations(stack.slice(1), path.concat(node));
      }
    } else {
      yield path;
    }
  }

  function _selectorFromPath(path) {
    let query = path[0].name;
    for (let i = 1; i < path.length; i++) {
      const level = path[i].level || 0;
      if (path[i - 1].level === level - 1) {
        query = `${path[i].name} > ${query}`;
      } else {
        query = `${path[i].name} ${query}`;
      }
    }
    return query;
  }

  function _penalty(path) {
    return path.reduce((acc, n) => acc + n.penalty, 0);
  }

  function buildFinderCandidates(element, candidates) {
    const root = document.body;
    const stack = [];
    let current = element;
    let i = 0;
    while (current && current !== root && i < 6) {
      let level = _levelCandidates(current);
      level = level.slice(0, 4); // cap per-level to avoid combinatorial explosion
      for (const node of level) {
        node.level = i;
      }
      stack.push(level);
      current = current.parentElement;
      i++;
    }

    const combos = [];
    for (const combo of _combinations(stack)) {
      combos.push(combo);
    }
    combos.sort((a, b) => _penalty(a) - _penalty(b));

    let checked = 0;
    const maxChecks = 80;
    const seen = new Set();
    for (const combo of combos) {
      if (checked >= maxChecks) break;
      const css = _selectorFromPath(combo);
      if (seen.has(css)) continue;
      seen.add(css);
      checked++;
      try {
        if (verifyLocator(css, 'css') === 1) {
          candidates.push({
            syntax: 'css:' + css,
            label: css + ' (组合搜索)',
            family: 'css',
            score: 94 - _penalty(combo),
            matchCount: 1,
          });
        }
      } catch (e) {}
    }
  }

  function buildFinderCandidatesFromPath(path, candidates) {
    const stack = [];
    const maxLevels = Math.min(path.length, 6);
    for (let i = 0; i < maxLevels; i++) {
      const node = path[path.length - 1 - i];
      let level = _levelCandidatesFromNode(node);
      level = level.slice(0, 4);
      for (const item of level) {
        item.level = i;
        item.pathIndex = path.length - 1 - i;
      }
      stack.push(level);
    }

    const combos = [];
    for (const combo of _combinations(stack)) {
      combos.push(combo);
    }
    combos.sort((a, b) => _penalty(a) - _penalty(b));

    let checked = 0;
    const maxChecks = 80;
    const seen = new Set();
    for (const combo of combos) {
      if (checked >= maxChecks) break;
      const css = _selectorFromPath(combo);
      if (seen.has(css)) continue;
      seen.add(css);
      checked++;
      try {
        if (verifyLocator(css, 'css') === 1) {
          const pathMapping = combo.slice().reverse().map(n => n.pathIndex);
          candidates.push({
            syntax: 'css:' + css,
            label: css + ' (组合搜索)',
            family: 'css',
            score: 94 - _penalty(combo),
            matchCount: 1,
            pathMapping,
          });
        }
      } catch (e) {}
    }
  }

  // ─── Sibling anchor strategy ─────────────────────────────────────

  function buildSiblingAnchorCandidates(element, candidates) {
    const tag = element.tagName.toLowerCase();
    const parent = element.parentElement;
    if (!parent) return;

    const siblings = Array.from(parent.children);
    if (siblings.length < 2) return;

    const myIdx = siblings.indexOf(element);
    const directions = [];

    // Adjacent previous siblings (up to 3)
    for (let i = myIdx - 1; i >= Math.max(0, myIdx - 3); i--) {
      directions.push({ dir: '+', anchor: siblings[i], desc: '前兄弟' });
    }
    // General sibling: any previous sibling with stable id
    for (let i = myIdx - 1; i >= 0; i--) {
      const sib = siblings[i];
      if (sib.id && isStableId(sib.id)) {
        directions.push({ dir: '~', anchor: sib, desc: '前兄弟~' });
        break;
      }
    }

    for (const { dir, anchor, desc } of directions) {
      const ancSel = getSimpleAncestorSelector(anchor);
      if (!ancSel) continue;

      // anchor + tag
      const sel1 = `${ancSel}${dir}${tag}`;
      let count = -1;
      try { count = verifyLocator(sel1, 'css'); } catch (e) {}
      if (count === 1) {
        candidates.push({ syntax: 'css:' + sel1, label: `${sel1} (${desc})`, family: 'css', score: 80, matchCount: 1 });
        continue;
      }

      // anchor + tag.class
      if (element.classList) {
        const stableClasses = Array.from(element.classList).filter(isStableClass);
        let found = false;
        for (const c of stableClasses) {
          const sel3 = `${ancSel}${dir}${tag}.${cssEscape(c)}`;
          try { count = verifyLocator(sel3, 'css'); } catch (e) {}
          if (count === 1) {
            candidates.push({ syntax: 'css:' + sel3, label: `${sel3} (${desc})`, family: 'css', score: 83, matchCount: 1 });
            found = true;
            break;
          }
        }
        if (found) continue;
      }

      // anchor + *
      const sel2 = `${ancSel}${dir}*`;
      try { count = verifyLocator(sel2, 'css'); } catch (e) {}
      if (count === 1) {
        candidates.push({ syntax: 'css:' + sel2, label: `${sel2} (${desc})`, family: 'css', score: 78, matchCount: 1 });
      }
    }
  }

  // ─── List / similar element detection (structural fingerprint + ancestor voting)

  /**
   * Build a structural fingerprint for list-item similarity comparison.
   * Avoids text content (too fragile) and focuses on shape/attrs/children.
   */
  function makeStructuralFingerprint(el) {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return null;
    const tag = el.tagName.toLowerCase();
    const stableClasses = el.classList ? Array.from(el.classList).filter(isStableClass) : [];
    const meaningfulAttrs = [];
    for (const attr of el.attributes || []) {
      const name = attr.name;
      if (name === 'class' || name === 'id' || isFragileAttr(name)) continue;
      if (name.startsWith('data-') || ['role', 'aria-label', 'name', 'type', 'rel'].includes(name)) {
        meaningfulAttrs.push(name);
      }
    }
    // Child tag sequence (depth-1 only; cheap and stable enough)
    const childTags = [];
    for (const child of el.children) {
      childTags.push(child.tagName.toLowerCase());
    }
    // Semantic flags
    const hasLink = el.querySelector('a') !== null || el.tagName === 'A';
    const hasImg = el.querySelector('img') !== null || el.tagName === 'IMG';
    const hasText = el.textContent && el.textContent.trim().length > 0;
    return {
      tag,
      stableClasses,
      meaningfulAttrs,
      childTags,
      hasLink,
      hasImg,
      hasText,
      depth: 0, // filled later if needed
    };
  }

  function jaccard(a, b) {
    if (!a.length || !b.length) return 0;
    const setA = new Set(a);
    const setB = new Set(b);
    const inter = new Set([...setA].filter(x => setB.has(x)));
    return inter.size / (setA.size + setB.size - inter.size);
  }

  /**
   * Similarity score [0, 1] between two structural fingerprints.
   */
  function fingerprintSimilarity(a, b) {
    if (!a || !b) return 0;
    if (a.tag !== b.tag) return 0;
    let score = 0.35; // same tag baseline
    score += jaccard(a.stableClasses, b.stableClasses) * 0.30;
    score += jaccard(a.meaningfulAttrs, b.meaningfulAttrs) * 0.15;
    score += jaccard(a.childTags, b.childTags) * 0.15;
    if (a.hasLink === b.hasLink) score += 0.025;
    if (a.hasImg === b.hasImg) score += 0.025;
    if (a.hasText === b.hasText) score += 0.025;
    return Math.min(1.0, score);
  }

  /**
   * Detect the list family for a target element.
   * Walks up ancestors and scores each by (similar sibling ratio * similar sibling count).
   *
   * Returns: {
   *   container: Element | null,
   *   items: Element[],
   *   score: number,
   *   similarity: number, // average similarity of items to target
   * }
   */
  function detectListFamily(target, options = {}) {
    const maxDepth = options.maxDepth || 6;
    const minItems = options.minItems || 2;
    const similarityThreshold = options.similarityThreshold || 0.60;
    const targetFp = makeStructuralFingerprint(target);
    if (!targetFp) return { container: null, items: [], score: 0, similarity: 0 };

    let best = { container: null, items: [], score: 0, similarity: 0 };
    let cur = target.parentElement;
    let depth = 0;

    while (cur && cur !== document.body && cur !== document.documentElement && depth < maxDepth) {
      const children = Array.from(cur.children);
      if (children.length >= minItems) {
        const similar = [];
        let totalSim = 0;
        for (const child of children) {
          const childFp = makeStructuralFingerprint(child);
          if (!childFp) continue;
          const sim = fingerprintSimilarity(targetFp, childFp);
          if (sim >= similarityThreshold) {
            similar.push(child);
            totalSim += sim;
          }
        }
        const ratio = similar.length / children.length;
        // score = count * ratio, with a small depth penalty
        const score = similar.length * ratio * (1 - depth * 0.05);
        const avgSim = similar.length > 0 ? totalSim / similar.length : 0;
        if (score > best.score && similar.length >= minItems) {
          best = { container: cur, items: similar, score, similarity: avgSim };
        }
      }
      cur = cur.parentElement;
      depth++;
    }

    return best;
  }

  /**
   * Build a CSS selector for an element that is stable enough for list-item matching.
   * Tries: data-* > stable class > role > tag.
   */
  function buildListItemSelector(el) {
    if (!el) return '';
    const tag = el.tagName.toLowerCase();

    // 1) data-*
    const dataAttrs = ['data-testid', 'data-test', 'data-test-id', 'data-cy', 'data-qa', 'data-e2e', 'data-id', 'data-key', 'data-name'];
    for (const attr of dataAttrs) {
      const v = el.getAttribute(attr);
      if (v && v.length < 80 && !attrValNeedsCssFallback(v)) {
        // For list items, a data-* value that appears on all items is usually structural.
        // If value looks unique, don't use it.
        if (!/[0-9]{4,}/.test(v) && !/^[a-f0-9]{6,}$/i.test(v)) {
          return `${tag}[${attr}="${attrValueEscape(v)}"]`;
        }
      }
    }

    // 2) stable class (prefer class that is present and not over-qualified)
    const stableClasses = el.classList ? Array.from(el.classList).filter(isStableClass) : [];
    if (stableClasses.length > 0) {
      return `${tag}.${stableClasses.map(cssEscape).join('.')}`;
    }

    // 3) role
    const role = el.getAttribute('role');
    if (role) return `${tag}[role="${attrValueEscape(role)}"]`;

    // 4) fallback to tag (often too broad, but caller will verify count)
    return tag;
  }

  /**
   * Build a stable CSS selector for a list container.
   */
  function buildListContainerSelector(container) {
    if (!container) return '';
    if (container.id && isStableId(container.id)) return '#' + container.id;

    const dataAttrs = ['data-testid', 'data-test', 'data-test-id', 'data-id', 'data-name', 'data-role'];
    for (const attr of dataAttrs) {
      const v = container.getAttribute(attr);
      if (v && v.length < 80 && !attrValNeedsCssFallback(v)) {
        return `[${attr}="${attrValueEscape(v)}"]`;
      }
    }

    const tag = container.tagName.toLowerCase();
    const stableClasses = container.classList ? Array.from(container.classList).filter(isStableClass) : [];
    if (stableClasses.length > 0) {
      return `${tag}.${stableClasses.map(cssEscape).join('.')}`;
    }
    if (['header', 'main', 'footer', 'nav', 'aside', 'article', 'section'].includes(tag)) return tag;
    return '';
  }

  /**
   * Generalize a selector so it matches all list items (not just the target index).
   * Strips :nth-of-type() / :nth-child() and overly specific IDs.
   */
  function generalizeListSelector(sel) {
    if (!sel) return sel;
    return sel
      .replace(/:nth-of-type\(\d+\)/g, '')
      .replace(/:nth-child\(\d+\)/g, '')
      .replace(/\[\d+\]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function stripXPathLeadingAxes(xp) {
    return xp.replace(/^\/+/, '');
  }

  function buildXPathForElement(el) {
    if (!el) return '';
    const tag = el.tagName.toLowerCase();

    // id
    if (el.id && isStableId(el.id)) {
      return `//*[@id=${xpathLiteral(el.id)}]`;
    }

    // data-*
    const dataAttrs = ['data-testid', 'data-test', 'data-test-id', 'data-cy', 'data-qa', 'data-e2e', 'data-id', 'data-key', 'data-name'];
    for (const attr of dataAttrs) {
      const v = el.getAttribute(attr);
      if (v && v.length < 80 && !attrValNeedsCssFallback(v)) {
        if (!/[0-9]{4,}/.test(v) && !/^[a-f0-9]{6,}$/i.test(v)) {
          return `//${tag}[@${attr}=${xpathLiteral(v)}]`;
        }
      }
    }

    // stable class
    const stableClasses = el.classList ? Array.from(el.classList).filter(isStableClass) : [];
    if (stableClasses.length > 0) {
      const parts = [`//${tag}`];
      for (const cls of stableClasses) {
        parts.push(`[contains(@class,${xpathLiteral(cls)})]`);
      }
      return parts.join('');
    }

    // role
    const role = el.getAttribute('role');
    if (role) return `//${tag}[@role=${xpathLiteral(role)}]`;

    // fallback
    return `//${tag}`;
  }

  /**
   * Build a position-based relative XPath from `item` down to descendant `el`.
   * Result is prefixed with `./` so it evaluates strictly within the item.
   * Returns null if `el` is not a descendant of `item` or the path is too deep.
   */
  function buildRelativeXPath(item, el) {
    const segs = [];
    let cur = el;
    while (cur && cur !== item) {
      const parent = cur.parentElement;
      if (!parent) return null;
      const sameTag = Array.from(parent.children).filter(c => c.tagName === cur.tagName);
      const pos = sameTag.indexOf(cur);
      // Shadow-DOM / slot boundaries can make parentElement.children not contain
      // cur. Bail rather than emit an invalid 1-indexed position (e.g. tag[0]).
      if (pos === -1) return null;
      const idx = pos + 1;
      const tag = cur.tagName.toLowerCase();
      segs.unshift(sameTag.length === 1 ? tag : `${tag}[${idx}]`);
      cur = parent;
      if (segs.length > 8) return null;
    }
    if (cur !== item) return null;
    if (segs.length === 0) return null;
    const xp = './' + segs.join('/');
    // Self-validate: the relative xpath must resolve to exactly one node === el
    // within the item, mirroring buildRelativeCss's uniqueness check.
    try {
      const r = document.evaluate(xp, item, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
      if (r.snapshotLength !== 1 || r.snapshotItem(0) !== el) return null;
    } catch (e) {
      return null;
    }
    return xp;
  }

  /**
   * Build a relative CSS selector that, queried within `item`, uniquely resolves
   * to `el`. Tries stable id/class/data-* first, then bare tag. Each candidate is
   * validated to match exactly one element === el inside the item. Returns null
   * if no unique stable CSS selector is found.
   */
  function buildRelativeCss(item, el) {
    const tag = el.tagName.toLowerCase();
    const tryers = [];
    if (el.id && isStableId(el.id)) tryers.push('#' + cssEscape(el.id));
    const stable = el.classList ? Array.from(el.classList).filter(isStableClass) : [];
    if (stable.length) tryers.push(tag + '.' + stable.map(cssEscape).join('.'));
    const dataAttrs = ['data-testid', 'data-test', 'data-test-id', 'data-cy', 'data-qa', 'data-e2e', 'data-id', 'data-key', 'data-name'];
    for (const attr of dataAttrs) {
      const v = el.getAttribute(attr);
      if (v && v.length < 80 && !attrValNeedsCssFallback(v)) {
        tryers.push(`${tag}[${attr}="${attrValueEscape(v)}"]`);
      }
    }
    tryers.push(tag);
    for (const sel of tryers) {
      try {
        const found = item.querySelectorAll(sel);
        if (found.length === 1 && found[0] === el) return sel;
      } catch (e) { /* invalid selector, skip */ }
    }
    return null;
  }

  /**
   * Generate a ranked list of relative selectors from an anchor element down to a
   * target descendant. Each candidate is validated against every resolved anchor
   * instance; candidates that match exactly one element per anchor score highest.
   */
  function generateRelativeCandidates(activeAnchor, host, el) {
    if (!activeAnchor || !host || !el || !host.contains(el)) return [];
    const anchorSelector = activeAnchor.selector;
    const anchorFamily = activeAnchor.family || splitSelectorPrefix(anchorSelector).family;
    let anchors = activeAnchor.elements;
    if (!anchors || !anchors.length) {
      anchors = resolveAllForVerify(anchorSelector, anchorFamily);
    }
    if (!anchors || !anchors.length) return [];

    const tag = el.tagName.toLowerCase();
    const candidates = [];
    const seen = new Set();

    function addCandidate(syntax, family) {
      if (!syntax || seen.has(syntax)) return;
      seen.add(syntax);
      let total = 0;
      let exact = 0;
      let zero = 0;
      for (const a of anchors) {
        const matches = queryRelativeInItem(a, syntax);
        total += matches.length;
        if (matches.length === 1) exact++;
        else if (matches.length === 0) zero++;
      }
      if (total === 0) return;
      const n = anchors.length;
      let score = 100;
      score -= (n - exact) * 15;
      score -= (total - exact) * 10;
      if (zero > 0) score -= 10;
      score = Math.max(0, Math.min(100, Math.round(score)));
      candidates.push({
        syntax,
        family,
        score,
        matchCount: total,
        isList: false,
        label: syntax.replace(/^(css|xpath):/, ''),
      });
    }

    // CSS strategies
    if (el.id && isStableId(el.id)) addCandidate('css:#' + cssEscape(el.id), 'css');
    const stableClasses = el.classList ? Array.from(el.classList).filter(isStableClass) : [];
    if (stableClasses.length) {
      addCandidate('css:' + tag + '.' + stableClasses.map(cssEscape).join('.'), 'css');
      addCandidate('css:' + stableClasses.map(c => '.' + cssEscape(c)).join(''), 'css');
    }
    const dataAttrs = ['data-testid', 'data-test', 'data-test-id', 'data-cy', 'data-qa', 'data-e2e', 'data-id', 'data-key', 'data-name'];
    for (const attr of dataAttrs) {
      const v = el.getAttribute(attr);
      if (v && v.length < 80 && !attrValNeedsCssFallback(v)) {
        addCandidate(`css:${tag}[${attr}="${attrValueEscape(v)}"]`, 'css');
        addCandidate(`css:[${attr}="${attrValueEscape(v)}"]`, 'css');
      }
    }
    addCandidate('css:' + tag, 'css');
    const parent = el.parentElement;
    if (parent) {
      const sameTag = Array.from(parent.children).filter(c => c.tagName === el.tagName);
      if (sameTag.length > 1) {
        const idx = sameTag.indexOf(el) + 1;
        addCandidate(`css:${tag}:nth-of-type(${idx})`, 'css');
      }
    }

    // XPath strategies
    const relXp = buildRelativeXPath(host, el);
    if (relXp) addCandidate('xpath:' + relXp, 'xpath');
    if (el.id && isStableId(el.id)) addCandidate(`xpath:.//*[@id=${xpathLiteral(el.id)}]`, 'xpath');
    for (const attr of dataAttrs) {
      const v = el.getAttribute(attr);
      if (v && v.length < 80) {
        addCandidate(`xpath:.//${tag}[@${attr}=${xpathLiteral(v)}]`, 'xpath');
      }
    }
    if (stableClasses.length) {
      addCandidate(`xpath:.//${tag}[contains(@class,${xpathLiteral(stableClasses[0])})]`, 'xpath');
    }
    const directText = getDirectText(el);
    if (directText && directText.length > 0 && directText.length < 50) {
      addCandidate(`xpath:.//${tag}[contains(text(),${xpathLiteral(directText)})]`, 'xpath');
    }

    return candidates.sort((a, b) => b.score - a.score);
  }

  /**
   * Capture-time anchoring (plan B). Given a detected list family, compute the
   * captured element's selector RELATIVE to its repeating ancestor (the future
   * loop item), plus the anchor (item) selector itself. Returns:
   *   { relative: 'css:...'|'xpath:...', anchor: 'css:...'|'xpath:...', family }
   * or null when:
   *   - no list family / item could be resolved, or
   *   - the captured element IS the list item itself (no child relative needed).
   * The relative selector is self-validated to resolve to exactly one element
   * (=== the captured element) within a single item.
   */
  function computeRelativeSelector(el, listFamily) {
    if (!el || !listFamily || !listFamily.container || !Array.isArray(listFamily.items)) return null;
    const item = listFamily.items.find(it => it && it.nodeType === 1 && (it === el || it.contains(el)));
    if (!item) return null;
    // The element is the repeating item itself — used as a loop target, not a
    // child reference. No relative selector to compute.
    if (item === el) return null;

    let relative = null;
    let family = null;
    const relCss = buildRelativeCss(item, el);
    if (relCss) {
      relative = 'css:' + relCss;
      family = 'css';
    } else {
      const relXp = buildRelativeXPath(item, el);
      if (relXp) {
        relative = 'xpath:' + relXp;
        family = 'xpath';
      }
    }
    if (!relative) return null;

    // Anchor selector for the repeating item. Prefer the stable CSS item selector;
    // fall back to an XPath built for the item.
    const itemSel = buildListItemSelector(item);
    let anchor = itemSel ? 'css:' + itemSel : '';
    if (!anchor) {
      const itemXp = buildXPathForElement(item);
      if (itemXp) anchor = 'xpath:' + itemXp;
    }

    return { relative, anchor, family };
  }

  function generateListCandidates(element) {
    const candidates = [];
    if (!element || element === document.body) return candidates;

    const tag = element.tagName.toLowerCase();

    // ── Phase 1: structural fingerprint + ancestor voting ──
    const family = detectListFamily(element, { maxDepth: 6, minItems: 2, similarityThreshold: 0.55 });
    if (family.container && family.items.length >= 2) {
      const listItem = family.items.find(item => item === element || item.contains(element)) || element;
      const containerSel = buildListContainerSelector(family.container);
      const itemSel = buildListItemSelector(listItem);

      // A) container > item (direct child)
      if (containerSel && itemSel) {
        const directSel = `${containerSel} > ${itemSel}`;
        const directCount = verifyLocator(directSel, 'css');
        if (directCount >= 2 && directCount <= 200) {
          candidates.push({
            syntax: 'css:' + directSel,
            label: `${directSel} (列表, ${directCount}个)`,
            family: 'css', score: 88, matchCount: directCount, isList: true,
            listContainer: containerSel, listItem: itemSel,
          });
        }
      }

      // B) container item (any depth)
      if (containerSel && itemSel) {
        const anyDepthSel = `${containerSel} ${itemSel}`;
        const anyDepthCount = verifyLocator(anyDepthSel, 'css');
        if (anyDepthCount >= 2 && anyDepthCount <= 200) {
          candidates.push({
            syntax: 'css:' + anyDepthSel,
            label: `${anyDepthSel} (列表, ${anyDepthCount}个)`,
            family: 'css', score: 82, matchCount: anyDepthCount, isList: true,
            listContainer: containerSel, listItem: itemSel,
          });
        }
      }

      // C) just the item selector (verified across whole page)
      if (itemSel) {
        const itemCount = verifyLocator(itemSel, 'css');
        if (itemCount >= 2 && itemCount <= 200) {
          candidates.push({
            syntax: 'css:' + itemSel,
            label: `${itemSel} (列表, ${itemCount}个)`,
            family: 'css', score: itemCount === family.items.length ? 80 : 55,
            matchCount: itemCount, isList: true,
            listItem: itemSel,
          });
        }
      }

      // D) container selector alone (for users who want the list wrapper)
      if (containerSel) {
        const containerCount = verifyLocator(containerSel, 'css');
        if (containerCount >= 1) {
          candidates.push({
            syntax: 'css:' + containerSel,
            label: `${containerSel} (列表容器)`,
            family: 'css', score: 45, matchCount: containerCount, isList: true,
            listContainer: containerSel,
          });
        }
      }

      // XPath list candidates (parallel to CSS A/B/C/D)
      const containerXp = buildXPathForElement(family.container);
      const itemXp = buildXPathForElement(listItem);

      // A-xp) container/item (direct child)
      if (containerXp && itemXp) {
        const directXp = `${containerXp}/${stripXPathLeadingAxes(itemXp)}`;
        const directCount = verifyLocator(directXp, 'xpath');
        if (directCount >= 2 && directCount <= 200) {
          candidates.push({
            syntax: 'xpath:' + directXp,
            label: `${directXp} (列表, ${directCount}个)`,
            family: 'xpath', score: 86, matchCount: directCount, isList: true,
            listContainer: containerXp, listItem: itemXp,
          });
        }
      }

      // B-xp) container//item (any depth)
      if (containerXp && itemXp) {
        const anyDepthXp = `${containerXp}//${stripXPathLeadingAxes(itemXp)}`;
        const anyDepthCount = verifyLocator(anyDepthXp, 'xpath');
        if (anyDepthCount >= 2 && anyDepthCount <= 200) {
          candidates.push({
            syntax: 'xpath:' + anyDepthXp,
            label: `${anyDepthXp} (列表, ${anyDepthCount}个)`,
            family: 'xpath', score: 80, matchCount: anyDepthCount, isList: true,
            listContainer: containerXp, listItem: itemXp,
          });
        }
      }

      // C-xp) just the item XPath
      if (itemXp) {
        const itemCount = verifyLocator(itemXp, 'xpath');
        if (itemCount >= 2 && itemCount <= 200) {
          candidates.push({
            syntax: 'xpath:' + itemXp,
            label: `${itemXp} (列表, ${itemCount}个)`,
            family: 'xpath', score: itemCount === family.items.length ? 78 : 53,
            matchCount: itemCount, isList: true,
            listItem: itemXp,
          });
        }
      }

      // D-xp) container XPath alone
      if (containerXp) {
        const containerCount = verifyLocator(containerXp, 'xpath');
        if (containerCount >= 1) {
          candidates.push({
            syntax: 'xpath:' + containerXp,
            label: `${containerXp} (列表容器)`,
            family: 'xpath', score: 43, matchCount: containerCount, isList: true,
            listContainer: containerXp,
          });
        }
      }
    }

    // ── Phase 1.6: target self repeated fallback ──
    // If the target element itself appears multiple times across the page
    // (even if not as direct siblings), offer it as a list item.
    const selfItemSel = buildListItemSelector(element);
    const familyItemSel = (family.container && family.items.length >= 2)
      ? buildListItemSelector(family.items.find(item => item === element || item.contains(element)) || element)
      : '';
    if (selfItemSel && selfItemSel !== familyItemSel) {
      const selfCount = verifyLocator(selfItemSel, 'css');
      if (selfCount >= 2 && selfCount <= 200) {
        candidates.push({
          syntax: 'css:' + selfItemSel,
          label: `${selfItemSel} (列表, ${selfCount}个)`,
          family: 'css', score: 60, matchCount: selfCount, isList: true,
          listItem: selfItemSel,
        });
      }
      const selfItemXp = buildXPathForElement(element);
      if (selfItemXp) {
        const selfXpCount = verifyLocator(selfItemXp, 'xpath');
        if (selfXpCount >= 2 && selfXpCount <= 200) {
          candidates.push({
            syntax: 'xpath:' + selfItemXp,
            label: `${selfItemXp} (列表, ${selfXpCount}个)`,
            family: 'xpath', score: 58, matchCount: selfXpCount, isList: true,
            listItem: selfItemXp,
          });
        }
      }
    }

    // ── Phase 1.5: ancestor list fallback ──
    // If the target itself has no list family, walk up ancestors and
    // recommend list candidates for every ancestor that qualifies.
    if (!(family.container && family.items.length >= 2)) {
      let ancestor = element.parentElement;
      let ancDepth = 0;
      const maxAncDepth = 10;
      while (ancestor && ancestor !== document.body && ancDepth < maxAncDepth) {
        const penalty = Math.min(ancDepth * 3, 25);
        const parent = ancestor.parentElement;
        let foundContainer = null;
        let foundItems = [];
        if (parent) {
          const siblings = Array.from(parent.children).filter(c => c.tagName === ancestor.tagName);
          if (siblings.length >= 2) {
            const targetFp = makeStructuralFingerprint(ancestor);
            if (targetFp) {
              const similar = siblings.filter(sib => {
                const sibFp = makeStructuralFingerprint(sib);
                if (!sibFp) return false;
                return fingerprintSimilarity(targetFp, sibFp) >= 0.55;
              });
              if (similar.length >= 2) {
                foundContainer = parent;
                foundItems = similar;
              }
            }
          }
        }
        if (foundContainer && foundItems.length >= 2) {
          const listItem = ancestor;
          const ancTag = listItem.tagName.toLowerCase();
          const containerSel = buildListContainerSelector(foundContainer);
          const itemSel = buildListItemSelector(listItem);

          // CSS A/B/C/D
          if (containerSel && itemSel) {
            const directSel = `${containerSel} > ${itemSel}`;
            const directCount = verifyLocator(directSel, 'css');
            if (directCount >= 2 && directCount <= 200) {
              candidates.push({
                syntax: 'css:' + directSel,
                label: `${directSel} (列表, ${directCount}个) ↑${ancTag}`,
                family: 'css', score: 90 - penalty, matchCount: directCount, isList: true,
                listContainer: containerSel, listItem: itemSel,
              });
            }
          }
          if (containerSel && itemSel) {
            const anyDepthSel = `${containerSel} ${itemSel}`;
            const anyDepthCount = verifyLocator(anyDepthSel, 'css');
            if (anyDepthCount >= 2 && anyDepthCount <= 200) {
              candidates.push({
                syntax: 'css:' + anyDepthSel,
                label: `${anyDepthSel} (列表, ${anyDepthCount}个) ↑${ancTag}`,
                family: 'css', score: 84 - penalty, matchCount: anyDepthCount, isList: true,
                listContainer: containerSel, listItem: itemSel,
              });
            }
          }
          if (itemSel) {
            const itemCount = verifyLocator(itemSel, 'css');
            if (itemCount >= 2 && itemCount <= 200) {
              candidates.push({
                syntax: 'css:' + itemSel,
                label: `${itemSel} (列表, ${itemCount}个) ↑${ancTag}`,
                family: 'css', score: itemCount === foundItems.length ? 82 - penalty : 57 - penalty,
                matchCount: itemCount, isList: true,
                listItem: itemSel,
              });
            }
          }
          if (containerSel) {
            const containerCount = verifyLocator(containerSel, 'css');
            if (containerCount >= 1) {
              candidates.push({
                syntax: 'css:' + containerSel,
                label: `${containerSel} (列表容器) ↑${ancTag}`,
                family: 'css', score: 47 - penalty, matchCount: containerCount, isList: true,
                listContainer: containerSel,
              });
            }
          }

          // XPath A/B/C/D
          const containerXp = buildXPathForElement(foundContainer);
          const itemXp = buildXPathForElement(listItem);
          if (containerXp && itemXp) {
            const directXp = `${containerXp}/${stripXPathLeadingAxes(itemXp)}`;
            const directCount = verifyLocator(directXp, 'xpath');
            if (directCount >= 2 && directCount <= 200) {
              candidates.push({
                syntax: 'xpath:' + directXp,
                label: `${directXp} (列表, ${directCount}个) ↑${ancTag}`,
                family: 'xpath', score: 88 - penalty, matchCount: directCount, isList: true,
                listContainer: containerXp, listItem: itemXp,
              });
            }
          }
          if (containerXp && itemXp) {
            const anyDepthXp = `${containerXp}//${stripXPathLeadingAxes(itemXp)}`;
            const anyDepthCount = verifyLocator(anyDepthXp, 'xpath');
            if (anyDepthCount >= 2 && anyDepthCount <= 200) {
              candidates.push({
                syntax: 'xpath:' + anyDepthXp,
                label: `${anyDepthXp} (列表, ${anyDepthCount}个) ↑${ancTag}`,
                family: 'xpath', score: 82 - penalty, matchCount: anyDepthCount, isList: true,
                listContainer: containerXp, listItem: itemXp,
              });
            }
          }
          if (itemXp) {
            const itemCount = verifyLocator(itemXp, 'xpath');
            if (itemCount >= 2 && itemCount <= 200) {
              candidates.push({
                syntax: 'xpath:' + itemXp,
                label: `${itemXp} (列表, ${itemCount}个) ↑${ancTag}`,
                family: 'xpath', score: itemCount === foundItems.length ? 80 - penalty : 55 - penalty,
                matchCount: itemCount, isList: true,
                listItem: itemXp,
              });
            }
          }
          if (containerXp) {
            const containerCount = verifyLocator(containerXp, 'xpath');
            if (containerCount >= 1) {
              candidates.push({
                syntax: 'xpath:' + containerXp,
                label: `${containerXp} (列表容器) ↑${ancTag}`,
                family: 'xpath', score: 45 - penalty, matchCount: containerCount, isList: true,
                listContainer: containerXp,
              });
            }
          }
        }

        // 跨容器列表检测：祖先本身有稳定特征且在整页重复出现
        const itemSel = buildListItemSelector(ancestor);
        if (itemSel && itemSel !== ancestor.tagName.toLowerCase()) {
          const count = verifyLocator(itemSel, 'css');
          if (count >= 2 && count <= 200) {
            const ancTag = ancestor.tagName.toLowerCase();
            candidates.push({
              syntax: 'css:' + itemSel,
              label: `${itemSel} (列表, ${count}个) ↑${ancTag}`,
              family: 'css', score: 58 - penalty, matchCount: count, isList: true,
              listItem: itemSel,
            });
            const itemXp = buildXPathForElement(ancestor);
            if (itemXp) {
              const xpCount = verifyLocator(itemXp, 'xpath');
              if (xpCount >= 2 && xpCount <= 200) {
                candidates.push({
                  syntax: 'xpath:' + itemXp,
                  label: `${itemXp} (列表, ${xpCount}个) ↑${ancTag}`,
                  family: 'xpath', score: 56 - penalty, matchCount: xpCount, isList: true,
                  listItem: itemXp,
                });
              }
            }
          }
        }

        ancestor = ancestor.parentElement;
        ancDepth++;
      }
    }

    // ── Phase 2: legacy quick heuristics as fallback ──
    const parent = element.parentElement;
    if (parent) {
      const siblings = Array.from(parent.children).filter(c => c.tagName === element.tagName);
      const stableClasses = element.classList ? Array.from(element.classList).filter(isStableClass) : [];

      if (siblings.length >= 2) {
        for (const c of stableClasses) {
          const sel = `${tag}.${c}`;
          const count = verifyLocator(sel, 'css');
          if (count >= 2) {
            candidates.push({
              syntax: 'css:' + sel, label: sel + ` (列表, ${count}个)`,
              family: 'css', score: 60, matchCount: count, isList: true,
            });
          }
        }
        if (stableClasses.length >= 2) {
          const sel = `${tag}.${stableClasses.slice(0, 3).join('.')}`;
          const count = verifyLocator(sel, 'css');
          if (count >= 2) {
            candidates.push({
              syntax: 'css:' + sel, label: sel + ` (列表, ${count}个)`,
              family: 'css', score: 62, matchCount: count, isList: true,
            });
          }
        }
      }

      // Walk up ancestors (up to 3 levels) to find stable context
      let ancestor = element.parentElement;
      let depth = 0;
      while (ancestor && ancestor !== document.body && depth < 3) {
        const ancSel = getSimpleAncestorSelector(ancestor);
        if (ancSel) {
          const sel1 = `${ancSel} ${tag}`;
          const count1 = verifyLocator(sel1, 'css');
          if (count1 >= 2 && count1 <= 200) {
            candidates.push({
              syntax: 'css:' + sel1, label: sel1 + ` (列表, ${count1}个)`,
              family: 'css', score: 50, matchCount: count1, isList: true,
            });
          }
          const sel2 = `${ancSel} > ${tag}`;
          const count2 = verifyLocator(sel2, 'css');
          if (count2 >= 2 && count2 <= 200) {
            candidates.push({
              syntax: 'css:' + sel2, label: sel2 + ` (列表, ${count2}个)`,
              family: 'css', score: 52, matchCount: count2, isList: true,
            });
          }
          for (const cc of stableClasses) {
            const sel3 = `${ancSel} ${tag}.${cc}`;
            const count3 = verifyLocator(sel3, 'css');
            if (count3 >= 2 && count3 <= 200) {
              candidates.push({
                syntax: 'css:' + sel3, label: sel3 + ` (列表, ${count3}个)`,
                family: 'css', score: 58, matchCount: count3, isList: true,
              });
            }
          }
        }
        ancestor = ancestor.parentElement;
        depth++;
      }
    }

    // bare tag fallback (if count is reasonable)
    const tagCount = verifyLocator(tag, 'css');
    if (tagCount >= 2 && tagCount <= 80) {
      candidates.push({
        syntax: 'css:' + tag, label: `${tag} (列表, ${tagCount}个)`,
        family: 'css', score: 25, matchCount: tagCount, isList: true,
      });
    }

    return candidates;
  }

  /**
   * Robula+ inspired: try short target-only XPath locators first.
   * Start from the most generic //* and add one robust predicate at a time.
   * If a selector is unique, it gets a high score.
   */
  function buildTargetOnlyXPathCandidates(path, candidates, element) {
    if (!path || path.length === 0) return;
    const targetNode = path[path.length - 1];
    const tag = targetNode.tag;
    const targetPathIndex = path.length - 1;

    function tryXPath(xp, score, label, filterVisible = true) {
      try {
        const r = document.evaluate(xp, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        let count = r.snapshotLength;
        if (filterVisible) {
          count = 0;
          for (let i = 0; i < r.snapshotLength; i++) {
            if (isRenderedVisible(r.snapshotItem(i))) count++;
          }
        }
        if (count === 1) {
          candidates.push({
            syntax: 'xpath:' + xp,
            label: label + ' (唯一)',
            family: 'xpath',
            score,
            pathMapping: [targetPathIndex],
          });
        }
      } catch (_e) {}
    }

    // id is king
    if (targetNode.id) {
      tryXPath(`//*[@id=${xpathLiteral(targetNode.id)}]`, 100, `id=${targetNode.id}`);
      tryXPath(`//${tag}[@id=${xpathLiteral(targetNode.id)}]`, 98, `id=${targetNode.id}`);
    }

    // data-* attrs (highest priority after id)
    const dataAttrs = ['data-testid', 'data-test', 'data-test-id', 'data-cy', 'data-qa', 'data-e2e', 'data-id', 'data-key', 'data-name'];
    for (const attr of dataAttrs) {
      const v = targetNode.attrs[attr];
      if (!v || v.length > 80) continue;
      tryXPath(`//${tag}[@${attr}=${xpathLiteral(v)}]`, 95, `${attr}=${v}`);
      tryXPath(`//*[@${attr}=${xpathLiteral(v)}]`, 93, `${attr}=${v}`);
    }

    // form attrs (name/placeholder) are extremely stable for inputs/textareas
    if (tag === 'input' || tag === 'textarea' || tag === 'select') {
      const formAttrs = ['name', 'placeholder'];
      for (const attr of formAttrs) {
        const v = targetNode.attrs[attr];
        if (!v || v.length > 80) continue;
        tryXPath(`//${tag}[@${attr}=${xpathLiteral(v)}]`, 98, `${attr}=${v}`);
        tryXPath(`//*[@${attr}=${xpathLiteral(v)}]`, 96, `${attr}=${v}`);
      }
    }

    // ancestor anchor + name (distinguishes e.g. header search vs in-feeds search)
    if ((tag === 'input' || tag === 'textarea' || tag === 'select') && targetNode.attrs.name) {
      const nameVal = targetNode.attrs.name;
      for (let i = path.length - 2; i >= Math.max(0, path.length - 11); i--) {
        const anc = path[i];
        if (anc.id && isStableId(anc.id)) {
          tryXPath(`//${anc.tag}[@id=${xpathLiteral(anc.id)}]//${tag}[@name=${xpathLiteral(nameVal)}]`, 99, `anc#id//name`);
        }
        const ancStable = (anc.classes || []).filter(isStableClass);
        for (const cls of ancStable.slice(0, 2)) {
          tryXPath(`//${anc.tag}[contains(@class,${xpathLiteral(cls)})]//${tag}[@name=${xpathLiteral(nameVal)}]`, 95 - (path.length - 2 - i) * 2, `anc.${cls}//name`);
        }
      }
    }

    // semantic attrs
    const semanticAttrs = [
      { name: 'aria-label', score: 90 },
      { name: 'name', score: 88 },
      { name: 'placeholder', score: 80 },
      { name: 'title', score: 75 },
      { name: 'rel', score: 78 },
    ];
    for (const { name, score } of semanticAttrs) {
      const v = targetNode.attrs[name];
      if (!v || v.length > 80) continue;
      tryXPath(`//${tag}[@${name}=${xpathLiteral(v)}]`, score, `${name}=${v}`);
      tryXPath(`//*[@${name}=${xpathLiteral(v)}]`, score - 2, `${name}=${v}`);
    }

    // text (direct text only; more robust than [n], less robust than stable attrs)
    if (element) {
      let text = getDirectText(element);
      if (!text && element.textContent) {
        text = element.textContent.trim().replace(/\s+/g, ' ');
      }
      if (text && text.length > 0 && text.length < 50) {
        tryXPath(`//${tag}[text()=${xpathLiteral(text)}]`, 84, `text="${text}"`, true);
        tryXPath(`//*[text()=${xpathLiteral(text)}]`, 82, `text="${text}"`, true);
        tryXPath(`//${tag}[contains(text(),${xpathLiteral(text)})]`, 76, `text~"${text}"`, true);
        tryXPath(`//*[contains(text(),${xpathLiteral(text)})]`, 74, `text~"${text}"`, true);

        // ancestor class + text (e.g. //div[contains(@class,'tags')]/span[text()='一天内'])
        for (let i = path.length - 2; i >= Math.max(0, path.length - 11); i--) {
          const anc = path[i];
          const ancStable = (anc.classes || []).filter(isStableClass);
          for (const cls of ancStable.slice(0, 2)) {
            tryXPath(`//${anc.tag}[contains(@class,${xpathLiteral(cls)})]//${tag}[text()=${xpathLiteral(text)}]`, 88 - (path.length - 2 - i) * 2, `anc.${cls}//text`, true);
            tryXPath(`//${anc.tag}[contains(@class,${xpathLiteral(cls)})]/${tag}[text()=${xpathLiteral(text)}]`, 90 - (path.length - 2 - i) * 2, `anc.${cls}/text`, true);
          }
          const ancStableId = anc.id && isStableId(anc.id) ? anc.id : '';
          if (ancStableId) {
            tryXPath(`//${anc.tag}[@id=${xpathLiteral(ancStableId)}]//${tag}[text()=${xpathLiteral(text)}]`, 94, `anc#id//text`, true);
          }
          const ancDataAttrs = ['data-testid', 'data-test', 'data-test-id', 'data-id', 'data-name', 'data-key', 'data-e2e', 'data-hp-bound', 'data-hp-kind'];
          for (const attr of ancDataAttrs) {
            const v = (anc.attrs || {})[attr];
            if (!v || v.length > 80) continue;
            tryXPath(`//${anc.tag}[@${attr}=${xpathLiteral(v)}]//${tag}[text()=${xpathLiteral(text)}]`, 86 - (path.length - 2 - i) * 2, `anc.${attr}//text`, true);
          }
        }
      }
    }

    // href (only if it looks stable: no session tokens, not too long)
    const href = targetNode.attrs.href;
    if (href && href.length < 100 && !/[?&](token|sid|session|_csrf)=/i.test(href)) {
      tryXPath(`//${tag}[@href=${xpathLiteral(href)}]`, 85, `href=${href}`);
    }

    // role + another semantic attr combo
    const role = targetNode.attrs.role;
    if (role) {
      for (const { name } of semanticAttrs) {
        const v = targetNode.attrs[name];
        if (!v || v.length > 80) continue;
        tryXPath(`//${tag}[@role=${xpathLiteral(role)}][@${name}=${xpathLiteral(v)}]`, 82, `role=${role} + ${name}`);
      }
    }

    // stable class (contains)
    const stableClasses = (targetNode.classes || []).filter(isStableClass);
    for (const cls of stableClasses.slice(0, 2)) {
      tryXPath(`//${tag}[contains(@class,${xpathLiteral(cls)})]`, 72, `class~${cls}`);
    }

    // type attr for input/button
    const typeAttr = targetNode.attrs.type;
    if (typeAttr && (tag === 'input' || tag === 'button')) {
      tryXPath(`//${tag}[@type=${xpathLiteral(typeAttr)}]`, 65, `type=${typeAttr}`);
    }

    // ancestor anchor + descendant tag path
    // when the target itself has no stable attrs but a nearby ancestor does
    for (let i = path.length - 2; i >= Math.max(0, path.length - 11); i--) {
      const anc = path[i];
      let anchorXp = null;
      let anchorScore = 0;
      if (anc.id && isStableId(anc.id)) {
        anchorXp = `//${anc.tag}[@id=${xpathLiteral(anc.id)}]`;
        anchorScore = 90;
      }
      const ancStable = (anc.classes || []).filter(isStableClass);
      if (!anchorXp && ancStable.length > 0) {
        anchorXp = `//${anc.tag}[contains(@class,${xpathLiteral(ancStable[0])})]`;
        anchorScore = 75;
      }
      if (!anchorXp) {
        for (const attr of dataAttrs) {
          const v = (anc.attrs || {})[attr];
          if (!v || v.length > 80) continue;
          anchorXp = `//${anc.tag}[@${attr}=${xpathLiteral(v)}]`;
          anchorScore = 80;
          break;
        }
      }
      if (!anchorXp) continue;

      const relSegs = [];
      for (let j = i + 1; j < path.length; j++) {
        const node = path[j];
        const idxPart = node.index > 0 ? `[${node.index + 1}]` : '';
        relSegs.push(`${node.tag}${idxPart}`);
      }
      if (relSegs.length === 0) continue;
      const relXp = relSegs.join('/');
      const depthPenalty = (path.length - 2 - i) * 2;
      tryXPath(`${anchorXp}/${relXp}`, anchorScore - depthPenalty, `anc+path`, true);
    }
  }

  function generateLocators(element) {
    if (!element || element === document.body) {
      return [{ syntax: 'tag:body', label: 'body', type: 'tag', score: 10, matchCount: 1 }];
    }
    const path = buildElementPath(element);
    const targetNode = path[path.length - 1];
    const tag = targetNode.tag;
    const candidates = [];
    const targetPathIndex = path.length - 1;

    // 1. id
    if (targetNode.id) {
      const stable = isStableId(targetNode.id);
      candidates.push({ syntax: '#' + targetNode.id, label: 'id: ' + targetNode.id, family: 'css', score: stable ? 100 : 35, pathMapping: [targetPathIndex] });
    }

    // 2. data-*
    const dataAttrs = ['data-testid', 'data-test', 'data-test-id', 'data-cy', 'data-qa', 'data-e2e', 'data-id', 'data-key', 'data-name'];
    for (const attr of dataAttrs) {
      const v = targetNode.attrs[attr];
      if (!v || v.length > 80) continue;
      if (attrValNeedsCssFallback(v)) {
        candidates.push({ syntax: `css:[${attr}="${attrValueEscape(v)}"]`, label: `${attr}=${v} (css)`, family: 'css', score: 92, pathMapping: [targetPathIndex] });
      } else {
        candidates.push({ syntax: `@${attr}=${escapeAttrVal(v)}`, label: `${attr}=${v}`, family: 'drission', score: 95, pathMapping: [targetPathIndex] });
      }
    }

    // 2.5 form attrs: name / placeholder are extremely stable for inputs/textareas
    if (tag === 'input' || tag === 'textarea' || tag === 'select') {
      const formAttrs = ['name', 'placeholder'];
      for (const attr of formAttrs) {
        const v = targetNode.attrs[attr];
        if (!v || v.length > 80 || attrValNeedsCssFallback(v)) continue;
        candidates.push({ syntax: `${tag}[${attr}="${attrValueEscape(v)}"]`, label: `${tag}[${attr}=${v}]`, family: 'css', score: 94, pathMapping: [targetPathIndex] });
        candidates.push({ syntax: `[${attr}="${attrValueEscape(v)}"]`, label: `[${attr}=${v}]`, family: 'css', score: 90, pathMapping: [targetPathIndex] });
        candidates.push({ syntax: `@${attr}=${escapeAttrVal(v)}`, label: `${attr}=${v}`, family: 'drission', score: 96, pathMapping: [targetPathIndex] });
      }
    }

    // 3. semantic attrs
    const semanticAttrs = [
      { name: 'aria-label', score: 88, family: 'drission' },
      { name: 'name', score: 85, family: 'drission' },
      { name: 'role', score: 60, family: 'drission' },
      { name: 'placeholder', score: 65, family: 'drission' },
      { name: 'title', score: 60, family: 'drission' },
    ];
    for (const { name, score, family } of semanticAttrs) {
      const v = targetNode.attrs[name];
      if (!v || v.length > 80) continue;
      if (attrValNeedsCssFallback(v)) {
        candidates.push({ syntax: `css:[${name}="${attrValueEscape(v)}"]`, label: `${name}=${v} (css)`, family: 'css', score: score - 5, pathMapping: [targetPathIndex] });
      } else {
        candidates.push({ syntax: `@${name}=${escapeAttrVal(v)}`, label: `${name}=${v}`, family, score, pathMapping: [targetPathIndex] });
      }
    }

    // 3.5 Robula+ style: short target-only XPath locators
    buildTargetOnlyXPathCandidates(path, candidates, element);

    // 4. direct text
    let directText = getDirectText(element);
    // Fallback: nested text (e.g. button > span)
    if (!directText && element.textContent) {
      directText = element.textContent.trim().replace(/\s+/g, ' ');
    }
    if (directText && directText.length > 0 && directText.length < 50) {
      candidates.push({ syntax: `tag:${tag}@text()=${directText}`, label: `${tag} + 文本: "${directText}"`, family: 'drission', score: 82 });
      candidates.push({ syntax: `text=${directText}`, label: `text: "${directText}"`, family: 'drission', score: 75 });
    }

    // 5. web-verse fingerprint (DOM-change resistant)
    const verseText = (element.innerText || element.textContent || '').trim();
    if (verseText.length > 10) {
      const fp = generateVerseFingerprint(verseText);
      if (fp) {
        candidates.push({ syntax: `verse:${fp}`, label: `verse 指纹: ${fp}`, family: 'drission', score: 78 });
      }
    }

    // 5. type attr
    if (tag === 'input' || tag === 'button') {
      const typeAttr = targetNode.attrs.type;
      if (typeAttr) {
        candidates.push({ syntax: `tag:${tag}@type=${typeAttr}`, label: `${tag}[type=${typeAttr}]`, family: 'drission', score: 50, pathMapping: [targetPathIndex] });
      }
    }

    // 6. class（只输出稳定 class，不稳定的直接跳过）
    if (targetNode.classes && targetNode.classes.length > 0) {
      const stableClasses = targetNode.classes.filter(isStableClass);
      if (stableClasses.length === 1) {
        const c = stableClasses[0];
        candidates.push({ syntax: '.' + c, label: 'class: .' + c, family: 'css', score: 65, pathMapping: [targetPathIndex] });
        candidates.push({ syntax: `tag:${tag}@class=${c}`, label: `${tag}.${c}`, family: 'drission', score: 70, pathMapping: [targetPathIndex] });
      } else if (stableClasses.length >= 2) {
        const top2 = stableClasses.slice(0, 2);
        candidates.push({ syntax: `@@class:${top2[0]}@@class:${top2[1]}`, label: `class 包含: ${top2[0]} & ${top2[1]}`, family: 'drission', score: 72, pathMapping: [targetPathIndex] });
        candidates.push({ syntax: '.' + top2[0], label: 'class: .' + top2[0], family: 'css', score: 55, pathMapping: [targetPathIndex] });
      }
    }

    // 7. finder-generated optimal selector
    try {
      if (window.__rpaFinder) {
        const finderSel = window.__rpaFinder(element, {
          seedMinLength: 1,
          optimizedMinLength: 2,
          className: wordLike,
          idName: wordLike,
          attr: (name, value) => {
            const accepted = new Set(['role', 'name', 'aria-label', 'rel', 'href']);
            if (accepted.has(name)) return wordLike(value) && value.length < 100;
            if (name.startsWith('data-')) return wordLike(name) && wordLike(value) && value.length < 100;
            return false;
          },
        });
        if (finderSel) {
          candidates.push({ syntax: 'css:' + finderSel, label: finderSel + ' (finder)', family: 'css', score: 93 });
        }
      }
    } catch (_e) {}

    // 8. anchor + descendant (影刀式简洁路径)
    buildAnchorDescendantCandidates(element, candidates);

    // 9. finder-style combination search (跨层组合，基于 path)
    buildFinderCandidatesFromPath(path, candidates);

    // 10. sibling anchor strategy
    buildSiblingAnchorCandidates(element, candidates);

    // 11. xpath & css path fallbacks
    const xpathResult = getElementXPathFromPath(path);
    if (xpathResult.selector) {
      candidates.push({ syntax: 'xpath:' + xpathResult.selector, label: xpathResult.selector + ' (路径)', family: 'xpath', score: 15, pathMapping: xpathResult.pathMapping });
    }
    const cssPathResult = getElementCssPathFromPath(path);
    if (cssPathResult.selector) {
      candidates.push({ syntax: 'css:' + cssPathResult.selector, label: cssPathResult.selector + ' (完整结构)', family: 'css', score: 16, pathMapping: cssPathResult.pathMapping });
    }
    candidates.push({ syntax: 'css:' + getOldCssSelectorFromPath(path), label: 'css (原算法)', family: 'css', score: 12, pathMapping: [targetPathIndex] });

    // 12. ancestor narrowing
    const hasCssUnique = candidates.some(c => c.family !== 'xpath' && c.matchCount === 1);
    if (!hasCssUnique && element !== document.body) {
      const seenBase = new Set();
      const bases = [];
      for (const c of candidates) {
        if (c.family === 'xpath') continue;
        const css = convertToCssForTest(c.syntax, c.family);
        if (!css || seenBase.has(css)) continue;
        if (containsUnstableClass(css)) continue; // 不稳定 class 不作为 ancestor narrowing 的 base
        seenBase.add(css); bases.push(css);
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
            try { count = verifyLocator(combined, 'css'); } catch (e) {}
            if (count >= 1) {
              candidates.push({ syntax: `css:${combined}`, label: `${combined} (祖先收窄)`, family: 'css', score: count === 1 ? 78 : 28 });
              if (count === 1) foundUnique = true;
            }
          }
        }
        cur = cur.parentElement;
        depth++;
      }
    }

    // 13. structural css fallback
    const stillNoCssUnique = !candidates.some(c => c.family !== 'xpath' && c.matchCount === 1);
    if (stillNoCssUnique && element !== document.body) {
      const structResult = buildStructuralCssFromPath(path);
      if (structResult.selector) {
        let count = -1;
        try { count = verifyLocator(structResult.selector, 'css'); } catch (e) {}
        if (count >= 1) {
          candidates.push({ syntax: 'css:' + structResult.selector, label: structResult.selector + ' (结构路径)', family: 'css', score: count === 1 ? 76 : 22, pathMapping: structResult.pathMapping });
        }
      }
    }

    // 14. List / similar elements selector
    const listCandidates = generateListCandidates(element);
    candidates.push(...listCandidates);

    // verify & re-score all candidates
    candidates.forEach(c => { c.matchCount = verifyLocator(c.syntax, c.family); });

    // optimize unique CSS selectors: remove intermediate levels if still unique (finder pattern)
    candidates.forEach(c => {
      if (c.matchCount === 1 && c.family === 'css' && c.syntax.startsWith('css:')) {
        const optimized = optimizeSelector(c.syntax, element);
        if (optimized !== c.syntax) {
          c.syntax = optimized;
          c.label = c.label.replace(/\(finder\)|\(祖先收窄\)|\(结构路径\)/, '(优化)');
          delete c.pathMapping; // optimization changes segment count; mapping is no longer valid
        }
      }
    });

    // Auto-tag list selectors: any multi-match CSS candidate without position pinning
    candidates.forEach(c => {
      if (c.isList) return;
      if (c.matchCount < 2) return;
      if (c.family !== 'css') return;
      const sel = c.syntax.replace(/^css:/, '');
      if (/:nth-of-type\(\d+\)|:nth-child\(\d+\)/.test(sel)) return;
      if (/^#[a-zA-Z][a-zA-Z0-9_-]*$/.test(sel)) return;
      c.isList = true;
      c.label = c.label.replace(/\((祖先收窄|结构路径|优化)\)/, '(列表, ' + c.matchCount + '个)');
    });

    candidates.forEach(c => { c.score = computeScore(c); });

    return candidates
      .filter(c => c.matchCount !== 0)
      .sort((a, b) => {
        const aUnique = a.matchCount === 1 ? 3 : (a.matchCount === -1 ? 2 : 1);
        const bUnique = b.matchCount === 1 ? 3 : (b.matchCount === -1 ? 2 : 1);
        if (aUnique !== bUnique) return bUnique - aUnique;
        // Within non-unique group, list candidates first
        if (a.matchCount !== 1 && b.matchCount !== 1) {
          if (a.isList && !b.isList) return -1;
          if (!a.isList && b.isList) return 1;
        }
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
    const parent = document.body || document.documentElement;
    if (!parent) {
      console.warn('[RPA capture] body/documentElement not ready, retrying in 100ms');
      highlightHost = null;
      setTimeout(initHighlightCanvas, 100);
      return;
    }
    parent.appendChild(highlightHost);
    highlightCanvas = shadow.getElementById('rpa-hl-canvas');
    highlightCtx = highlightCanvas.getContext('2d');
    resizeHighlightCanvas();
    window.addEventListener('resize', resizeHighlightCanvas);
    window.addEventListener('scroll', () => { if (captureMode) { resizeHighlightCanvas(); redrawHighlight(); } updateEditorHighlights(); }, true);
    window.addEventListener('resize', updateEditorHighlights);
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

  function resolveCaptureTarget(el) {
    if (!el) return el;
    // Already an SVG — keep it
    if (el.tagName === 'svg' || el.tagName === 'SVG') return el;
    // If the wrapper contains only one SVG/USE/IMG child and has no text,
    // prefer the inner visual element (common for icon-button wrappers).
    const children = Array.from(el.children);
    if (children.length === 1) {
      const child = children[0];
      const tag = child.tagName.toLowerCase();
      if (tag === 'svg' || tag === 'use' || tag === 'img') {
        const text = (el.textContent || '').trim();
        if (!text) return tag === 'use' ? child.closest('svg') || child : child;
      }
    }
    // If we hit a <use>, surface to the owning <svg>
    if (el.tagName === 'use' || el.tagName === 'USE') {
      return el.closest('svg') || el;
    }
    return el;
  }

  function onCaptureMouseMove(e) {
    if (!captureMode) return;
    const stack = document.elementsFromPoint(e.clientX, e.clientY);
    let target = stack.find(el => el !== document.body && el !== document.documentElement && !el.closest('#rpa-capture-highlight-host'));
    if (!target) return;
    target = resolveCaptureTarget(target);
    if (target === lastHoveredEl) {
      redrawHighlight();
      return;
    }
    lastHoveredEl = target;
    lockedElement = target;
    lockedCandidates = [];
    redrawHighlight();
  }

  function isExtensionContextInvalidated(err) {
    const msg = err?.message || String(err);
    return msg.includes('Extension context invalidated') || msg.includes('context invalidated');
  }

  async function performCapture(el) {
    const rect = el.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    let screenshot = null;
    try {
      const resp = await chrome.runtime.sendMessage({
        action: 'captureElementScreenshot',
        rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
        dpr,
      });
      if (resp?.dataUrl) screenshot = resp.dataUrl;
    } catch (e) {
      if (isExtensionContextInvalidated(e)) {
        showToast('扩展已重新加载，请刷新当前页面后重试');
        throw e;
      }
      console.warn('[RPA Capture] screenshot failed:', e);
    }

    // 异步计算候选方案并通过 Side Panel 展示
    const computePayload = () => {
      lockedCandidates = generateLocators(el);
      if (lockedCandidates.length === 0) {
        showToast('无法为此元素生成选择器');
        return;
      }
      const path = buildElementPath(el);
      const features = buildFeatureSnapshot(el);
      let defaultName = features.tag;
      if (features.id) defaultName += '_' + features.id;
      else if (features.inner_text) {
        const text = features.inner_text.trim().replace(/\s+/g, '_').slice(0, 20);
        if (text) defaultName += '_' + text;
      }

      const verseCand = lockedCandidates.find((c) => c.family === 'drission' && c.syntax.startsWith('verse:'));
      const verseFp = verseCand ? verseCand.syntax.replace(/^verse:/, '') : null;
      const best = lockedCandidates[0] || {};

      // Per-family top 10: CSS 拆为单个/列表，XPath / Drission 各取前 10，互不挤占
      function pickCandidatesByFamily(all, limitPerFamily = 10) {
        const byFamily = {};
        for (const c of all) {
          const family = c.family || c.type || 'css';
          const key = family === 'css' ? (c.isList ? 'css-list' : 'css-single') : family;
          if (!byFamily[key]) byFamily[key] = [];
          byFamily[key].push(c);
        }
        const selected = [];
        for (const key of Object.keys(byFamily)) {
          selected.push(...byFamily[key].slice(0, limitPerFamily));
        }
        return selected;
      }
      const payloadCandidates = pickCandidatesByFamily(lockedCandidates);

      // Detect list family for rich list metadata
      const listFamily = detectListFamily(el, { maxDepth: 6, minItems: 2, similarityThreshold: 0.55 });
      const listMeta = {};
      if (listFamily.container && listFamily.items.length >= 2) {
        const listItem = listFamily.items.find(item => item === el || item.contains(el)) || el;
        const containerSel = buildListContainerSelector(listFamily.container);
        const itemSel = buildListItemSelector(listItem);
        listMeta.listContainer = containerSel || '';
        listMeta.listItem = itemSel || '';
        listMeta.listSize = listFamily.items.length;
        listMeta.listSimilarity = Math.round(listFamily.similarity * 100) / 100;
      }

      // Capture-time anchoring — anchor-first only (explicit-first policy).
      // A relative selector is produced ONLY when the user pre-selected an
      // active anchor and this element sits inside one of its instances.
      // No anchor → plain global capture (no relative selector).
      const anchorMeta = {};
      if (activeAnchor && (activeAnchor.selector || (activeAnchor.elements && activeAnchor.elements.length))) {
        try {
          let anchorEls = activeAnchor.elements;
          if (!anchorEls || !anchorEls.length) {
            anchorEls = resolveAllForVerify(activeAnchor.selector, activeAnchor.family);
          }
          const host = anchorEls.find((a) => a && a.nodeType === 1 && (a === el || a.contains(el)));
          if (host && host !== el) {
            // Locate the anchor inside the target's ancestor path so the sidepanel
            // can render only the sub-path below the anchor and build the relative
            // selector directly without a global-selector round-trip.
            let anchorPathIndex = -1;
            let cur = el;
            for (let i = path.length - 1; i >= 0; i--) {
              if (cur === host) {
                anchorPathIndex = i;
                break;
              }
              cur = cur.parentElement;
            }
            if (anchorPathIndex === -1) {
              showToast('锚点层级超出捕获范围，已按全局捕获');
            } else {
              let relative = null;
              const relCss = buildRelativeCss(host, el);
              if (relCss) relative = 'css:' + relCss;
              else {
                const relXp = buildRelativeXPath(host, el);
                if (relXp) relative = 'xpath:' + relXp;
              }
              const relativeCandidates = generateRelativeCandidates(activeAnchor, host, el);
              if (relative || relativeCandidates.length) {
                anchorMeta.relativeSelector = relative || relativeCandidates[0]?.syntax || '';
                anchorMeta.relativeCandidates = relativeCandidates;
                anchorMeta.anchorSelector = activeAnchor.selector;
                anchorMeta.anchorElementName = activeAnchor.name;
                anchorMeta.anchorMode = 'anchor-first';
                anchorMeta.elementKind = 'child';
                anchorMeta.relativeManuallyEdited = false;
                anchorMeta.anchorPathIndex = anchorPathIndex;
              } else {
                showToast('无法在锚点内生成稳定相对选择器，已按普通捕获');
              }
            }
          } else {
            showToast('捕获的元素不在所选锚点内，已按全局捕获');
          }
        } catch (e) {
          console.warn('[RPA capture] anchor-first compute failed', e);
        }
      }

      const payload = {
        name: defaultName,
        tag: features.tag,
        id: features.id,
        classes: features.classes,
        attrs: features.attrs,
        path,
        screenshot,
        selectorFamily: best.family || 'css',
        targetMode: best.isList ? 'list' : 'single',
        candidates: payloadCandidates.map((c) => ({
          syntax: c.syntax, family: c.family, score: c.score, matchCount: c.matchCount, isList: c.isList || false,
          pathMapping: c.pathMapping,
          listContainer: c.listContainer || undefined,
          listItem: c.listItem || undefined,
        })),
        pageUrl: window.location.href,
        inner_text: features.inner_text,
        verse_fp: verseFp,
        ...listMeta,
        ...anchorMeta,
      };

      lastCapturePayload = payload;
      activeCandidate = null;
      chrome.runtime.sendMessage({ action: 'captureElement', payload })
        .catch((err) => {
          if (isExtensionContextInvalidated(err)) {
            showToast('扩展已重新加载，请刷新当前页面后重试');
            return;
          }
          showToast('发送失败: ' + err.message);
        });
    };
    if (typeof requestIdleCallback === 'function') {
      requestIdleCallback(computePayload, { timeout: 200 });
    } else {
      setTimeout(computePayload, 0);
    }
  }

  async function onCaptureClick(e) {
    if (!captureMode || !e.altKey) return;
    e.preventDefault();
    e.stopPropagation();
    const el = lockedElement;
    if (!el) {
      showToast('没有可捕获的元素');
      return;
    }
    exitCaptureMode();
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    await performCapture(el);
  }

  // ─── Element highlighting (used by Side Panel verify) ────────────

  let editorHighlightTimer = null;
  let editorHighlights = [];

  function removeEditorHighlights() {
    document.querySelectorAll('.rpa-editor-highlight').forEach((el) => el.remove());
    editorHighlights = [];
    if (editorHighlightTimer) {
      clearTimeout(editorHighlightTimer);
      editorHighlightTimer = null;
    }
  }

  function updateEditorHighlights() {
    const active = [];
    for (const h of editorHighlights) {
      if (!h.node.isConnected || !h.el.isConnected) {
        if (h.el.isConnected) h.el.remove();
        continue;
      }
      const rect = h.node.getBoundingClientRect();
      h.el.style.left = rect.left + 'px';
      h.el.style.top = rect.top + 'px';
      h.el.style.width = rect.width + 'px';
      h.el.style.height = rect.height + 'px';
      active.push(h);
    }
    editorHighlights = active;
  }

  // ─── Active anchor persistent highlight (anchor-first capture) ───
  // Distinct from the 3s verify highlight: stays until the anchor is cleared or
  // the side panel closes, and follows layout via requestAnimationFrame.

  let anchorHighlightEls = [];   // overlay divs, index-aligned with anchorHighlightNodes
  let anchorHighlightNodes = []; // tracked anchor DOM instances
  let anchorHighlightRAF = null;

  function clearActiveAnchorHighlights() {
    if (anchorHighlightRAF) { cancelAnimationFrame(anchorHighlightRAF); anchorHighlightRAF = null; }
    anchorHighlightEls.forEach((el) => el.remove());
    document.querySelectorAll('.rpa-anchor-highlight').forEach((el) => el.remove());
    anchorHighlightEls = [];
    anchorHighlightNodes = [];
  }

  function renderActiveAnchorHighlights(nodes) {
    clearActiveAnchorHighlights();
    anchorHighlightNodes = (nodes || []).filter((n) => n && n.getBoundingClientRect);
    anchorHighlightNodes.forEach(() => {
      const hl = document.createElement('div');
      hl.className = 'rpa-anchor-highlight';
      hl.style.cssText = `
        position: fixed; pointer-events: none; z-index: 2147483645;
        border: 2px solid #fa8c16; background: rgba(250,140,22,0.10);
        box-sizing: border-box; border-radius: 2px;
      `;
      document.body.appendChild(hl);
      anchorHighlightEls.push(hl);
    });
    if (!anchorHighlightNodes.length) return;
    const tick = () => {
      for (let i = 0; i < anchorHighlightNodes.length; i++) {
        const node = anchorHighlightNodes[i];
        const box = anchorHighlightEls[i];
        if (!box) continue;
        if (!node.isConnected) { box.style.display = 'none'; continue; }
        const r = node.getBoundingClientRect();
        box.style.display = 'block';
        box.style.left = r.left + 'px';
        box.style.top = r.top + 'px';
        box.style.width = r.width + 'px';
        box.style.height = r.height + 'px';
      }
      // Keep following layout only while an anchor is active.
      anchorHighlightRAF = activeAnchor ? requestAnimationFrame(tick) : null;
    };
    anchorHighlightRAF = requestAnimationFrame(tick);
  }

  function resolveAllForVerify(selector, type) {
    try {
      if (type === 'css' || !type) {
        const s = selector.startsWith('css:') ? selector.slice(4) : selector;
        return Array.from(document.querySelectorAll(s)).filter(isRenderedVisible);
      }
      if (type === 'xpath') {
        const s = selector.startsWith('xpath:') ? selector.slice(6) : selector;
        const r = document.evaluate(s, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        const arr = [];
        for (let i = 0; i < r.snapshotLength; i++) {
          const node = r.snapshotItem(i);
          if (isRenderedVisible(node)) arr.push(node);
        }
        return arr;
      }
      if (type === 'id') {
        const s = selector.startsWith('#') ? selector : '#' + selector;
        const el = document.querySelector(s);
        return el ? [el] : [];
      }
      if (type === 'class') {
        const s = selector.startsWith('.') ? selector : '.' + selector;
        return Array.from(document.querySelectorAll(s));
      }
      if (type === 'data-attr' || type === 'aria' || type === 'name') {
        let l = selector;
        if (l.startsWith('@')) l = l.slice(1);
        const eq = l.indexOf('=');
        if (eq > 0) {
          return Array.from(document.querySelectorAll(`[${l.slice(0, eq)}="${attrValueEscape(l.slice(eq + 1))}"]`));
        }
        return [];
      }
      if (type === 'tag_attr') {
        const m = selector.match(/^tag:(\w+)@([\w\-:]+)=(.+)$/);
        if (m) return Array.from(document.querySelectorAll(`${m[1]}[${m[2]}="${attrValueEscape(m[3])}"]`));
        return [];
      }
      if (type === 'tag_class') {
        const m = selector.match(/^tag:(\w+)@class=(.+)$/);
        if (m) return Array.from(document.querySelectorAll(`${m[1]}.${m[2]}`));
        return [];
      }
      if (type === 'tag_text') {
        const m = selector.match(/^tag:(\w+)@text\(\)=(.+)$/);
        if (m) {
          const r = document.evaluate(`//${m[1]}[contains(text(), ${JSON.stringify(m[2])})]`, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
          const arr = [];
          for (let i = 0; i < r.snapshotLength; i++) {
            const node = r.snapshotItem(i);
            if (isRenderedVisible(node)) arr.push(node);
          }
          return arr;
        }
        return [];
      }
      if (type === 'text') {
        const text = selector.startsWith('text=') ? selector.slice(5) : selector;
        const r = document.evaluate(`//*[contains(text(), ${JSON.stringify(text)})]`, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        const arr = [];
        for (let i = 0; i < r.snapshotLength; i++) {
          const node = r.snapshotItem(i);
          if (isRenderedVisible(node)) arr.push(node);
        }
        return arr;
      }
      if (type === 'multi_attr') {
        const parts = selector.match(/@@class:([^@]+)/g);
        if (parts) {
          const s = parts.map(p => '.' + p.replace('@@class:', '')).join('');
          return Array.from(document.querySelectorAll(s));
        }
        return [];
      }
      if (type === 'verse') {
        const fp = selector.replace(/^verse:/, '');
        const nodes = document.querySelectorAll('body, body *');
        const arr = [];
        let checked = 0;
        for (const node of nodes) {
          if (checked++ > 20000) break;
          const text = (node.innerText || node.textContent || '').trim();
          if (text.length > 5 && generateVerseFingerprint(text) === fp) {
            arr.push(node);
          }
        }
        return arr;
      }
      if (selector.startsWith('css:')) {
        return Array.from(document.querySelectorAll(selector.slice(4)));
      }
      if (selector.startsWith('xpath:')) {
        const r = document.evaluate(selector.slice(6), document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        const arr = [];
        for (let i = 0; i < r.snapshotLength; i++) arr.push(r.snapshotItem(i));
        return arr;
      }
      return Array.from(document.querySelectorAll(selector));
    } catch (e) {
      return [];
    }
  }

  function resolveAllForVerifyStats(selector, type) {
    try {
      let all = [];
      if (type === 'css' || !type) {
        const s = selector.startsWith('css:') ? selector.slice(4) : selector;
        all = Array.from(document.querySelectorAll(s));
      } else if (type === 'xpath') {
        const s = selector.startsWith('xpath:') ? selector.slice(6) : selector;
        const r = document.evaluate(s, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        for (let i = 0; i < r.snapshotLength; i++) all.push(r.snapshotItem(i));
      } else if (type === 'text') {
        const text = selector.startsWith('text=') ? selector.slice(5) : selector;
        const r = document.evaluate(`//*[contains(text(), ${JSON.stringify(text)})]`, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        for (let i = 0; i < r.snapshotLength; i++) all.push(r.snapshotItem(i));
      } else if (type === 'tag_text') {
        const m = selector.match(/^tag:(\w+)@text\(\)=(.+)$/);
        if (m) {
          const r = document.evaluate(`//${m[1]}[contains(text(), ${JSON.stringify(m[2])})]`, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
          for (let i = 0; i < r.snapshotLength; i++) all.push(r.snapshotItem(i));
        }
      } else {
        all = resolveAllForVerify(selector, type);
      }
      const visible = all.filter(isRenderedVisible);
      const invisible = all.filter((n) => !isRenderedVisible(n));
      return { total: all.length, visible: visible.length, invisible: invisible.length };
    } catch (e) {
      return { total: 0, visible: 0, invisible: 0 };
    }
  }

  function resolveLocatorForVerify(selector, type) {
    const all = resolveAllForVerify(selector, type);
    return all[0] || null;
  }

  function splitSelectorPrefix(sel) {
    if (!sel) return { bare: '', family: 'css' };
    const lowered = sel.toLowerCase();
    if (lowered.startsWith('css:')) return { bare: sel.slice(4).trim(), family: 'css' };
    if (lowered.startsWith('xpath:')) return { bare: sel.slice(6).trim(), family: 'xpath' };
    if (lowered.startsWith('drission:')) return { bare: sel.slice(9).trim(), family: 'css' };
    const bare = sel.trim();
    if (bare.startsWith('//') || bare.startsWith('.//')) return { bare, family: 'xpath' };
    return { bare, family: 'css' };
  }

  function queryRelativeInItem(item, relativeSelector) {
    const { bare, family } = splitSelectorPrefix(relativeSelector);
    if (family === 'xpath') {
      const r = document.evaluate(bare, item, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
      const arr = [];
      for (let i = 0; i < r.snapshotLength; i++) arr.push(r.snapshotItem(i));
      return arr;
    }
    return Array.from(item.querySelectorAll(bare));
  }

  /**
   * Resolve a selector chain from the outermost root down to the innermost
   * anchor. Each chain node is { selector: 'css:...' | 'xpath:...' }.
   */
  function resolveSelectorChain(chain) {
    if (!chain || !chain.length) return [];
    let contexts = [document];
    for (const node of chain) {
      const sel = node.selector || '';
      if (!sel) return [];
      const next = [];
      for (const ctx of contexts) {
        const scope = (ctx === document) ? document : ctx;
        const matches = queryRelativeInItem(scope, sel);
        for (const m of matches) next.push(m);
      }
      contexts = next;
      if (!contexts.length) break;
    }
    return contexts.filter((el) => el && el.nodeType === 1);
  }

  function verifyRelativeSelector(anchorSelector, relativeSelector, anchorChain) {
    if ((!anchorSelector && (!anchorChain || !anchorChain.length)) || !relativeSelector) {
      return { total: 0, perItem: [], error: '锚点或相对选择器为空' };
    }
    let anchors = [];
    if (anchorChain && anchorChain.length) {
      anchors = resolveSelectorChain(anchorChain);
    } else {
      const { bare: anchorBare, family: anchorFamily } = splitSelectorPrefix(anchorSelector);
      anchors = anchorFamily === 'xpath'
        ? (() => {
            const r = document.evaluate(anchorBare, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
            const arr = [];
            for (let i = 0; i < r.snapshotLength; i++) arr.push(r.snapshotItem(i));
            return arr;
          })()
        : Array.from(document.querySelectorAll(anchorBare));
    }

    let total = 0;
    let uniqueItems = 0;
    let emptyItems = 0;
    const perItem = [];
    const matchedElements = [];
    for (const item of anchors) {
      const found = queryRelativeInItem(item, relativeSelector);
      total += found.length;
      if (found.length === 1) uniqueItems++;
      if (found.length === 0) emptyItems++;
      perItem.push(found.length);
      matchedElements.push(...found);
    }
    return {
      total,
      anchorCount: anchors.length,
      uniqueItems,
      emptyItems,
      perItem,
      matchedElements,
    };
  }

  function highlightSelectorMatches(selector, type) {
    // DEBUG: inject a visible marker to confirm this function runs
    try { const _dbg=document.createElement("div");_dbg.id="rpa-debug-marker";_dbg.textContent="✅ RPA verify running";_dbg.style.cssText="position:fixed;top:10px;right:10px;z-index:99999999;background:red;color:white;padding:8px 16px;font-size:16px;font-weight:bold;border-radius:4px";(document.body||document.documentElement).appendChild(_dbg);setTimeout(()=>_dbg.remove(),3000); } catch(_){}
    console.log('[RPA Capture] highlightSelectorMatches: selector=' + selector + ' type=' + type);
    removeEditorHighlights();
    const nodes = resolveAllForVerify(selector, type);
    console.log('[RPA Capture] highlightSelectorMatches: found ' + nodes.length + ' nodes');

    nodes.forEach((node) => {
      if (!node.getBoundingClientRect) return;
      const rect = node.getBoundingClientRect();
      const hl = document.createElement('div');
      hl.className = 'rpa-editor-highlight';
      hl.style.setProperty('position', 'fixed', 'important');
      hl.style.setProperty('pointer-events', 'none', 'important');
      hl.style.setProperty('z-index', '2147483646', 'important');
      hl.style.setProperty('left', rect.left + 'px', 'important');
      hl.style.setProperty('top', rect.top + 'px', 'important');
      hl.style.setProperty('width', rect.width + 'px', 'important');
      hl.style.setProperty('height', rect.height + 'px', 'important');
      hl.style.setProperty('border', '3px solid #1677ff', 'important');
      hl.style.setProperty('background', 'rgba(22,119,255,0.15)', 'important');
      hl.style.setProperty('box-sizing', 'border-box', 'important');
      const parent = document.body || document.documentElement;
      if (parent) parent.appendChild(hl);
      else console.warn('[RPA Capture] highlight: no body or documentElement');
      editorHighlights.push({ node, el: hl });
    });

    if (editorHighlightTimer) clearTimeout(editorHighlightTimer);
    editorHighlightTimer = setTimeout(removeEditorHighlights, 3000);
  }

  function highlightRelativeMatches(elements) {
    removeEditorHighlights();
    elements.forEach((node) => {
      if (!node.getBoundingClientRect) return;
      const rect = node.getBoundingClientRect();
      const hl = document.createElement('div');
      hl.className = 'rpa-editor-highlight';
      hl.style.cssText = `
        position: fixed; pointer-events: none; z-index: 2147483646;
        left: ${rect.left}px; top: ${rect.top}px;
        width: ${rect.width}px; height: ${rect.height}px;
        border: 2px dashed #1677ff; background: rgba(22,119,255,0.08);
        box-sizing: border-box;
      `;
      document.body.appendChild(hl);
      editorHighlights.push({ node, el: hl });
    });

    if (editorHighlightTimer) clearTimeout(editorHighlightTimer);
    editorHighlightTimer = setTimeout(removeEditorHighlights, 3000);
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

  document.addEventListener('mousemove', (e) => {
    lastMouseX = e.clientX;
    lastMouseY = e.clientY;
  });

  async function triggerQuickCapture() {
    if (!captureEnabled) return;
    let el = lockedElement;
    if (!el && lastMouseX >= 0 && lastMouseY >= 0) {
      const stack = document.elementsFromPoint(lastMouseX, lastMouseY);
      el = stack.find((elm) => elm !== document.body && elm !== document.documentElement && !elm.closest('#rpa-capture-highlight-host'));
    }
    if (!el) {
      showToast('没有可捕获的元素');
      return;
    }
    if (captureMode) exitCaptureMode();
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    await performCapture(el);
  }

  async function triggerQuickVerify() {
    if (!captureEnabled) return;
    const target = activeCandidate || lastCapturePayload?.candidates?.[0];
    if (!target) {
      showToast('没有可校验的选择器，请先捕获元素');
      return;
    }
    const selector = activeCandidate ? target.selector : target.syntax;
    const type = activeCandidate ? target.type : target.family;
    const stats = resolveAllForVerifyStats(selector, type);
    highlightSelectorMatches(selector, type);
    const parts = [];
    if (stats.visible > 0) parts.push(`${stats.visible} 个可见`);
    if (stats.invisible > 0) parts.push(`${stats.invisible} 个不可见`);
    if (parts.length === 0) parts.push('0 个');
    showToast(`校验结果: ${parts.join('，')} (共 ${stats.total} 个)`);
    try {
      chrome.runtime.sendMessage({ action: 'verifyResult', payload: { ...stats, matchedSelector: selector } }).catch(() => {});
    } catch (_e) {}
  }

  document.addEventListener('keydown', (e) => {
    if (e.altKey && (e.key === '1')) {
      e.preventDefault();
      triggerQuickCapture();
      return;
    }
    if (e.altKey && (e.key === '2')) {
      e.preventDefault();
      triggerQuickVerify();
      return;
    }
    if (e.key === 'Alt') {
      if (!captureEnabled) return;
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
    if (message.action === 'setCaptureEnabled') {
      captureEnabled = message.enabled;
      if (!captureEnabled && captureMode) exitCaptureMode();
      if (!captureEnabled) { activeAnchor = null; clearActiveAnchorHighlights(); }
      sendResponse({ ok: true });
      return false;
    }
    if (message.action === 'setActiveAnchor') {
      const { anchorSelector, anchorElementName, anchorChain } = message.payload || {};
      if ((!anchorSelector || !anchorSelector.trim()) && (!anchorChain || !anchorChain.length)) {
        activeAnchor = null;
        clearActiveAnchorHighlights();
        sendResponse({ ok: true, count: 0 });
        return false;
      }
      if (anchorChain && anchorChain.length) {
        const finalEls = resolveSelectorChain(anchorChain);
        const last = anchorChain[anchorChain.length - 1] || {};
        const { family } = splitSelectorPrefix(last.selector || '');
        activeAnchor = {
          name: anchorElementName || '',
          selector: last.selector || '',
          family,
          elements: finalEls,
          chain: anchorChain,
        };
        renderActiveAnchorHighlights(finalEls);
        sendResponse({ ok: true, count: finalEls.length });
        return false;
      }
      const family = splitSelectorPrefix(anchorSelector).family;
      let els = [];
      try { els = resolveAllForVerify(anchorSelector, family); } catch (_e) { els = []; }
      activeAnchor = { name: anchorElementName || '', selector: anchorSelector, family, elements: els };
      renderActiveAnchorHighlights(els);
      sendResponse({ ok: true, count: els.length });
      return false;
    }
    if (message.action === 'selectCandidate') {
      activeCandidate = message.payload || null;
      sendResponse({ ok: true });
      return false;
    }
    if (message.action === 'triggerCapture') {
      if (!captureEnabled) { sendResponse({ ok: false, error: 'side panel not open' }); return false; }
      triggerQuickCapture().then(() => sendResponse({ ok: true })).catch((err) => sendResponse({ error: err.message }));
      return true;
    }
    if (message.action === 'triggerVerify') {
      if (!captureEnabled) { sendResponse({ ok: false, error: 'side panel not open' }); return false; }
      triggerQuickVerify().then(() => sendResponse({ ok: true })).catch((err) => sendResponse({ error: err.message }));
      return true;
    }
    if (message.action === 'elementCaptured') {
      console.log('[RPA Capture] received broadcast, posting to page');
      window.postMessage(
        { source: 'rpa-extension', type: 'elementCaptured', detail: message.payload },
        '*'
      );
      sendResponse({ dispatched: true });
      return false;
    }
    if (message.action === 'verifyElement') {
      console.log('[RPA Capture] verifyElement received:', JSON.stringify(message.payload).slice(0, 200));
      let { selector, type } = message.payload || {};
      // 若选择器带显式前缀，以后缀推断 family，覆盖侧板可能传错的 type
      const inferred = splitSelectorPrefix(selector).family;
      if (inferred === 'css' || inferred === 'xpath') type = inferred;
      console.log('[RPA Capture] verifyElement: selector=' + selector + ' type=' + type + ' inferred=' + inferred);
      let stats = { total: 0, visible: 0, invisible: 0 };
      let matchedSelector = selector;
      // 支持多选择器数组：逐个试，命中即停
      if (Array.isArray(selector) && selector.length > 0) {
        for (const sel of selector) {
          const selType = splitSelectorPrefix(sel).family || type;
          const s = resolveAllForVerifyStats(sel, selType);
          console.log('[RPA Capture] verifyElement multi: sel=' + sel + ' selType=' + selType + ' total=' + s.total);
          if (s.total > 0) {
            stats = s;
            matchedSelector = sel;
            highlightSelectorMatches(sel, selType);
            break;
          }
        }
      } else {
        stats = resolveAllForVerifyStats(selector, type);
        console.log('[RPA Capture] verifyElement single: total=' + stats.total + ' visible=' + stats.visible);
        highlightSelectorMatches(selector, type);
      }
      console.log('[RPA Capture] verifyElement done: total=' + stats.total + ' matchedSelector=' + matchedSelector);
      sendResponse({ ...stats, matchedSelector });
      // Also broadcast result so side panel can pick it up
      chrome.runtime.sendMessage({ action: 'verifyResult', payload: { ...stats, matchedSelector } }).catch(() => {});
      return false;
    }

    if (message.action === 'recomputeAnchor') {
      const { selector, selectorFamily } = message.payload || {};
      try {
        const el = resolveLocatorForVerify(selector, selectorFamily);
        if (!el) {
          sendResponse({ error: '当前选择器未匹配到元素' });
          return false;
        }
        const listFamily = detectListFamily(el, { maxDepth: 6, minItems: 2, similarityThreshold: 0.55 });
        const rel = computeRelativeSelector(el, listFamily);
        if (!rel) {
          sendResponse({ error: '未找到稳定的循环锚点' });
          return false;
        }
        sendResponse({ relativeSelector: rel.relative, anchorSelector: rel.anchor, family: rel.family });
      } catch (e) {
        sendResponse({ error: e?.message || String(e) });
      }
      return false;
    }

    if (message.action === 'computeRelativeFromAnchor') {
      const { targetSelector, anchorSelector, anchorChain } = message.payload || {};
      try {
        const targetEl = resolveLocatorForVerify(targetSelector, splitSelectorPrefix(targetSelector).family);
        let anchors = [];
        if (anchorChain && anchorChain.length) {
          anchors = resolveSelectorChain(anchorChain);
        } else {
          anchors = [resolveLocatorForVerify(anchorSelector, splitSelectorPrefix(anchorSelector).family)].filter(Boolean);
        }
        if (!targetEl || !anchors.length) {
          sendResponse({ error: '目标元素或锚点元素未匹配' });
          return false;
        }
        const anchorEl = anchors.find((a) => a === targetEl || a.contains(targetEl));
        if (!anchorEl) {
          sendResponse({ error: '目标元素不在所选锚点元素内部' });
          return false;
        }
        let relative = null;
        let family = null;
        const relCss = buildRelativeCss(anchorEl, targetEl);
        if (relCss) {
          relative = 'css:' + relCss;
          family = 'css';
        } else {
          const relXp = buildRelativeXPath(anchorEl, targetEl);
          if (relXp) {
            relative = 'xpath:' + relXp;
            family = 'xpath';
          }
        }
        if (!relative) {
          sendResponse({ error: '无法构建稳定的相对选择器' });
          return false;
        }
        sendResponse({ relativeSelector: relative, family });
      } catch (e) {
        sendResponse({ error: e?.message || String(e) });
      }
      return false;
    }

    if (message.action === 'verifyRelative') {
      const { anchorSelector, relativeSelector, anchorChain } = message.payload || {};
      try {
        const result = verifyRelativeSelector(anchorSelector, relativeSelector, anchorChain);
        if (result.matchedElements?.length) {
          highlightRelativeMatches(result.matchedElements);
        }
        sendResponse(result);
      } catch (e) {
        sendResponse({ error: e?.message || String(e), total: 0 });
      }
      return false;
    }
  });

  // 页面刷新/导航后，主动向 background 查询 side panel 是否已打开
  //（避免 side panel 已打开但新页面收不到 setCaptureEnabled 广播）
  try {
    chrome.runtime.sendMessage({ action: 'queryCaptureState' })
      .then((resp) => {
        if (resp?.captureEnabled) {
          captureEnabled = true;
          console.log('[RPA Capture] side panel already open, capture enabled');
        }
      })
      .catch(() => {});
  } catch (_e) {}

  console.log('[RPA Capture] 捕获模块已加载，按 Alt 进入捕获模式');
})();
