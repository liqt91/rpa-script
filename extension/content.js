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

  function resolveLocator(locator, locatorType) {
    if (!locator) return document;
    switch (locatorType) {
      case 'xpath':
        return document.evaluate(locator, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
      case 'id':
        return document.getElementById(locator);
      case 'class':
        return document.querySelector('.' + locator);
      case 'text':
        return document.evaluate(
          `//*[contains(text(), ${JSON.stringify(locator)})]`,
          document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
        ).singleNodeValue;
      case 'data-attr':
        return document.querySelector(`[data-${locator}]`);
      case 'css':
      default:
        return document.querySelector(locator);
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

    click({ locator, locatorType, extra }) {
      const el = resolveLocator(locator, locatorType);
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
      const el = resolveLocator(locator, locatorType);
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
      const el = resolveLocator(locator, locatorType);
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
      const el = resolveLocator(locator, locatorType);
      if (!el) throw new Error(`hover: element not found: ${locator}`);
      el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, cancelable: true, view: window }));
      el.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true, cancelable: true, view: window }));
      return { hovered: true, tagName: el.tagName };
    },

    clearInput({ locator, locatorType, extra }) {
      const el = resolveLocator(locator, locatorType);
      if (!el) throw new Error(`clearInput: element not found: ${locator}`);
      el.value = '';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
      return { cleared: true };
    },

    selectOption({ locator, locatorType, extra }) {
      const el = resolveLocator(locator, locatorType);
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
