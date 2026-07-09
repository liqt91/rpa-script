/**
 * RPA Script Browser Agent — Content Script
 *
 * Executes automation steps inside the page context.
 * Invoked by background.js via chrome.tabs.sendMessage.
 */

(function () {
  'use strict';

  // Prevent double-injection
  if (window.__rpaAgentInjected) return;
  window.__rpaAgentInjected = true;

  const AGENT_VERSION = '1.0.0';

  // ─── Locator resolution ──────────────────────────────────────────

  function isRendered(el) {
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
    if (el.disabled === true || el.readOnly === true || el.getAttribute('tabindex') === '-1' || el.hasAttribute('inert')) return false;
    return true;
  }

  function isInViewport(el) {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    return !(
      rect.width <= 0 || rect.height <= 0 ||
      rect.bottom < 0 || rect.top > window.innerHeight ||
      rect.right < 0 || rect.left > window.innerWidth
    );
  }

  function isVisible(el) {
    return isRendered(el) && isInViewport(el);
  }

  function checkVisibility(el, mode) {
    if (!el || mode === 'any') return true;
    return isRendered(el);
  }

  function getVisibilityMode(extra) {
    if (extra?.visibilityMode) {
      const m = extra.visibilityMode;
      // backwards compatibility for old saved values
      if (m === 'rendered' || m === 'viewport') return 'visible';
      return m;
    }
    if (extra?.visibleOnly === false) return 'any';
    return 'visible';
  }

  function getElementXPath(el) {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return '';
    const parts = [];
    let node = el;
    while (node && node.nodeType === Node.ELEMENT_NODE) {
      let index = 1;
      let sibling = node.previousSibling;
      while (sibling) {
        if (sibling.nodeType === Node.ELEMENT_NODE && sibling.localName === node.localName) {
          index += 1;
        }
        sibling = sibling.previousSibling;
      }
      parts.unshift(`${node.localName.toLowerCase()}[${index}]`);
      node = node.parentNode;
    }
    return 'xpath:/' + parts.join('/');
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

  function normalizeLocator(locator) {
    if (Array.isArray(locator) && locator.length > 0) {
      const first = locator[0];
      if (first && typeof first === 'object') {
        return first.locator || first.syntax || first.selector || '';
      }
      if (typeof first === 'string') return first;
    }
    return locator;
  }

  function normalizeSelectorFamily(locator, selectorFamily) {
    if (selectorFamily) return selectorFamily;
    if (Array.isArray(locator) && locator.length > 0) {
      const first = locator[0];
      if (first && typeof first === 'object') {
        return first.selectorFamily || first.selectorFamily || first.type || 'css';
      }
    }
    return 'css';
  }

  function inferSelectorFamily(locator) {
    locator = normalizeLocator(locator);
    if (!locator || typeof locator !== 'string') return 'css';
    if (locator.startsWith('css:')) return 'css';
    if (locator.startsWith('xpath:') || locator.startsWith('//') || locator.startsWith('/')) return 'xpath';
    if (locator.startsWith('@') || locator.startsWith('tag:') || locator.startsWith('verse:') || locator.startsWith('text=') || locator.startsWith('@@class:')) return 'drission';
    return 'css';
  }

  function resolveAllLocators(locator, selectorFamily) {
    locator = normalizeLocator(locator);
    selectorFamily = normalizeSelectorFamily(locator, selectorFamily);
    if (!locator) return [];
    if (locator.startsWith('css:')) { locator = locator.slice(4); selectorFamily = 'css'; }
    if (locator.startsWith('xpath:')) { locator = locator.slice(6); selectorFamily = 'xpath'; }
    const inferred = inferSelectorFamily(locator);
    if (inferred && inferred !== selectorFamily) selectorFamily = inferred;

    if (selectorFamily === 'xpath') {
      const r = document.evaluate(locator, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
      const arr = [];
      for (let i = 0; i < r.snapshotLength; i++) arr.push(r.snapshotItem(i));
      return arr;
    }
    if (selectorFamily === 'drission') {
      if (locator.startsWith('verse:')) {
        const fp = locator.replace(/^verse:/, '');
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
      if (locator.startsWith('text=')) {
        const text = locator.slice(5);
        const r = document.evaluate(`//*[contains(text(), ${JSON.stringify(text)})]`, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        const arr = [];
        for (let i = 0; i < r.snapshotLength; i++) arr.push(r.snapshotItem(i));
        return arr;
      }
      const m = locator.match(/^tag:(\w+)@text\(\)=(.+)$/);
      if (m) {
        const r = document.evaluate(`//${m[1]}[contains(text(), ${JSON.stringify(m[2])})]`, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        const arr = [];
        for (let i = 0; i < r.snapshotLength; i++) arr.push(r.snapshotItem(i));
        return arr;
      }
      let selector = locator;
      if (locator.startsWith('@')) {
        const l = locator.slice(1);
        const eq = l.indexOf('=');
        if (eq > 0) {
          selector = `[${l.slice(0, eq)}=${JSON.stringify(l.slice(eq + 1))}]`;
        } else {
          selector = `[data-${l}]`;
        }
      } else {
        const m1 = locator.match(/^tag:(\w+)@class=(.+)$/);
        if (m1) selector = `${m1[1]}.${m1[2]}`;
        else {
          const m2 = locator.match(/^tag:(\w+)@(\w+)=(.+)$/);
          if (m2) selector = `${m2[1]}[${m2[2]}=${JSON.stringify(m2[3])}]`;
          else {
            const parts = locator.match(/@@class:([^@]+)/g);
            if (parts) selector = parts.map(p => '.' + p.replace('@@class:', '')).join('');
          }
        }
      }
      try { return Array.from(document.querySelectorAll(selector)); } catch (e) {}
      return [];
    }

    // css family
    try { return Array.from(document.querySelectorAll(locator)); } catch (e) {}
    return [];
  }

  function resolveLocator(locator, selectorFamily, mode) {
    locator = normalizeLocator(locator);
    selectorFamily = normalizeSelectorFamily(locator, selectorFamily);
    if (!locator) return document;

    // Normalize css:/xpath: prefixes
    if (locator.startsWith('css:')) {
      locator = locator.slice(4);
      selectorFamily = 'css';
    }
    if (locator.startsWith('xpath:')) {
      locator = locator.slice(6);
      selectorFamily = 'xpath';
    }
    const inferred = inferSelectorFamily(locator);
    if (inferred && inferred !== selectorFamily) selectorFamily = inferred;

    let el = null;
    switch (selectorFamily) {
      case 'xpath':
        el = document.evaluate(locator, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        break;
      case 'drission': {
        if (locator.startsWith('verse:')) {
          const fp = locator.replace(/^verse:/, '');
          const nodes = document.querySelectorAll('body, body *');
          let checked = 0;
          for (const node of nodes) {
            if (checked++ > 20000) break;
            const text = (node.innerText || node.textContent || '').trim();
            if (text.length > 5 && generateVerseFingerprint(text) === fp) {
              el = node;
              break;
            }
          }
        } else if (locator.startsWith('text=')) {
          const text = locator.slice(5);
          el = document.evaluate(`//*[contains(text(), ${JSON.stringify(text)})]`, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        } else if (/^tag:(\w+)@text\(\)=(.+)$/.test(locator)) {
          const m = locator.match(/^tag:(\w+)@text\(\)=(.+)$/);
          if (m) {
            el = document.evaluate(`//${m[1]}[contains(text(), ${JSON.stringify(m[2])})]`, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
          }
        } else {
          const css = drissionToCss(locator);
          if (css) el = document.querySelector(css);
        }
        break;
      }
      case 'css':
      default:
        el = document.querySelector(locator);
    }

    if (!el) {
      try { el = document.querySelector(locator); } catch (e) {}
      try { el = document.evaluate(locator, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; } catch (e) {}
    }

    if (!el || mode === 'any') return el;
    if (!checkVisibility(el, mode)) {
      const all = resolveAllLocators(locator, selectorFamily);
      const v = all.find(e => checkVisibility(e, mode));
      if (v) return v;
    }
    return el;
  }

  function waitForElement(locator, selectorFamily, mode, timeoutMs = 10000, pollMs = 200) {
    locator = normalizeLocator(locator);
    selectorFamily = normalizeSelectorFamily(locator, selectorFamily);
    console.log(`[RPA waitForElement] normLocator=${locator} normType=${selectorFamily} mode=${mode} timeout=${timeoutMs}`);
    const start = Date.now();
    let ticks = 0;
    return new Promise((resolve, reject) => {
      const tick = () => {
        ticks++;
        const el = resolveLocator(locator, selectorFamily, mode);
        if (el && el !== document) {
          console.log(`[RPA waitForElement] FOUND after ${ticks} ticks, ${Date.now() - start}ms`);
          return resolve(el);
        }
        if (Date.now() - start >= timeoutMs) {
          console.log(`[RPA waitForElement] TIMEOUT after ${ticks} ticks, ${Date.now() - start}ms`);
          return reject(new Error(`元素未在 ${timeoutMs}ms 内出现: ${locator}`));
        }
        setTimeout(tick, pollMs);
      };
      tick();
    });
  }

  // ─── Relative/context element resolution ─────────────────────────

  function resolveLocatorInContext(locator, selectorFamily, rootElement) {
    locator = normalizeLocator(locator);
    selectorFamily = normalizeSelectorFamily(locator, selectorFamily);
    if (!rootElement) return resolveLocator(locator, selectorFamily, true);

    // Normalize css:/xpath: prefixes
    let l = locator;
    let lt = selectorFamily;
    if (l.startsWith('css:')) { l = l.slice(4); lt = 'css'; }
    if (l.startsWith('xpath:')) { l = l.slice(6); lt = 'xpath'; }
    const inferred = inferSelectorFamily(l);
    if (inferred && inferred !== lt) lt = inferred;

    let el = null;
    switch (lt) {
      case 'xpath': {
        let xl = l;
        if (xl.startsWith('//')) xl = '.' + xl;
        el = document.evaluate(xl, rootElement, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        break;
      }
      case 'drission': {
        if (l.startsWith('verse:')) {
          const fp = l.replace(/^verse:/, '');
          const walker = document.createTreeWalker(rootElement, NodeFilter.SHOW_ELEMENT, null, false);
          let checked = 0;
          while (walker.nextNode()) {
            if (checked++ > 5000) break;
            const node = walker.currentNode;
            const text = (node.innerText || node.textContent || '').trim();
            if (text.length > 5 && generateVerseFingerprint(text) === fp) {
              el = node;
              break;
            }
          }
        } else if (l.startsWith('text=')) {
          const text = l.slice(5);
          const walker = document.createTreeWalker(rootElement, NodeFilter.SHOW_ELEMENT, null, false);
          while (walker.nextNode()) {
            const node = walker.currentNode;
            if ((node.textContent || '').includes(text)) { el = node; break; }
          }
        } else {
          let selector = l;
          if (l.startsWith('@')) {
            const attr = l.slice(1);
            const eq = attr.indexOf('=');
            if (eq > 0) {
              selector = `[${attr.slice(0, eq)}=${JSON.stringify(attr.slice(eq + 1))}]`;
            } else {
              selector = `[data-${attr}]`;
            }
          } else {
            const m1 = l.match(/^tag:(\w+)@class=(.+)$/);
            if (m1) selector = `${m1[1]}.${m1[2]}`;
            else {
              const m2 = l.match(/^tag:(\w+)@(\w+)=(.+)$/);
              if (m2) selector = `${m2[1]}[${m2[2]}=${JSON.stringify(m2[3])}]`;
              else {
                const parts = l.match(/@@class:([^@]+)/g);
                if (parts) selector = parts.map(p => '.' + p.replace('@@class:', '')).join('');
              }
            }
          }
          el = rootElement.querySelector(selector);
        }
        break;
      }
      case 'css':
      default:
        el = rootElement.querySelector(l);
    }
    return el;
  }

  function resolveAllLocatorsInContext(locator, selectorFamily, rootElement) {
    locator = normalizeLocator(locator);
    selectorFamily = normalizeSelectorFamily(locator, selectorFamily);
    if (!rootElement) return resolveAllLocators(locator, selectorFamily);

    let l = locator;
    let lt = selectorFamily;
    if (l.startsWith('css:')) { l = l.slice(4); lt = 'css'; }
    if (l.startsWith('xpath:')) { l = l.slice(6); lt = 'xpath'; }
    const inferred = inferSelectorFamily(l);
    if (inferred && inferred !== lt) lt = inferred;

    if (lt === 'xpath') {
      let xl = l;
      // If the XPath was captured as an absolute document path (//...), evaluating it
      // relative to a context element with './/...' would fail because the path includes
      // ancestor nodes outside the context. Always evaluate against document and then
      // filter to descendants of the context element.
      const r = document.evaluate(xl, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
      const arr = [];
      for (let i = 0; i < r.snapshotLength; i++) {
        const node = r.snapshotItem(i);
        if (rootElement.contains(node)) arr.push(node);
      }
      return arr;
    }
    if (lt === 'drission') {
      if (l.startsWith('verse:')) {
        const fp = l.replace(/^verse:/, '');
        const walker = document.createTreeWalker(rootElement, NodeFilter.SHOW_ELEMENT, null, false);
        const arr = [];
        let checked = 0;
        while (walker.nextNode()) {
          if (checked++ > 5000) break;
          const node = walker.currentNode;
          const text = (node.innerText || node.textContent || '').trim();
          if (text.length > 5 && generateVerseFingerprint(text) === fp) {
            arr.push(node);
          }
        }
        return arr;
      }
      if (l.startsWith('text=')) {
        const text = l.slice(5);
        const walker = document.createTreeWalker(rootElement, NodeFilter.SHOW_ELEMENT, null, false);
        const arr = [];
        while (walker.nextNode()) {
          const node = walker.currentNode;
          if ((node.textContent || '').includes(text)) arr.push(node);
        }
        return arr;
      }
      const m = l.match(/^tag:(\w+)@text\(\)=(.+)$/);
      if (m) {
        const walker = document.createTreeWalker(rootElement, NodeFilter.SHOW_ELEMENT, {
          acceptNode: (node) => node.tagName.toLowerCase() === m[1].toLowerCase() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP
        }, false);
        const arr = [];
        while (walker.nextNode()) {
          const node = walker.currentNode;
          if ((node.textContent || '').includes(m[2])) arr.push(node);
        }
        return arr;
      }
      let selector = l;
      if (l.startsWith('@')) {
        const attr = l.slice(1);
        const eq = attr.indexOf('=');
        if (eq > 0) {
          selector = `[${attr.slice(0, eq)}=${JSON.stringify(attr.slice(eq + 1))}]`;
        } else {
          selector = `[data-${attr}]`;
        }
      } else {
        const m1 = l.match(/^tag:(\w+)@class=(.+)$/);
        if (m1) selector = `${m1[1]}.${m1[2]}`;
        else {
          const m2 = l.match(/^tag:(\w+)@(\w+)=(.+)$/);
          if (m2) selector = `${m2[1]}[${m2[2]}=${JSON.stringify(m2[3])}]`;
          else {
            const parts = l.match(/@@class:([^@]+)/g);
            if (parts) selector = parts.map(p => '.' + p.replace('@@class:', '')).join('');
          }
        }
      }
      try { return Array.from(rootElement.querySelectorAll(selector)); } catch (e) {}
      return [];
    }

    // css family
    try { return Array.from(rootElement.querySelectorAll(l)); } catch (e) {}
    return [];
  }

  // True relative query: evaluate a capture-time relative selector strictly
  // *within* the loop-item parent, rather than the legacy global-evaluate +
  // parent.contains() filter. Unifies xpath/css/drission scope semantics so a
  // child selector cannot leak across sibling loop items.
  function resolveAllRelativeInContext(relLocator, relFamily, rootElement) {
    if (!rootElement || !relLocator) return [];
    let l = String(relLocator).trim();
    let lt = relFamily || '';
    if (l.startsWith('css:')) { l = l.slice(4); lt = 'css'; }
    else if (l.startsWith('xpath:')) { l = l.slice(6); lt = 'xpath'; }
    else if (l.startsWith('drission:')) { l = l.slice(9); lt = 'drission'; }
    if (!lt) lt = inferSelectorFamily(l) || 'css';

    if (lt === 'xpath') {
      // Force the path to evaluate relative to the context node.
      let xl = l;
      if (xl.startsWith('.//') || xl.startsWith('./')) {
        // already relative
      } else if (xl.startsWith('//')) {
        xl = '.' + xl;            // //div -> .//div
      } else if (xl.startsWith('/')) {
        xl = '.' + xl;            // /div  -> ./div
      } else {
        xl = './/' + xl;          // div/span -> .//div/span
      }
      try {
        const r = document.evaluate(xl, rootElement, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        const arr = [];
        for (let i = 0; i < r.snapshotLength; i++) arr.push(r.snapshotItem(i));
        return arr;
      } catch (e) { return []; }
    }

    if (lt === 'drission') {
      // Reuse the drission→css/walker logic by delegating to the contains-based
      // resolver; for drission, relative is best-effort (still scoped to parent).
      return resolveAllLocatorsInContext(l, 'drission', rootElement);
    }

    // css family
    try { return Array.from(rootElement.querySelectorAll(l)); } catch (e) {}
    return [];
  }

  function waitForElementInContext(locator, selectorFamily, rootElement, mode = 'visible', timeoutMs = 10000, pollMs = 200) {
    locator = normalizeLocator(locator);
    selectorFamily = normalizeSelectorFamily(locator, selectorFamily);
    const start = Date.now();
    return new Promise((resolve, reject) => {
      const tick = () => {
        const el = resolveLocatorInContext(locator, selectorFamily, rootElement);
        if (el && el !== rootElement && checkVisibility(el, mode)) return resolve(el);
        if (Date.now() - start >= timeoutMs) {
          return reject(new Error(`元素未在 ${timeoutMs}ms 内出现: ${locator}`));
        }
        setTimeout(tick, pollMs);
      };
      tick();
    });
  }

  function waitForElementWithContext(locator, selectorFamily, extra, mode = 'visible', timeoutMs = 10000, pollMs = 200) {
    const ctxLocator = extra?.contextLocator;
    const ctxLocatorType = extra?.contextLocatorType;
    const ctxIndex = extra?.contextIndex ?? 0;
    const ctxTotal = extra?.contextTotal;
    const srcLocator = extra?.sourceLocator;
    const srcLocatorType = extra?.sourceSelectorFamily;
    const srcIndex = extra?.sourceIndex ?? 0;
    const srcTotal = extra?.sourceTotal;

    if (!ctxLocator && !srcLocator) {
      return waitForElement(locator, selectorFamily, mode, timeoutMs);
    }

    const start = Date.now();
    return new Promise((resolve, reject) => {
      const tick = () => {
        let parents = [];
        let parent = null;
        let usedSource = false;
        if (ctxLocator) {
          parents = resolveAllLocators(ctxLocator, ctxLocatorType);
          parent = parents[ctxIndex];
        }
        if (!parent && srcLocator) {
          parents = resolveAllLocators(srcLocator, srcLocatorType);
          parent = parents[srcIndex];
          usedSource = true;
        }
        if (!parent) {
          if (Date.now() - start >= timeoutMs) {
            return reject(new Error(`上下文元素未找到 (第 ${ctxIndex + 1}/${ctxTotal || '?'} 个)`));
          }
          return setTimeout(tick, pollMs);
        }

        // "Reference the loop item itself": the target IS the current loop item,
        // not a descendant. First-class replacement for the old "child selector
        // == loop selector" heuristic.
        if (extra?.referenceItemItself) {
          if (mode === 'any' || checkVisibility(parent, mode)) {
            window.__rpaLastContextDebugInfo = getElementDebugInfo(locator, selectorFamily, extra, parent);
            return resolve(parent);
          }
          const err = new Error(`循环项本身不可见: ${ctxLocator || srcLocator}`);
          err.contextNotFound = true;
          return reject(err);
        }

        // Prefer the capture-time relative selector when present: query strictly
        // within the loop item, unifying xpath/css scope semantics.
        let el = null;
        if (extra?.useRelative && extra?.relativeLocator) {
          const relMatches = resolveAllRelativeInContext(
            extra.relativeLocator, extra.relativeSelectorFamily, parent);
          el = mode === 'any'
            ? relMatches[0] || null
            : relMatches.find(e => checkVisibility(e, mode)) || null;
          if (!el && relMatches.length === 0) {
            addRunLog(`相对选择器在循环项内未命中，回退全局解析: ${extra.relativeLocator}`);
          }
        }

        // Local/descendant scope: only search within the current outer element.
        if (!el) {
          const allDescendants = resolveAllLocatorsInContext(locator, selectorFamily, parent);
          el = mode === 'any'
            ? allDescendants[0] || null
            : allDescendants.find(e => checkVisibility(e, mode)) || null;
        }

        // Fallback: when the child selector is the same as the loop selector,
        // the intended target is the current loop item itself (not a descendant).
        if (!el) {
          const globalMatches = resolveAllLocators(locator, selectorFamily);
          if (globalMatches.includes(parent) && (mode === 'any' || checkVisibility(parent, mode))) {
            el = parent;
          }
        }

        if (el) {
          const debugInfo = getElementDebugInfo(locator, selectorFamily, extra, el);
          window.__rpaLastContextDebugInfo = debugInfo;
          console.log(
            `[waitForElementWithContext] mode=${debugInfo.mode} ` +
            `index=${ctxIndex + 1}/${ctxTotal || '?'} ` +
            `outerTotal=${debugInfo.outerTotal} innerTotal=${debugInfo.innerTotal} innerIndex=${debugInfo.innerIndex} ` +
            `locator=${locator} ${usedSource ? '(source fallback)' : ''}`
          );
          return resolve(el);
        }

        // Parent exists but no matching descendant inside it.
        const err = new Error(`元素在当前外层元素中未找到: ${locator}`);
        err.contextNotFound = true;
        return reject(err);
      };
      tick();
    });
  }

  function reResolveWithContext(locator, selectorFamily, extra, mode = 'visible') {
    const ctxLocator = extra?.contextLocator;
    const ctxLocatorType = extra?.contextLocatorType;
    const ctxIndex = extra?.contextIndex ?? 0;
    const srcLocator = extra?.sourceLocator;
    const srcLocatorType = extra?.sourceSelectorFamily;
    const srcIndex = extra?.sourceIndex ?? 0;

    let parent = null;
    if (ctxLocator) {
      const parents = resolveAllLocators(ctxLocator, ctxLocatorType);
      parent = parents[ctxIndex];
    }
    if (!parent && srcLocator) {
      const parents = resolveAllLocators(srcLocator, srcLocatorType);
      parent = parents[srcIndex];
    }

    let el = null;
    if (parent) {
      // Reference the loop item itself.
      if (extra?.referenceItemItself) {
        if (mode === 'any' || checkVisibility(parent, mode)) el = parent;
      }
      // Prefer the capture-time relative selector.
      if (!el && extra?.useRelative && extra?.relativeLocator) {
        const relMatches = resolveAllRelativeInContext(
          extra.relativeLocator, extra.relativeSelectorFamily, parent);
        el = mode === 'any'
          ? relMatches[0] || null
          : relMatches.find(e => checkVisibility(e, mode)) || null;
      }
      if (!el) {
        const allDescendants = resolveAllLocatorsInContext(locator, selectorFamily, parent);
        el = mode === 'any'
          ? allDescendants[0] || null
          : allDescendants.find(e => checkVisibility(e, mode)) || null;
      }

      // Fallback: loop item itself matches the child selector.
      if (!el) {
        const globalMatches = resolveAllLocators(locator, selectorFamily);
        if (globalMatches.includes(parent) && (mode === 'any' || checkVisibility(parent, mode))) {
          el = parent;
        }
      }
    }
    if (!el) {
      el = resolveLocator(locator, selectorFamily, mode);
    }
    if (el && extra?.contextLocator) {
      window.__rpaLastContextDebugInfo = getElementDebugInfo(locator, selectorFamily, extra, el);
    }
    return el;
  }

  function buildDebugSnippet(ctxLocator, ctxLocatorType, ctxIndex, locator, selectorFamily, mode, innerIndex, outerTotal, innerTotal) {
    const safe = (s) => JSON.stringify(s ?? '');
    function snapExpr(scopeVar, sel, type) {
      const family = type || inferSelectorFamily(sel);
      if (family === 'xpath' || (sel && sel.startsWith('//'))) {
        return `document.evaluate(${safe(sel)}, ${scopeVar}, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null)`;
      }
      return `${scopeVar}.querySelectorAll(${safe(sel)})`;
    }
    function lenExpr(expr) {
      return `(${expr}.snapshotLength ?? ${expr}.length)`;
    }
    const ctxExpr = snapExpr('document', ctxLocator, ctxLocatorType);
    const scope = mode === 'descendant' ? 'outer' : 'document';
    let innerSel = locator;
    if (mode === 'descendant' && (selectorFamily === 'xpath' || (innerSel && innerSel.startsWith('//')))) {
      innerSel = '.' + innerSel;
    }
    const innerExpr = snapExpr(scope, innerSel, selectorFamily);
    const idx = innerIndex >= 0 ? innerIndex : 0;
    return `// RPA debug snippet (mode=${mode})
function rpaItem(list, i) { return list.snapshotItem ? list.snapshotItem(i) : list[i]; }
const outer = rpaItem(${ctxExpr}, ${ctxIndex});
const innerAll = ${innerExpr};
const inner = rpaItem(innerAll, ${idx});
console.log({
  outerTotal: ${lenExpr(ctxExpr)},
  outerIndex: ${ctxIndex},
  innerTotal: ${lenExpr(innerExpr)},
  innerIndex: ${innerIndex}
});
// target element: inner`;
  }

  function getElementDebugInfo(locator, selectorFamily, extra, el) {
    const ctxLocator = extra?.contextLocator;
    const ctxLocatorType = extra?.contextLocatorType;
    const ctxIndex = extra?.contextIndex ?? 0;
    const mode = getVisibilityMode(extra);
    const info = {
      mode: 'none',
      outerTotal: 0,
      outerIndex: ctxIndex,
      innerTotal: 0,
      innerIndex: -1,
      jsSnippet: '',
    };
    if (!ctxLocator) return info;

    const parents = resolveAllLocators(ctxLocator, ctxLocatorType);
    info.outerTotal = parents.length;
    const parent = parents[ctxIndex];
    if (!parent) {
      info.mode = 'no-outer';
      info.jsSnippet = buildDebugSnippet(ctxLocator, ctxLocatorType, ctxIndex, locator, selectorFamily, info.mode, -1, info.outerTotal, 0);
      return info;
    }

    const inCtxAll = resolveAllLocatorsInContext(locator, selectorFamily, parent);
    const inCtx = mode !== 'any' ? inCtxAll.filter(e => checkVisibility(e, mode)) : inCtxAll;
    const descendantEl = inCtx[0] || null;
    let innerList = inCtx;
    let resolutionMode = 'descendant';
    if (el && descendantEl !== el) {
      resolutionMode = 'index-alignment';
      const globalAll = resolveAllLocators(locator, selectorFamily);
      innerList = mode !== 'any' ? globalAll.filter(e => checkVisibility(e, mode)) : globalAll;
    }
    info.mode = resolutionMode;
    info.innerTotal = innerList.length;
    info.innerIndex = el ? innerList.indexOf(el) : -1;
    info.jsSnippet = buildDebugSnippet(ctxLocator, ctxLocatorType, ctxIndex, locator, selectorFamily, resolutionMode, info.innerIndex, info.outerTotal, info.innerTotal);
    return info;
  }

  // ─── Human-like interaction utilities ────────────────────────────

  let _lastOpTime = 0;
  let _lastHoveredElement = null;

  function rand(min, max) {
    return Math.random() * (max - min) + min;
  }
  function randInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
  }
  function randNormal(mean, stdDev) {
    let u = 0, v = 0;
    while (u === 0) u = Math.random();
    while (v === 0) v = Math.random();
    return Math.max(0, mean + stdDev * Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v));
  }
  function sleep(ms) {
    return new Promise(r => setTimeout(r, Math.max(0, ms)));
  }

  // 操作间随机间隔（伽马分布近似）
  async function humanDelay(minMs = 100) {
    const gamma = randNormal(400, 200);
    const delay = Math.max(minMs, gamma);
    await sleep(delay);
  }

  // 视觉确认延迟
  async function visualConfirmDelay() {
    await sleep(rand(200, 600));
  }

  // 元素内随机点击点（避开边缘 5px）
  function getClickPoint(el, humanLike) {
    const rect = el.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    if (!humanLike) return { x: cx, y: cy };
    const pad = 5;
    const maxOffX = Math.max(0, rect.width / 2 - pad);
    const maxOffY = Math.max(0, rect.height / 2 - pad);
    const angle = rand(0, Math.PI * 2);
    const dist = rand(0, Math.min(maxOffX, maxOffY, 20));
    return { x: cx + Math.cos(angle) * dist, y: cy + Math.sin(angle) * dist };
  }

  // 贝塞尔曲线鼠标轨迹
  async function moveMouseBezier(startX, startY, endX, endY, humanLike) {
    if (!humanLike) return;
    const steps = randInt(15, 35);
    const cp1x = startX + (endX - startX) * rand(0.2, 0.4) + rand(-30, 30);
    const cp1y = startY + (endY - startY) * rand(0.1, 0.3) + rand(-30, 30);
    const cp2x = startX + (endX - startX) * rand(0.6, 0.8) + rand(-30, 30);
    const cp2y = startY + (endY - startY) * rand(0.7, 0.9) + rand(-30, 30);
    const duration = rand(300, 900);
    const startTime = performance.now();

    function bezier(t, p0, p1, p2, p3) {
      const u = 1 - t, u2 = u * u, u3 = u2 * u, t2 = t * t, t3 = t2 * t;
      return u3 * p0 + 3 * u2 * t * p1 + 3 * u * t2 * p2 + t3 * p3;
    }

    let prevX = startX, prevY = startY;
    for (let i = 1; i <= steps; i++) {
      const t = i / steps;
      // 先加速后减速：easeInOut
      const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      const targetTime = startTime + duration * eased;
      const x = bezier(eased, startX, cp1x, cp2x, endX);
      const y = bezier(eased, startY, cp1y, cp2y, endY);
      const wait = targetTime - performance.now();
      if (wait > 0) await sleep(wait);
      document.dispatchEvent(new MouseEvent('mousemove', {
        bubbles: true, cancelable: true, view: window,
        clientX: x, clientY: y, movementX: x - prevX, movementY: y - prevY
      }));
      prevX = x; prevY = y;
    }
  }

  // 悬停微动
  async function hoverWiggle(x, y) {
    const wiggleDuration = rand(80, 300);
    const wiggleStart = performance.now();
    while (performance.now() - wiggleStart < wiggleDuration) {
      const dx = rand(-1.5, 1.5);
      const dy = rand(-1.5, 1.5);
      document.dispatchEvent(new MouseEvent('mousemove', {
        bubbles: true, cancelable: true, view: window,
        clientX: x + dx, clientY: y + dy, movementX: dx, movementY: dy
      }));
      await sleep(rand(30, 80));
    }
  }

  // 等待元素滚动停止（用于平滑滚动）
  async function waitForScrollEnd(el, timeout = 2000) {
    const start = performance.now();
    let lastTop = el.getBoundingClientRect().top;
    let lastWindowY = window.scrollY;
    let stableFrames = 0;
    while (performance.now() - start < timeout) {
      await new Promise(resolve => requestAnimationFrame(resolve));
      const top = el.getBoundingClientRect().top;
      const windowY = window.scrollY;
      if (Math.abs(top - lastTop) < 0.5 && Math.abs(windowY - lastWindowY) < 0.5) {
        stableFrames += 1;
        if (stableFrames >= 3) return;
      } else {
        stableFrames = 0;
      }
      lastTop = top;
      lastWindowY = windowY;
    }
  }

  // 拟人点击
  async function humanClick(el, humanLike, clickType = 'click') {
    try {
      // 后台标签页 setTimeout 被节流到 1s，跳过拟人动画避免超时
      if (document.hidden) {
        el.scrollIntoView({ block: 'center', behavior: 'instant' });
        if (el.focus) el.focus();
        el.click();
        return;
      }

      // 确保元素在视口内并可交互
      const scrollBehavior = humanLike ? 'smooth' : 'instant';
      el.scrollIntoView({ block: 'center', behavior: scrollBehavior });
      if (humanLike) {
        await waitForScrollEnd(el);
      } else {
        await sleep(50);
      }
      if (el.focus) el.focus();

      const point = getClickPoint(el, humanLike);
      const rect = el.getBoundingClientRect();
      const startX = rect.left + rect.width / 2;
      const startY = rect.top + rect.height / 2;
      console.log(`[humanClick] el=${el.tagName} point=(${point.x.toFixed(1)},${point.y.toFixed(1)}) humanLike=${humanLike} clickType=${clickType}`);
      try {
        console.log(`[humanClick] detail class="${el.className || ''}" id="${el.id || ''}" disabled=${el.disabled} readOnly=${el.readOnly} tabindex="${el.getAttribute?.('tabindex') || ''}"`);
        const style = window.getComputedStyle(el);
        console.log(`[humanClick] style display=${style.display} visibility=${style.visibility} opacity=${style.opacity} pointerEvents=${style.pointerEvents} cursor=${style.cursor}`);
        console.log(`[humanClick] children=${Array.from(el.children).map(c => c.tagName + (c.className ? '.' + c.className : '')).join(', ')}`);
        console.log(`[humanClick] innerHTML=${(el.innerHTML || '').slice(0, 300).replace(/\s+/g, ' ')}`);
        const stack = document.elementsFromPoint(point.x, point.y);
        console.log(`[humanClick] elementsFromPoint=${stack.slice(0, 6).map(e => { const cls = e.getAttribute ? (e.getAttribute('class') || '') : ''; return e.tagName + (cls ? '.' + cls.slice(0, 40) : ''); }).join(' | ')}`);
      } catch (err) {
        console.warn('[humanClick] log detail failed', err);
      }

      if (humanLike) {
        try {
          await moveMouseBezier(startX, startY, point.x, point.y, true);
          await hoverWiggle(point.x, point.y);
        } catch (e) {
          console.warn('[humanClick] mouse movement skipped:', e.message);
        }
        await sleep(rand(80, 300));
      }

      const button = clickType === 'rightClick' ? 2 : 0;
      const detail = clickType === 'doubleClick' ? 2 : 1;

      const mousedown = new MouseEvent('mousedown', {
        bubbles: true, cancelable: true, view: window,
        clientX: point.x, clientY: point.y, button, detail
      });
      el.dispatchEvent(mousedown);
      console.log('[humanClick] dispatched mousedown to', el.tagName, 'button=', button);

      if (humanLike) {
        await sleep(rand(80, 200));
      }

      const mouseup = new MouseEvent('mouseup', {
        bubbles: true, cancelable: true, view: window,
        clientX: point.x, clientY: point.y, button, detail
      });
      el.dispatchEvent(mouseup);
      console.log('[humanClick] dispatched mouseup to', el.tagName, 'button=', button);

      if (clickType === 'doubleClick') {
        const dblclickEvt = new MouseEvent('dblclick', {
          bubbles: true, cancelable: true, view: window,
          clientX: point.x, clientY: point.y, button: 0, detail: 2
        });
        el.dispatchEvent(dblclickEvt);
        console.log('[humanClick] dispatched dblclick to', el.tagName);
        // Fallback
        if (el.click) { el.click(); await sleep(rand(80, 200)); el.click(); }
      } else if (clickType === 'rightClick') {
        const contextEvt = new MouseEvent('contextmenu', {
          bubbles: true, cancelable: true, view: window,
          clientX: point.x, clientY: point.y, button: 2, detail: 1
        });
        el.dispatchEvent(contextEvt);
        console.log('[humanClick] dispatched contextmenu to', el.tagName);
      } else {
        const clickEvt = new MouseEvent('click', {
          bubbles: true, cancelable: true, view: window,
          clientX: point.x, clientY: point.y, button: 0, detail: 1
        });
        el.dispatchEvent(clickEvt);
        console.log('[humanClick] dispatched click to', el.tagName, 'bubbles=true');
      }

      // Fallback：某些框架只响应原生 click()
      if (clickType === 'click' && el.click && !humanLike) {
        console.log('[humanClick] fallback el.click()');
        el.click();
      } else if (clickType === 'click' && humanLike) {
        console.log('[humanClick] fallback el.click() skipped because humanLike=true');
      }
    } catch (e) {
      console.error('[humanClick] error:', e);
      // 降级：直接 click
      if (el.click) el.click();
      else el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    }
  }

  // 安全设置输入值（触发 React/Vue 响应）
  function setInputValue(el, value) {
    const tag = el.tagName.toLowerCase();
    let descriptor = null;
    if (tag === 'input') {
      descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    } else if (tag === 'textarea') {
      descriptor = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');
    }
    if (descriptor && descriptor.set) {
      descriptor.set.call(el, value);
    } else {
      el.value = value;
    }
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  // 拟人打字
  async function humanType(el, text, humanLike) {
    if (!humanLike || document.hidden) {
      setInputValue(el, text);
      return;
    }
    let current = '';
    for (let i = 0; i < text.length; i++) {
      // 2~5% 概率打错字
      if (Math.random() < rand(0.02, 0.05)) {
        const wrong = String.fromCharCode(text.charCodeAt(i) + randInt(-3, 3));
        setInputValue(el, current + wrong);
        await sleep(rand(100, 300));
        setInputValue(el, current);
        await sleep(rand(100, 200));
      }
      current += text[i];
      setInputValue(el, current);
      if (i < text.length - 1) {
        await sleep(randNormal(125, 40));
      }
    }
  }

  // 平滑滚动（非线性缓动 + rAF 连续动画）
  async function humanScroll(direction, amount, humanLike) {
    // 后台标签页中 requestAnimationFrame 会被浏览器暂停，直接跳转避免超时
    if (!humanLike || document.hidden) {
      if (direction === 'down') window.scrollBy(0, amount);
      else if (direction === 'up') window.scrollBy(0, -amount);
      else if (direction === 'bottom') window.scrollTo(0, document.documentElement.scrollHeight);
      else if (direction === 'top') window.scrollTo(0, 0);
      return;
    }

    const startY = window.scrollY;
    const maxY = document.documentElement.scrollHeight - window.innerHeight;
    let targetY;
    if (direction === 'bottom') targetY = maxY;
    else if (direction === 'top') targetY = 0;
    else if (direction === 'down') targetY = startY + amount;
    else if (direction === 'up') targetY = startY - amount;
    else targetY = startY;

    targetY = Math.max(0, Math.min(maxY, targetY));
    const distance = targetY - startY;
    if (Math.abs(distance) < 5) return;

    const duration = rand(600, 1400); // 随机总时长，模拟人类节奏差异
    const startTime = performance.now();

    // easeInOutCubic: 启动慢 → 中间快 → 停止慢
    const ease = (t) => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

    await new Promise((resolve) => {
      function tick(now) {
        const elapsed = now - startTime;
        const p = Math.min(elapsed / duration, 1);
        window.scrollTo(0, startY + distance * ease(p));
        if (p < 1) {
          requestAnimationFrame(tick);
        } else {
          // 10% 概率微回调（人类常见的滚过头回弹）
          if (Math.random() < 0.1) {
            window.scrollBy(0, distance > 0 ? randInt(3, 10) : randInt(-10, -3));
          }
          resolve();
        }
      }
      requestAnimationFrame(tick);
    });
  }

  // ─── Running UI ──────────────────────────────────────────────────

  let _bannerTimer = null;
  let _runLogs = [];

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function addRunLog(msg) {
    _runLogs.push({ time: new Date().toLocaleTimeString('zh-CN', { hour12: false }), msg });
    if (_runLogs.length > 20) _runLogs.shift();
    updateRunningUI();
  }

  function updateRunningUI() {
    let container = document.getElementById('__rpa_ui_container');
    if (!container) {
      container = document.createElement('div');
      container.id = '__rpa_ui_container';
      document.body.appendChild(container);

      if (!document.getElementById('__rpa_banner_style')) {
        const style = document.createElement('style');
        style.id = '__rpa_banner_style';
        style.textContent = `@keyframes rpa-pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }`;
        document.head.appendChild(style);
      }
    }

    const corners = [
      { id: '__rpa_corner_tl', style: 'top:12px;left:12px;' },
      { id: '__rpa_corner_tr', style: 'top:12px;right:12px;' },
      { id: '__rpa_corner_bl', style: 'bottom:48px;left:12px;' },
      { id: '__rpa_corner_br', style: 'bottom:48px;right:12px;' },
    ];

    corners.forEach(c => {
      let el = document.getElementById(c.id);
      if (!el) {
        el = document.createElement('div');
        el.id = c.id;
        el.style.cssText = `
          position: fixed;
          ${c.style}
          z-index: 999999;
          background: rgba(0,0,0,0.65);
          color: #fff;
          padding: 3px 10px;
          border-radius: 10px;
          font-size: 11px;
          font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
          pointer-events: none;
          backdrop-filter: blur(3px);
          white-space: nowrap;
          display: flex;
          align-items: center;
          gap: 5px;
          transition: opacity 0.3s;
        `;
        container.appendChild(el);
      }
      el.innerHTML = `
        <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#22c55e;animation:rpa-pulse 1.5s infinite;"></span>
        <span>RPA 运行中</span>
      `;
      el.style.opacity = '1';
    });

    let logEl = document.getElementById('__rpa_bottom_logs');
    if (!logEl) {
      logEl = document.createElement('div');
      logEl.id = '__rpa_bottom_logs';
      logEl.style.cssText = `
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        z-index: 999998;
        background: rgba(0,0,0,0.6);
        color: #e5e7eb;
        padding: 5px 12px;
        font-size: 11px;
        font-family: ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
        pointer-events: none;
        backdrop-filter: blur(3px);
        transition: opacity 0.3s;
        line-height: 1.45;
      `;
      container.appendChild(logEl);
    }
    const recent = _runLogs.slice(-3);
    logEl.innerHTML = recent.length
      ? recent.map(l => `<div><span style="color:#9ca3af;">${escapeHtml(l.time)}</span> ${escapeHtml(l.msg)}</div>`).join('')
      : '<div style="color:#6b7280;">等待执行...</div>';
    logEl.style.opacity = '1';
  }

  function hideRunningUI() {
    _bannerTimer = null;
    const container = document.getElementById('__rpa_ui_container');
    if (container) {
      container.style.opacity = '0';
      setTimeout(() => container?.remove(), 300);
    }
  }

  function showRunningBanner(stepType) {
    addRunLog(stepType ? `执行: ${stepType}` : '开始运行');
    if (_bannerTimer) clearTimeout(_bannerTimer);
    _bannerTimer = setTimeout(hideRunningUI, 8000);
  }


  // ── checkElementExists ──
// ─── Condition check handlers ───────────────────────────────────

registerHandler('checkElementExists', async function checkElementExists({ locator, selectorFamily, extra }) {
      const mode = getVisibilityMode(extra);
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      try {
        await waitForElementWithContext(locator, selectorFamily, extra, mode, timeoutMs);
        return { exists: true };
      } catch (e) {
        return { exists: false };
      }
    });


  // ── click ──


registerHandler('click', async function click(args) { return doClick(args); });


  // ── closeBrowser ──


registerHandler('closeBrowser', function closeBrowser() {
      // handled by background.js (chrome.windows.remove)
      return {};
    });


  // ── elementAction ──


registerHandler('elementAction', async function elementAction({ locator, selectorFamily, extra }) {
    const action = extra?.action;
    if (!action) throw new Error('elementAction: extra.action is required');
    switch (action) {
      case 'click':
      case 'doubleClick':
      case 'rightClick':
        return doClick({ locator, selectorFamily, extra });
      case 'clickCurrentLoopItem':
        return doClickCurrentLoopItem({ extra });
      case 'input':
      case 'inputAndPressEnter':
        return doInput({ locator, selectorFamily, extra });
      case 'extract':
      case 'getText':
      case 'getAttr':
      case 'getHtml':
      case 'getValue':
        return doExtract({ locator, selectorFamily, extra });
      case 'scroll':
      case 'scrollToBottom':
      case 'scrollToTop':
      case 'scrollOneScreen':
      case 'scrollIntoView':
      case 'scrollBy':
        return doScroll({ locator, selectorFamily, extra });
      case 'hover':
        return doHover({ locator, selectorFamily, extra });
      case 'unhover':
        return doUnhover({ locator, selectorFamily, extra });
      case 'clearInput':
        return doClearInput({ locator, selectorFamily, extra });
      case 'selectOption':
        return doSelectOption({ locator, selectorFamily, extra });
      default:
        throw new Error(`elementAction: unknown action "${action}"`);
    }
  });


  // ── executeJs ──


registerHandler('executeJs', function executeJs({ extra }) {
      const script = extra?.script;
      if (!script) throw new Error('executeJs: script required');
      // eslint-disable-next-line no-eval
      const result = eval(script);
      return { executed: true, result: String(result) };
    });


  // ── extract ──


registerHandler('extract', async function extract(args) { return doExtract(args); });


  // ── findElements ──


registerHandler('findElements', async function findElements({ locator, selectorFamily, extra }) {
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const mode = getVisibilityMode(extra);
      const ctxLocator = extra?.contextLocator;
      const ctxLocatorType = extra?.contextLocatorType;
      const ctxIndex = extra?.contextIndex ?? 0;
      const srcLocator = extra?.sourceLocator;
      const srcLocatorType = extra?.sourceSelectorFamily;
      const srcIndex = extra?.sourceIndex ?? 0;
      const start = Date.now();
      let elements = [];
      while (Date.now() - start < timeoutMs) {
        let parent = null;
        if (ctxLocator) {
          const parents = resolveAllLocators(ctxLocator, ctxLocatorType);
          parent = parents[ctxIndex];
        }
        if (!parent && srcLocator) {
          const parents = resolveAllLocators(srcLocator, srcLocatorType);
          parent = parents[srcIndex];
        }
        if (extra?.useRelative && extra?.relativeLocator && parent) {
          elements = resolveAllRelativeInContext(extra.relativeLocator, extra.relativeSelectorFamily, parent);
        } else if (parent) {
          elements = resolveAllLocatorsInContext(locator, selectorFamily, parent);
        } else {
          elements = resolveAllLocators(locator, selectorFamily);
        }
        const rawCount = elements.length;
        if (mode !== 'any') {
          elements = elements.filter(el => checkVisibility(el, mode));
        }
        console.log(`[RPA findElements] raw=${rawCount} filtered=${elements.length} mode=${mode} locator=${JSON.stringify(locator)} ctx=${ctxLocator ? 'yes' : 'no'}`);
        if (elements.length > 0) break;
        await sleep(200);
      }
      const items = elements.map((el, idx) => ({
        text: el.textContent?.trim() ?? '',
        html: el.innerHTML?.slice(0, 500) ?? '',
        tagName: el.tagName,
        index: idx,
        contextLocator: getElementXPath(el),
        contextLocatorType: 'xpath',
      }));
      return { count: items.length, items };
    });


  // ── getAttribute ──


registerHandler('getAttribute', async (args) => {
      args.extra = { ...(args.extra || {}), action: 'getAttr' };
      return doExtract(args);
  });


  // ── getText ──


registerHandler('getText', async (args) => {
      args.extra = { ...(args.extra || {}), action: 'getText' };
      return doExtract(args);
  });


  // ── getValue ──


registerHandler('getValue', async (args) => {
      args.extra = { ...(args.extra || {}), action: 'getValue' };
      return doExtract(args);
  });


  // ── hover ──


registerHandler('hover', async function hover(args) { return doHover(args); });


  // ── input ──


registerHandler('input', async function input(args) { return doInput(args); });


  // ── inputText ──


registerHandler('inputText', async (args) => doInput(args));


  // ── navigate ──


registerHandler('navigate', function navigate({ extra }) {
      const url = extra?.url;
      if (!url) throw new Error('navigate: url required');
      window.location.href = url;
      return { navigatedTo: url };
    });


  // ── newTab ──


registerHandler('newTab', function newTab({ extra }) {
      const url = extra?.url;
      if (!url) throw new Error('newTab: url required');
      window.open(url, '_blank');
      return { opened: url };
    });


  // ── pressKey ──


registerHandler('pressKey', async function pressKey({ extra }) {
      const key = extra?.key || 'Enter';
      const humanLike = extra?.humanLike ?? true;
      const modifiers = ['Control', 'Alt', 'Shift', 'Meta'];
      const isModifier = modifiers.includes(key);
      const hasModifier = extra?.modifiers?.some(m => modifiers.includes(m));

      if (humanLike && (isModifier || hasModifier)) {
        await sleep(rand(30, 100));
      }
      if (humanLike && (key === 'Enter' || key === 'Tab')) {
        await sleep(rand(200, 600));
      }

      document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
      if (humanLike && !isModifier) await sleep(rand(80, 200));
      document.dispatchEvent(new KeyboardEvent('keyup', { key, bubbles: true }));
      return { pressed: key };
    });


  // ── scroll ──


registerHandler('scroll', async function scroll(args) { return doScroll(args); });


  // ── scrollIntoView ──


registerHandler('scrollIntoView', async (args) => {
      args.extra = { ...(args.extra || {}), action: 'scrollIntoView' };
      return doScroll(args);
  });


  // ── scrollToBottom ──


registerHandler('scrollToBottom', async (args) => {
      args.extra = { ...(args.extra || {}), action: 'scrollToBottom' };
      return doScroll(args);
  });


  // ── takeScreenshot ──
// ─── takeScreenshot ──────────────────────────────────────────────

registerHandler('takeScreenshot', async function takeScreenshotHandler({ locator, selectorFamily, extra }) {
    const mode = getVisibilityMode(extra);
    if (locator) {
      // Screenshot of a specific element
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const el = await waitForElement(locator, selectorFamily, mode, timeoutMs);
      el.scrollIntoView({ block: 'center', behavior: 'instant' });
      await sleep(200);
      const rect = el.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const resp = await chrome.runtime.sendMessage({
        action: 'captureElementScreenshot',
        rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
        dpr,
      });
      if (resp?.error) throw new Error(`截图失败: ${resp.error}`);
      return { dataUrl: resp.dataUrl, elementScreenshot: true };
    }
    // Full page screenshot
    const resp = await chrome.runtime.sendMessage({ action: 'captureScreenshot' });
    if (resp?.error) throw new Error(`截图失败: ${resp.error}`);
    return { dataUrl: resp.dataUrl, elementScreenshot: false };
  });


  // ── waitForElement ──
// ─── waitForElement / waitForElementHide ─────────────────────────

registerHandler('waitForElement', async function waitForElementHandler({ locator, selectorFamily, extra }) {
    const mode = getVisibilityMode(extra);
    const timeoutMs = (extra?.timeout ?? 10) * 1000;
    await waitForElement(locator, selectorFamily, mode, timeoutMs);
    return { appeared: true };
  });


  // ── clickElement ──

registerHandler('clickElement', async (args) => doClick(args));


  // ── inputElement ──

registerHandler('inputElement', async (args) => doInput(args));


  // ─── Message listener ────────────────────────────────────────────

  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'setRunningBanner') {
      if (request.visible) showRunningBanner(request.stepType);
      else hideRunningUI();
      sendResponse({ ok: true });
      return false;
    }

    if (request.action !== 'executeStep') return false;

    const { step } = request;
    const { type, locator, selectorFamily, extra } = step;
    console.log(`[RPA executeStep] type=${type} locator=${JSON.stringify(locator)} selectorFamily=${selectorFamily}`);

    showRunningBanner(type);

    const handler = handlers[type];

    if (!handler) {
      sendResponse({ status: 'error', error: `Unknown step type: ${type}` });
      return false;
    }

    let responded = false;
    const safeRespond = (payload) => {
      if (responded) return;
      responded = true;
      try { sendResponse(payload); } catch (_) {}
    };

    // 兜底超时：即使 handler 卡住也保证返回
    const timeoutId = setTimeout(() => {
      safeRespond({ status: 'error', error: 'Content script step timeout (>30s)' });
    }, 30000);

    (async () => {
      try {
        // 操作间拟人化间隔（串行执行）
        const humanLike = extra?.humanLike ?? true;
        if (humanLike && _lastOpTime > 0) {
          const elapsed = performance.now() - _lastOpTime;
          const minGap = randNormal(400, 200);
          if (elapsed < minGap) await sleep(minGap - elapsed);
        }

        // 支持多 locator 数组：按优先级逐个试，命中即停
        let targetLocator = locator;
        let targetLocatorType = selectorFamily;
        let matchedIndex = -1;
        if (Array.isArray(locator) && locator.length > 0) {
          for (let i = 0; i < locator.length; i++) {
            const item = locator[i];
            const itemLocator = typeof item === 'string' ? item : (item.locator || item.syntax || item.selector || '');
            const itemType = typeof item === 'string' ? selectorFamily : (item.selectorFamily || item.type || selectorFamily);
            const el = resolveLocator(itemLocator, itemType, false);
            if (el) {
              targetLocator = itemLocator;
              targetLocatorType = itemType;
              matchedIndex = i;
              break;
            }
          }
          if (matchedIndex === -1) {
            clearTimeout(timeoutId);
            addRunLog(`${type} 失败: 未匹配到元素`);
            safeRespond({ status: 'error', error: 'None of the locators matched any element' });
            return;
          }
        }

        console.log(`[RPA Agent] executing step type=${type} humanLike=${extra?.humanLike ?? true} matchedIndex=${matchedIndex}`);
        const result = await handler({ locator: targetLocator, selectorFamily: targetLocatorType, extra: extra || {} });
        _lastOpTime = performance.now();
        clearTimeout(timeoutId);

        // Compute matched count and context debug info
        let matchedCount = result?.matchedCount;
        let contextDebug = null;
        if (extra?.contextLocator) {
          contextDebug = window.__rpaLastContextDebugInfo || null;
          if (contextDebug) {
            matchedCount = contextDebug.innerTotal;
            console.log(`[RPA Agent] context mode=${contextDebug.mode} outer=${contextDebug.outerTotal} inner=${contextDebug.innerTotal} innerIndex=${contextDebug.innerIndex}`);
          }
        } else if (targetLocator && matchedCount === undefined) {
          const all = resolveAllLocators(targetLocator, targetLocatorType);
          const mode = getVisibilityMode(extra);
          matchedCount = mode !== 'any' ? all.filter(e => checkVisibility(e, mode)).length : all.length;
          console.log(`[RPA Agent] matched ${matchedCount} element(s) for locator=${targetLocator}`);
        }

        addRunLog(`${type} 完成`);
        const responseResult = (result && typeof result === 'object' && !Array.isArray(result))
          ? { ...result, matchedIndex, matchedCount, ...(contextDebug ? { contextDebug } : {}) }
          : { value: result, matchedIndex, matchedCount, ...(contextDebug ? { contextDebug } : {}) };
        safeRespond({ status: 'success', result: responseResult });
      } catch (e) {
        console.error(`[RPA Agent] step ${type} failed:`, e);
        clearTimeout(timeoutId);
        addRunLog(`${type} 失败: ${e?.message || String(e)}`);
        safeRespond({ status: 'error', error: e?.message || String(e) });
      }
    })();

    return true;
  });

  console.log(`[RPA Agent] Content script injected v${AGENT_VERSION}`);
})();

