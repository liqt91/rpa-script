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

  function isVisible(el) {
    if (!el) return false;
    const style = getComputedStyle(el);
    const reason = [];
    if (style.visibility === 'hidden') reason.push('visibility:hidden');
    if (style.display === 'none') reason.push('display:none');
    if (style.position !== 'fixed' && style.position !== 'sticky' && el.offsetParent === null) reason.push('offsetParent:null');
    const visible = reason.length === 0;
    if (!visible) {
      console.log(`[RPA isVisible] tag=${el.tagName}, offsetParent=${el.offsetParent?.tagName || 'null'}, position=${style.position}, reasons=[${reason.join(', ')}]`);
    }
    return visible;
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
    if (locator.startsWith('xpath:') || locator.startsWith('//')) return 'xpath';
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

  function resolveLocator(locator, selectorFamily, visibleOnly) {
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

    if (!el || !visibleOnly) return el;
    if (!isVisible(el)) {
      const all = resolveAllLocators(locator, selectorFamily);
      const v = all.find(isVisible);
      if (v) return v;
    }
    return el;
  }

  function waitForElement(locator, selectorFamily, visibleOnly, timeoutMs = 10000, pollMs = 200) {
    locator = normalizeLocator(locator);
    selectorFamily = normalizeSelectorFamily(locator, selectorFamily);
    console.log(`[RPA waitForElement] normLocator=${locator} normType=${selectorFamily} visibleOnly=${visibleOnly} timeout=${timeoutMs}`);
    const start = Date.now();
    let ticks = 0;
    return new Promise((resolve, reject) => {
      const tick = () => {
        ticks++;
        const el = resolveLocator(locator, selectorFamily, visibleOnly);
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
      case 'xpath':
        el = document.evaluate(l, rootElement, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        break;
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
      const r = document.evaluate(l, rootElement, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
      const arr = [];
      for (let i = 0; i < r.snapshotLength; i++) arr.push(r.snapshotItem(i));
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

  function waitForElementInContext(locator, selectorFamily, rootElement, timeoutMs = 10000, pollMs = 200) {
    locator = normalizeLocator(locator);
    selectorFamily = normalizeSelectorFamily(locator, selectorFamily);
    const start = Date.now();
    return new Promise((resolve, reject) => {
      const tick = () => {
        const el = resolveLocatorInContext(locator, selectorFamily, rootElement);
        if (el && el !== rootElement) return resolve(el);
        if (Date.now() - start >= timeoutMs) {
          return reject(new Error(`元素未在 ${timeoutMs}ms 内出现: ${locator}`));
        }
        setTimeout(tick, pollMs);
      };
      tick();
    });
  }

  // ─── Human-like interaction utilities ────────────────────────────

  let _lastOpTime = 0;

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

  // 拟人点击
  async function humanClick(el, humanLike) {
    try {
      // 后台标签页 setTimeout 被节流到 1s，跳过拟人动画避免超时
      if (document.hidden) {
        el.scrollIntoView({ block: 'center', behavior: 'instant' });
        if (el.focus) el.focus();
        el.click();
        return;
      }

      // 确保元素在视口内并可交互
      el.scrollIntoView({ block: 'center', behavior: 'instant' });
      await sleep(50);
      if (el.focus) el.focus();

      const point = getClickPoint(el, humanLike);
      const rect = el.getBoundingClientRect();
      const startX = rect.left + rect.width / 2;
      const startY = rect.top + rect.height / 2;
      console.log(`[humanClick] el=${el.tagName} point=(${point.x.toFixed(1)},${point.y.toFixed(1)}) humanLike=${humanLike}`);

      if (humanLike) {
        try {
          await moveMouseBezier(startX, startY, point.x, point.y, true);
          await hoverWiggle(point.x, point.y);
        } catch (e) {
          console.warn('[humanClick] mouse movement skipped:', e.message);
        }
        await sleep(rand(80, 300));
      }

      const mousedown = new MouseEvent('mousedown', {
        bubbles: true, cancelable: true, view: window,
        clientX: point.x, clientY: point.y, button: 0
      });
      el.dispatchEvent(mousedown);

      if (humanLike) {
        await sleep(rand(80, 200));
      }

      const mouseup = new MouseEvent('mouseup', {
        bubbles: true, cancelable: true, view: window,
        clientX: point.x, clientY: point.y, button: 0
      });
      el.dispatchEvent(mouseup);

      const clickEvt = new MouseEvent('click', {
        bubbles: true, cancelable: true, view: window,
        clientX: point.x, clientY: point.y, button: 0
      });
      el.dispatchEvent(clickEvt);

      // Fallback：某些框架只响应原生 click()
      if (el.click && !humanLike) {
        el.click();
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

  // ─── Network interception helpers ────────────────────────────────

  const _interceptQueue = [];
  const _traceResults = [];
  let _interceptActive = false;

  function matchPattern(url, pattern) {
    if (!pattern || pattern === '*') return true;
    const parts = pattern.split('*');
    let idx = 0;
    for (const part of parts) {
      const i = url.indexOf(part, idx);
      if (i === -1) return false;
      idx = i + part.length;
    }
    return true;
  }

  function tryJsonParse(text) {
    try { return JSON.parse(text); } catch { return text; }
  }

  function injectInterceptScript(config) {
    removeInterceptScript();
    const script = document.createElement('script');
    script.id = '__rpa_intercept_script';
    script.src = chrome.runtime.getURL('intercept.js');
    script.dataset.config = JSON.stringify(config);
    (document.head || document.documentElement).appendChild(script);
    // Also broadcast config via postMessage in case script loaded before config was set
    window.postMessage({ source: 'rpa-intercept-config', config }, '*');
  }

  function removeInterceptScript() {
    const existing = document.getElementById('__rpa_intercept_script');
    if (existing) existing.remove();
    window.__rpaInterceptActive = false;
    _interceptActive = false;
  }

  // Listen for data from the injected intercept.js
  window.addEventListener('message', (e) => {
    if (!e.data || e.data.source !== 'rpa-intercept') return;
    if (e.data.type === 'trace') {
      _traceResults.push({ url: e.data.url, method: e.data.method, time: e.data.time });
    } else if (e.data.type === 'intercept') {
      _interceptQueue.push({
        url: e.data.url,
        method: e.data.method,
        status: e.data.status,
        body: e.data.body,
        time: e.data.time,
      });
      // Forward to background for optional WS relay
      try {
        chrome.runtime.sendMessage({
          action: 'interceptedData',
          payload: { url: e.data.url, method: e.data.method, status: e.data.status },
        });
      } catch (_e) {}
    }
  });

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

  // ─── Step handlers ───────────────────────────────────────────────

  const handlers = {
    navigate({ extra }) {
      const url = extra?.url;
      if (!url) throw new Error('navigate: url required');
      window.location.href = url;
      return { navigatedTo: url };
    },

    async click({ locator, selectorFamily, extra }) {
      const visibleOnly = extra?.visibleOnly ?? true;
      const humanLike = extra?.humanLike ?? true;
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const el = await waitForElement(locator, selectorFamily, visibleOnly, timeoutMs);

      await visualConfirmDelay();
      await humanClick(el, humanLike);
      return { clicked: true, tagName: el.tagName };
    },

    async input({ locator, selectorFamily, extra }) {
      const visibleOnly = extra?.visibleOnly ?? true;
      const humanLike = extra?.humanLike ?? true;
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const el = await waitForElement(locator, selectorFamily, visibleOnly, timeoutMs);

      const text = extra?.text ?? '';
      const clearFirst = extra?.clearFirst !== false;

      if (clearFirst) {
        setInputValue(el, '');
      }

      await humanType(el, text, humanLike);

      // If inputAndPressEnter, also dispatch Enter key
      if (extra?.pressEnter) {
        if (humanLike) await sleep(rand(200, 600));
        el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        if (humanLike) await sleep(rand(30, 100));
        el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true }));
      }

      return { input: true, length: text.length };
    },

    async extract({ locator, selectorFamily, extra }) {
      const visibleOnly = extra?.visibleOnly ?? true;
      const timeoutMs = (extra?.timeout ?? 10) * 1000;

      let el;
      const ctxLocator = extra?.contextLocator;
      const ctxLocatorType = extra?.contextLocatorType;
      const ctxIndex = extra?.contextIndex ?? 0;

      if (ctxLocator) {
        const parents = resolveAllLocators(ctxLocator, ctxLocatorType);
        const parent = parents[ctxIndex];
        if (!parent) throw new Error('上下文元素未找到');
        el = await waitForElementInContext(locator, selectorFamily, parent, timeoutMs);
        if (visibleOnly && !isVisible(el)) {
          const all = resolveAllLocatorsInContext(locator, selectorFamily, parent);
          const v = all.find(isVisible);
          if (v) el = v;
        }
      } else {
        el = await waitForElement(locator, selectorFamily, visibleOnly, timeoutMs);
      }

      const attr = extra?.attribute;
      let value;
      if (attr === 'innerHTML') {
        value = el.innerHTML;
      } else if (attr === 'value') {
        value = el.value;
      } else if (attr) {
        value = el.getAttribute(attr);
      } else {
        value = el.textContent?.trim() ?? '';
      }
      return { extracted: value };
    },

    wait({ extra }) {
      const ms = (extra?.seconds || 1) * 1000;
      return new Promise((resolve) => {
        setTimeout(() => resolve({ waited: ms }), ms);
      });
    },

    async scroll({ locator, selectorFamily, extra }) {
      const scrollType = extra?.scrollType || 'toBottom';
      const humanLike = extra?.humanLike ?? true;
      const smooth = extra?.smooth ?? true;

      // scrollIntoView mode (element target)
      if (scrollType === 'intoView' || locator) {
        const visibleOnly = extra?.visibleOnly ?? true;
        const timeoutMs = (extra?.timeout ?? 10) * 1000;
        const el = await waitForElement(locator, selectorFamily, visibleOnly, timeoutMs);
        if (humanLike) {
          const rect = el.getBoundingClientRect();
          const targetY = rect.top + window.scrollY;
          const currentY = window.scrollY;
          const diff = targetY - currentY - window.innerHeight / 2;
          await humanScroll(diff > 0 ? 'down' : 'up', Math.abs(diff), true);
        } else {
          const block = extra?.block || 'center';
          el.scrollIntoView({ behavior: smooth ? 'smooth' : 'instant', block });
        }
        return { scrolled: 'intoView' };
      }

      // Page scroll modes
      if (scrollType === 'oneScreen') {
        const amount = window.innerHeight * 3;
        await humanScroll('down', amount, humanLike);
        return { scrolled: 'oneScreen', amount };
      }

      const direction = {
        'toBottom': 'bottom',
        'toTop': 'top',
        'by': (extra?.y || 500) >= 0 ? 'down' : 'up',
      }[scrollType] || 'bottom';
      const amount = scrollType === 'by' ? Math.abs(extra?.y || 500) : 0;
      await humanScroll(direction, amount, humanLike);
      return { scrolled: direction, amount };
    },

    goBack() {
      window.history.back();
      return { wentBack: true };
    },

    goForward() {
      window.history.forward();
      return { wentForward: true };
    },

    refresh() {
      window.location.reload();
      return { refreshed: true };
    },

    async pressKey({ extra }) {
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
    },

    async hover({ locator, selectorFamily, extra }) {
      const visibleOnly = extra?.visibleOnly ?? true;
      const humanLike = extra?.humanLike ?? true;
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const el = await waitForElement(locator, selectorFamily, visibleOnly, timeoutMs);
      const point = getClickPoint(el, humanLike);
      const rect = el.getBoundingClientRect();
      const startX = rect.left + rect.width / 2;
      const startY = rect.top + rect.height / 2;
      if (humanLike) {
        await moveMouseBezier(startX, startY, point.x, point.y, true);
        await hoverWiggle(point.x, point.y);
      }
      el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, cancelable: true, view: window, clientX: point.x, clientY: point.y }));
      el.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true, cancelable: true, view: window, clientX: point.x, clientY: point.y }));
      return { hovered: true, tagName: el.tagName };
    },

    async clearInput({ locator, selectorFamily, extra }) {
      const visibleOnly = extra?.visibleOnly ?? true;
      const humanLike = extra?.humanLike ?? true;
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const el = await waitForElement(locator, selectorFamily, visibleOnly, timeoutMs);
      if (humanLike) await visualConfirmDelay();
      setInputValue(el, '');
      return { cleared: true };
    },

    async selectOption({ locator, selectorFamily, extra }) {
      const visibleOnly = extra?.visibleOnly ?? true;
      const humanLike = extra?.humanLike ?? true;
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const el = await waitForElement(locator, selectorFamily, visibleOnly, timeoutMs);
      const value = extra?.value;
      if (!value) throw new Error('selectOption: value required');
      if (humanLike) await visualConfirmDelay();

      // Try select.by_value first
      let option = el.querySelector(`option[value="${CSS.escape(value)}"]`);
      if (!option) {
        // Fallback: select.by_text
        option = Array.from(el.options).find(o => o.textContent.trim() === value);
      }
      if (option) {
        const descriptor = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
        if (descriptor && descriptor.set) {
          descriptor.set.call(el, option.value);
        } else {
          el.value = option.value;
        }
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return { selected: option.value, text: option.textContent };
      }
      throw new Error(`selectOption: option "${value}" not found`);
    },

    newTab({ extra }) {
      const url = extra?.url;
      if (!url) throw new Error('newTab: url required');
      window.open(url, '_blank');
      return { opened: url };
    },

    executeJs({ extra }) {
      const script = extra?.script;
      if (!script) throw new Error('executeJs: script required');
      // eslint-disable-next-line no-eval
      const result = eval(script);
      return { executed: true, result: String(result) };
    },

    // ─── Condition check handlers ───────────────────────────────────

    async checkElementExists({ locator, selectorFamily, extra }) {
      const visibleOnly = extra?.visibleOnly ?? true;
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const ctxLocator = extra?.contextLocator;
      const ctxLocatorType = extra?.contextLocatorType;
      const ctxIndex = extra?.contextIndex ?? 0;
      try {
        if (ctxLocator) {
          const parents = resolveAllLocators(ctxLocator, ctxLocatorType);
          const parent = parents[ctxIndex];
          if (!parent) return { exists: false };
          await waitForElementInContext(locator, selectorFamily, parent, timeoutMs);
        } else {
          await waitForElement(locator, selectorFamily, visibleOnly, timeoutMs);
        }
        return { exists: true };
      } catch (e) {
        return { exists: false };
      }
    },

    async checkElementVisible({ locator, selectorFamily, extra }) {
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const ctxLocator = extra?.contextLocator;
      const ctxLocatorType = extra?.contextLocatorType;
      const ctxIndex = extra?.contextIndex ?? 0;
      console.log(`[RPA checkElementVisible] start locator=${JSON.stringify(locator)} type=${selectorFamily} ctx=${ctxLocator ? 'yes' : 'no'} timeout=${timeoutMs}`);
      try {
        let el;
        if (ctxLocator) {
          const parents = resolveAllLocators(ctxLocator, ctxLocatorType);
          const parent = parents[ctxIndex];
          if (!parent) {
            console.log('[RPA checkElementVisible] context parent not found');
            return { visible: false };
          }
          el = await waitForElementInContext(locator, selectorFamily, parent, timeoutMs);
        } else {
          el = await waitForElement(locator, selectorFamily, false, timeoutMs);
        }
        const vis = isVisible(el);
        console.log(`[RPA checkElementVisible] result tag=${el?.tagName} visible=${vis}`);
        return { visible: vis };
      } catch (e) {
        console.log(`[RPA checkElementVisible] ERROR: ${e.message}`);
        return { visible: false };
      }
    },

    async getElementText({ locator, selectorFamily, extra }) {
      const visibleOnly = extra?.visibleOnly ?? true;
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const ctxLocator = extra?.contextLocator;
      const ctxLocatorType = extra?.contextLocatorType;
      const ctxIndex = extra?.contextIndex ?? 0;
      let el;
      if (ctxLocator) {
        const parents = resolveAllLocators(ctxLocator, ctxLocatorType);
        const parent = parents[ctxIndex];
        if (!parent) throw new Error('上下文元素未找到');
        el = await waitForElementInContext(locator, selectorFamily, parent, timeoutMs);
        if (visibleOnly && !isVisible(el)) {
          const all = resolveAllLocatorsInContext(locator, selectorFamily, parent);
          const v = all.find(isVisible);
          if (v) el = v;
        }
      } else {
        el = await waitForElement(locator, selectorFamily, visibleOnly, timeoutMs);
      }
      return { text: el.textContent?.trim() ?? '' };
    },

    getCurrentUrl() {
      return { url: window.location.href };
    },

    async findElements({ locator, selectorFamily, extra }) {
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const ctxLocator = extra?.contextLocator;
      const ctxLocatorType = extra?.contextLocatorType;
      const ctxIndex = extra?.contextIndex ?? 0;
      const start = Date.now();
      let elements = [];
      while (Date.now() - start < timeoutMs) {
        if (ctxLocator) {
          const parents = resolveAllLocators(ctxLocator, ctxLocatorType);
          const parent = parents[ctxIndex];
          if (parent) {
            elements = resolveAllLocatorsInContext(locator, selectorFamily, parent);
          }
        } else {
          elements = resolveAllLocators(locator, selectorFamily);
        }
        if (elements.length > 0) break;
        await sleep(200);
      }
      const items = elements.map((el, idx) => ({
        text: el.textContent?.trim() ?? '',
        html: el.innerHTML?.slice(0, 500) ?? '',
        tagName: el.tagName,
        index: idx,
      }));
      return { count: items.length, items };
    },

    // ─── Network interception handlers ──────────────────────────────

    traceNetwork({ extra }) {
      const duration = (extra?.duration || 5) * 1000;
      const urlPattern = extra?.urlPattern || '*';
      _traceResults.length = 0;
      _interceptActive = true;
      injectInterceptScript({ mode: 'trace', urlPattern, method: 'ALL', captureResponse: false });
      return new Promise((resolve) => {
        setTimeout(() => {
          removeInterceptScript();
          const urls = _traceResults.map(r => `${r.method} ${r.url}`);
          resolve({ traced: _traceResults.length, urls });
        }, duration);
      });
    },

    interceptNetwork({ extra }) {
      const urlPattern = extra?.urlPattern || '*';
      const method = extra?.method || 'ALL';
      const captureResponse = extra?.captureResponse !== false;
      _interceptQueue.length = 0;
      _interceptActive = true;
      injectInterceptScript({ mode: 'intercept', urlPattern, method, captureResponse });
      return { started: true, pattern: urlPattern, method, captureResponse };
    },

    waitForNetwork({ extra }) {
      const urlPattern = extra?.urlPattern || '*';
      const timeoutMs = (extra?.timeout || 10) * 1000;
      const start = Date.now();
      if (!_interceptActive) {
        // Auto-start intercept if not active
        interceptNetwork({ extra: { urlPattern } });
      }
      return new Promise((resolve, reject) => {
        const tick = () => {
          const elapsed = Date.now() - start;
          const match = _interceptQueue.find(item => matchPattern(item.url, urlPattern));
          if (match) {
            resolve({ matched: true, url: match.url, data: tryJsonParse(match.body) });
            return;
          }
          if (elapsed >= timeoutMs) {
            reject(new Error(`waitForNetwork 超时: ${timeoutMs}ms 内未匹配到 ${urlPattern}`));
            return;
          }
          setTimeout(tick, 200);
        };
        tick();
      });
    },

    getInterceptedData({ extra }) {
      const limit = extra?.limit || 100;
      const data = _interceptQueue.slice(0, limit).map(item => ({
        url: item.url,
        method: item.method,
        status: item.status,
        data: tryJsonParse(item.body),
      }));
      return { count: data.length, data };
    },

    previewInterceptData() {
      if (_interceptQueue.length === 0) return { preview: null };
      const first = _interceptQueue[0];
      return { preview: { url: first.url, data: tryJsonParse(first.body) } };
    },

    logInterceptedData() {
      const summary = _interceptQueue.slice(0, 5).map((item, idx) => {
        const data = tryJsonParse(item.body);
        const preview = typeof data === 'object'
          ? JSON.stringify(data).slice(0, 180)
          : String(data).slice(0, 180);
        return `${idx + 1}. [${item.method}] ${item.url} → ${preview}...`;
      });
      console.log('[RPA Intercept] 已拦截数据摘要 (' + _interceptQueue.length + ' 条):\n' + summary.join('\n'));
      return { logged: _interceptQueue.length, summary };
    },

    clearInterceptedData() {
      const count = _interceptQueue.length;
      _interceptQueue.length = 0;
      return { cleared: count };
    },

    stopIntercept() {
      removeInterceptScript();
      return { stopped: true, remaining: _interceptQueue.length };
    },
  };

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

        // Compute matched count for logging
        let matchedCount = result?.matchedCount;
        if (targetLocator && matchedCount === undefined) {
          const ctxLocator = extra?.contextLocator;
          const ctxLocatorType = extra?.contextLocatorType;
          const ctxIndex = extra?.contextIndex ?? 0;
          const visibleOnly = extra?.visibleOnly !== false;
          if (ctxLocator) {
            const parents = resolveAllLocators(ctxLocator, ctxLocatorType);
            const parent = parents[ctxIndex];
            if (parent) {
              const all = resolveAllLocatorsInContext(targetLocator, targetLocatorType, parent);
              matchedCount = visibleOnly ? all.filter(isVisible).length : all.length;
            }
          } else {
            const all = resolveAllLocators(targetLocator, targetLocatorType);
            matchedCount = visibleOnly ? all.filter(isVisible).length : all.length;
          }
          console.log(`[RPA Agent] matched ${matchedCount} element(s) for locator=${targetLocator}`);
        }

        addRunLog(`${type} 完成`);
        safeRespond({ status: 'success', result: { ...result, matchedIndex, matchedCount } });
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
