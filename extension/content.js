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
    return el.offsetParent !== null && style.visibility !== 'hidden' && style.display !== 'none';
  }

  function inferLocatorType(locator) {
    if (locator.startsWith('css:')) return 'css';
    if (locator.startsWith('xpath:')) return 'xpath';
    if (locator.startsWith('tag:') && locator.includes('@class=')) return 'tag_class';
    if (locator.startsWith('tag:') && locator.includes('@text()=')) return 'tag_text';
    if (locator.startsWith('tag:') && locator.includes('@')) return 'tag_attr';
    if (locator.startsWith('@@class:')) return 'multi_attr';
    if (locator.startsWith('text=')) return 'text';
    if (locator.startsWith('@')) return 'data-attr';
    if (locator.startsWith('#')) return 'id';
    if (locator.startsWith('.')) return 'class';
    if (locator.startsWith('//')) return 'xpath';
    return null;
  }

  function resolveAllLocators(locator, locatorType) {
    if (!locator) return [];
    if (locator.startsWith('css:')) { locator = locator.slice(4); locatorType = 'css'; }
    if (locator.startsWith('xpath:')) { locator = locator.slice(6); locatorType = 'xpath'; }
    const inferred = inferLocatorType(locator);
    if (inferred && inferred !== locatorType) locatorType = inferred;

    if (locatorType === 'xpath') {
      const r = document.evaluate(locator, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
      const arr = [];
      for (let i = 0; i < r.snapshotLength; i++) arr.push(r.snapshotItem(i));
      return arr;
    }
    if (locatorType === 'text') {
      const text = locator.startsWith('text=') ? locator.slice(5) : locator;
      const r = document.evaluate(`//*[contains(text(), ${JSON.stringify(text)})]`, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
      const arr = [];
      for (let i = 0; i < r.snapshotLength; i++) arr.push(r.snapshotItem(i));
      return arr;
    }
    if (locatorType === 'tag_text') {
      const m = locator.match(/^tag:(\w+)@text\(\)=(.+)$/);
      if (m) {
        const r = document.evaluate(`//${m[1]}[contains(text(), ${JSON.stringify(m[2])})]`, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        const arr = [];
        for (let i = 0; i < r.snapshotLength; i++) arr.push(r.snapshotItem(i));
        return arr;
      }
      return [];
    }

    let selector = locator;
    if (locatorType === 'id') selector = locator.startsWith('#') ? locator : '#' + locator;
    else if (locatorType === 'class') selector = locator.startsWith('.') ? locator : '.' + locator;
    else if (locatorType === 'data-attr' || locatorType === 'aria' || locatorType === 'name') {
      let l = locator;
      if (l.startsWith('@')) l = l.slice(1);
      const eq = l.indexOf('=');
      if (eq > 0) {
        selector = `[${l.slice(0, eq)}=${JSON.stringify(l.slice(eq + 1))}]`;
      } else {
        selector = `[data-${l}]`;
      }
    } else if (locatorType === 'tag_attr') {
      const m = locator.match(/^tag:(\w+)@(\w+)=(.+)$/);
      if (m) selector = `${m[1]}[${m[2]}=${JSON.stringify(m[3])}]`;
    } else if (locatorType === 'tag_class') {
      const m = locator.match(/^tag:(\w+)@class=(.+)$/);
      if (m) selector = `${m[1]}.${m[2]}`;
    } else if (locatorType === 'multi_attr') {
      const parts = locator.match(/@@class:([^@]+)/g);
      if (parts) selector = parts.map(p => '.' + p.replace('@@class:', '')).join('');
    }
    try { return Array.from(document.querySelectorAll(selector)); } catch (e) {}
    return [];
  }

  function resolveLocator(locator, locatorType, visibleOnly) {
    if (!locator) return document;

    // Normalize css:/xpath: prefixes
    if (locator.startsWith('css:')) {
      locator = locator.slice(4);
      locatorType = 'css';
    }
    if (locator.startsWith('xpath:')) {
      locator = locator.slice(6);
      locatorType = 'xpath';
    }
    const inferred = inferLocatorType(locator);
    if (inferred && inferred !== locatorType) locatorType = inferred;

    let el = null;
    switch (locatorType) {
      case 'xpath':
        el = document.evaluate(locator, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        break;
      case 'id':
        el = locator.startsWith('#') ? document.querySelector(locator) : document.getElementById(locator);
        break;
      case 'class':
        el = document.querySelector(locator.startsWith('.') ? locator : '.' + locator);
        break;
      case 'text': {
        const text = locator.startsWith('text=') ? locator.slice(5) : locator;
        el = document.evaluate(`//*[contains(text(), ${JSON.stringify(text)})]`, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        break;
      }
      case 'tag_text': {
        const m = locator.match(/^tag:(\w+)@text\(\)=(.+)$/);
        if (m) {
          el = document.evaluate(`//${m[1]}[contains(text(), ${JSON.stringify(m[2])})]`, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        }
        break;
      }
      case 'data-attr':
      case 'aria':
      case 'name': {
        let l = locator;
        if (l.startsWith('@')) l = l.slice(1);
        const eq = l.indexOf('=');
        if (eq > 0) {
          el = document.querySelector(`[${l.slice(0, eq)}=${JSON.stringify(l.slice(eq + 1))}]`);
        } else {
          el = document.querySelector(`[data-${l}]`);
        }
        break;
      }
      case 'tag_attr': {
        const m = locator.match(/^tag:(\w+)@(\w+)=(.+)$/);
        if (m) el = document.querySelector(`${m[1]}[${m[2]}=${JSON.stringify(m[3])}]`);
        break;
      }
      case 'tag_class': {
        const m = locator.match(/^tag:(\w+)@class=(.+)$/);
        if (m) el = document.querySelector(`${m[1]}.${m[2]}`);
        break;
      }
      case 'multi_attr': {
        const parts = locator.match(/@@class:([^@]+)/g);
        if (parts) {
          const cls = parts.map(p => '.' + p.replace('@@class:', '')).join('');
          el = document.querySelector(cls);
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
      const all = resolveAllLocators(locator, locatorType);
      const v = all.find(isVisible);
      if (v) return v;
    }
    return el;
  }

  function waitForElement(locator, locatorType, visibleOnly, timeoutMs = 10000, pollMs = 200) {
    const start = Date.now();
    return new Promise((resolve, reject) => {
      const tick = () => {
        const el = resolveLocator(locator, locatorType, visibleOnly);
        if (el && el !== document) return resolve(el);
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
    if (!humanLike) {
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

  // 拟人滚动
  async function humanScroll(direction, amount, humanLike) {
    if (!humanLike) {
      if (direction === 'down') window.scrollBy(0, amount);
      else if (direction === 'up') window.scrollBy(0, -amount);
      else if (direction === 'bottom') window.scrollTo(0, document.body.scrollHeight);
      else if (direction === 'top') window.scrollTo(0, 0);
      return;
    }
    const total = direction === 'down' ? amount : (direction === 'up' ? -amount : 0);
    if (direction === 'bottom') {
      const target = document.body.scrollHeight;
      let current = window.scrollY;
      while (current < target) {
        const step = randInt(100, 400);
        window.scrollBy(0, step);
        current += step;
        await sleep(rand(100, 300));
        if (Math.random() < 0.15) {
          window.scrollBy(0, randInt(-10, -3));
          await sleep(rand(50, 150));
        }
      }
      return;
    }
    if (direction === 'top') {
      let current = window.scrollY;
      while (current > 0) {
        const step = randInt(100, 400);
        window.scrollBy(0, -step);
        current -= step;
        await sleep(rand(100, 300));
        if (Math.random() < 0.15) {
          window.scrollBy(0, randInt(3, 10));
          await sleep(rand(50, 150));
        }
      }
      return;
    }
    let scrolled = 0;
    while (Math.abs(scrolled) < Math.abs(total)) {
      const step = Math.min(randInt(100, 400), Math.abs(total) - Math.abs(scrolled));
      window.scrollBy(0, total > 0 ? step : -step);
      scrolled += step;
      await sleep(rand(100, 300));
      if (Math.random() < 0.1) {
        window.scrollBy(0, total > 0 ? randInt(-5, -1) : randInt(1, 5));
        await sleep(rand(50, 150));
      }
    }
  }

  // ─── Step handlers ───────────────────────────────────────────────

  const handlers = {
    navigate({ extra }) {
      const url = extra?.url;
      if (!url) throw new Error('navigate: url required');
      window.location.href = url;
      return { navigatedTo: url };
    },

    async click({ locator, locatorType, extra }) {
      const visibleOnly = extra?.visibleOnly ?? true;
      const humanLike = extra?.humanLike ?? true;
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const el = await waitForElement(locator, locatorType, visibleOnly, timeoutMs);

      await visualConfirmDelay();
      await humanClick(el, humanLike);
      return { clicked: true, tagName: el.tagName };
    },

    async input({ locator, locatorType, extra }) {
      const visibleOnly = extra?.visibleOnly ?? true;
      const humanLike = extra?.humanLike ?? true;
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const el = await waitForElement(locator, locatorType, visibleOnly, timeoutMs);

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

    async extract({ locator, locatorType, extra }) {
      const visibleOnly = extra?.visibleOnly ?? true;
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const el = await waitForElement(locator, locatorType, visibleOnly, timeoutMs);

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

    async scroll({ locator, locatorType, extra }) {
      const humanLike = extra?.humanLike ?? true;
      if (locator) {
        const visibleOnly = extra?.visibleOnly ?? true;
        const timeoutMs = (extra?.timeout ?? 10) * 1000;
        const el = await waitForElement(locator, locatorType, visibleOnly, timeoutMs);
        if (humanLike) {
          const rect = el.getBoundingClientRect();
          const targetY = rect.top + window.scrollY;
          const currentY = window.scrollY;
          const diff = targetY - currentY - window.innerHeight / 2;
          await humanScroll(diff > 0 ? 'down' : 'up', Math.abs(diff), true);
        } else {
          const block = extra?.block || 'center';
          el.scrollIntoView({ behavior: 'smooth', block });
        }
        return { scrolled: 'intoView' };
      }
      const direction = extra?.direction || 'down';
      const amount = extra?.amount || 500;
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

    async hover({ locator, locatorType, extra }) {
      const visibleOnly = extra?.visibleOnly ?? true;
      const humanLike = extra?.humanLike ?? true;
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const el = await waitForElement(locator, locatorType, visibleOnly, timeoutMs);
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

    async clearInput({ locator, locatorType, extra }) {
      const visibleOnly = extra?.visibleOnly ?? true;
      const humanLike = extra?.humanLike ?? true;
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const el = await waitForElement(locator, locatorType, visibleOnly, timeoutMs);
      if (humanLike) await visualConfirmDelay();
      setInputValue(el, '');
      return { cleared: true };
    },

    async selectOption({ locator, locatorType, extra }) {
      const visibleOnly = extra?.visibleOnly ?? true;
      const humanLike = extra?.humanLike ?? true;
      const timeoutMs = (extra?.timeout ?? 10) * 1000;
      const el = await waitForElement(locator, locatorType, visibleOnly, timeoutMs);
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
  };

  // ─── Message listener ────────────────────────────────────────────

  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action !== 'executeStep') return false;

    const { step } = request;
    const { type, locator, locatorType, extra } = step;
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

        console.log(`[RPA Agent] executing step type=${type} humanLike=${extra?.humanLike ?? true}`);
        const result = await handler({ locator, locatorType, extra: extra || {} });
        _lastOpTime = performance.now();
        clearTimeout(timeoutId);
        safeRespond({ status: 'success', result });
      } catch (e) {
        console.error(`[RPA Agent] step ${type} failed:`, e);
        clearTimeout(timeoutId);
        safeRespond({ status: 'error', error: e?.message || String(e) });
      }
    })();

    return true;
  });

  console.log(`[RPA Agent] Content script injected v${AGENT_VERSION}`);
})();
