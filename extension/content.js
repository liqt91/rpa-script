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
        // Simple text matching via XPath
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

      // Try native click first, fallback to MouseEvent
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

      return { input: true, length: text.length };
    },

    extract({ locator, locatorType, extra }) {
      const el = resolveLocator(locator, locatorType);
      if (!el) throw new Error(`extract: element not found: ${locator}`);

      const attr = extra?.attribute;
      let value;
      if (attr) {
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

    // Execute handler (sync or async)
    try {
      const result = handler({ locator, locatorType, extra: extra || {} });
      if (result instanceof Promise) {
        result
          .then((r) => sendResponse({ status: 'success', result: r }))
          .catch((e) => sendResponse({ status: 'error', error: e.message }));
        return true; // Keep channel open for async
      }
      sendResponse({ status: 'success', result });
    } catch (e) {
      sendResponse({ status: 'error', error: e.message });
    }
    return false;
  });

  console.log(`[RPA Agent] Content script injected v${AGENT_VERSION}`);
})();
