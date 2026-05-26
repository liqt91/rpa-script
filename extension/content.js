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

  // ─── Step handlers ───────────────────────────────────────────────

  const handlers = {
    navigate({ extra }) {
      const url = extra?.url;
      if (!url) throw new Error('navigate: url required');
      window.location.href = url;
      return { navigatedTo: url };
    },

    click({ locator, locatorType, extra }) {
      const el = resolveLocator(locator, locatorType, extra?.visibleOnly);
      if (!el) throw new Error(`click: element not found: ${locator}`);

      if (el.click) {
        el.click();
      } else {
        const evt = new MouseEvent('click', { bubbles: true, cancelable: true, view: window });
        el.dispatchEvent(evt);
      }
      return { clicked: true, tagName: el.tagName };
    },

    input({ locator, locatorType, extra }) {
      const el = resolveLocator(locator, locatorType, extra?.visibleOnly);
      if (!el) throw new Error(`input: element not found: ${locator}`);

      const text = extra?.text ?? '';
      const clearFirst = extra?.clearFirst !== false;

      if (clearFirst) {
        el.value = '';
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }

      el.value = text;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));

      // If inputAndPressEnter, also dispatch Enter key
      if (extra?.pressEnter) {
        el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true }));
      }

      return { input: true, length: text.length };
    },

    extract({ locator, locatorType, extra }) {
      const el = resolveLocator(locator, locatorType, extra?.visibleOnly);
      if (!el) throw new Error(`extract: element not found: ${locator}`);

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

    scroll({ extra }) {
      const direction = extra?.direction || 'down';
      const amount = extra?.amount || 500;
      if (direction === 'down') {
        window.scrollBy(0, amount);
      } else if (direction === 'up') {
        window.scrollBy(0, -amount);
      } else if (direction === 'bottom') {
        window.scrollTo(0, document.body.scrollHeight);
      } else if (direction === 'top') {
        window.scrollTo(0, 0);
      }
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

    pressKey({ extra }) {
      const key = extra?.key || 'Enter';
      document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
      document.dispatchEvent(new KeyboardEvent('keyup', { key, bubbles: true }));
      return { pressed: key };
    },

    hover({ locator, locatorType, extra }) {
      const el = resolveLocator(locator, locatorType, extra?.visibleOnly);
      if (!el) throw new Error(`hover: element not found: ${locator}`);
      el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, cancelable: true, view: window }));
      el.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true, cancelable: true, view: window }));
      return { hovered: true, tagName: el.tagName };
    },

    clearInput({ locator, locatorType, extra }) {
      const el = resolveLocator(locator, locatorType, extra?.visibleOnly);
      if (!el) throw new Error(`clearInput: element not found: ${locator}`);
      el.value = '';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
      return { cleared: true };
    },

    selectOption({ locator, locatorType, extra }) {
      const el = resolveLocator(locator, locatorType, extra?.visibleOnly);
      if (!el) throw new Error(`selectOption: element not found: ${locator}`);
      const value = extra?.value;
      if (!value) throw new Error('selectOption: value required');

      // Try select.by_value first
      let option = el.querySelector(`option[value="${CSS.escape(value)}"]`);
      if (!option) {
        // Fallback: select.by_text
        option = Array.from(el.options).find(o => o.textContent.trim() === value);
      }
      if (option) {
        el.value = option.value;
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

    try {
      const result = handler({ locator, locatorType, extra: extra || {} });
      if (result instanceof Promise) {
        result
          .then((r) => sendResponse({ status: 'success', result: r }))
          .catch((e) => sendResponse({ status: 'error', error: e.message }));
        return true;
      }
      sendResponse({ status: 'success', result });
    } catch (e) {
      sendResponse({ status: 'error', error: e.message });
    }
    return false;
  });

  console.log(`[RPA Agent] Content script injected v${AGENT_VERSION}`);
})();
