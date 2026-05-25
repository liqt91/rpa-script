/**
 * RPA Script Browser Agent — Background Service Worker
 *
 * Architecture:
 *   Backend (FastAPI WS)  <--WebSocket-->  background.js  <--chrome.tabs.sendMessage-->  content.js  <--DOM-->  Page
 */

const DEFAULT_WS_URL = 'ws://localhost:8000/api/extension/ws';

class AgentBackground {
  constructor() {
    this.ws = null;
    this.reconnectTimer = null;
    this.pingTimer = null;
    this.clientId = null;
    this.pendingSteps = new Map(); // stepId -> {resolve, reject, timer}
    this.workTabId = null;         // 工作流专用标签页 ID
  }

  async start() {
    const cfg = await chrome.storage.local.get('wsUrl');
    const wsUrl = cfg.wsUrl || DEFAULT_WS_URL;
    this._connect(wsUrl);
  }

  _connect(wsUrl) {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    console.log('[Agent] Connecting to', wsUrl);
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log('[Agent] WS connected');
      this._send('register', { browser: this._detectBrowser(), version: chrome.runtime.getManifest().version });
      this._startPing();
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        this._onBackendMessage(msg);
      } catch (e) {
        console.error('[Agent] Invalid JSON from backend:', e);
      }
    };

    this.ws.onclose = () => {
      console.log('[Agent] WS closed, reconnecting in 3s...');
      this._stopPing();
      this.reconnectTimer = setTimeout(() => this._connect(wsUrl), 3000);
    };

    this.ws.onerror = (err) => {
      console.error('[Agent] WS error:', err);
    };
  }

  _detectBrowser() {
    const ua = navigator.userAgent;
    if (ua.includes('Edg/')) return 'edge';
    if (ua.includes('Chrome/')) return 'chrome';
    return 'unknown';
  }

  _send(action, payload = {}) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action, payload }));
    }
  }

  _startPing() {
    this.pingTimer = setInterval(() => {
      this._send('ping');
    }, 15000);
  }

  _stopPing() {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  /**
   * Handle messages from backend.
   * Expected actions:
   *   - executeStep: { stepId, type, locator, locatorType, action, extra }
   */
  async _onBackendMessage(msg) {
    const { action, payload } = msg;

    if (action === 'pong') return;

    if (action === 'executeStep') {
      await this._handleExecuteStep(payload);
      return;
    }

    console.log('[Agent] Unknown backend action:', action);
  }

  _isRestrictedUrl(url) {
    if (!url) return true;
    const restricted = ['chrome://', 'edge://', 'chrome-extension://', 'about:', 'file://', 'data:', 'javascript:'];
    return restricted.some(p => url.startsWith(p));
  }

  async _ensureWorkTab(step) {
    // Check if current workTabId is still valid and not restricted
    let workTab = null;
    if (this.workTabId) {
      try {
        workTab = await chrome.tabs.get(this.workTabId);
        if (!workTab || this._isRestrictedUrl(workTab.url)) {
          workTab = null;
        }
      } catch (e) {
        workTab = null;
      }
    }

    // If we have a valid work tab, use it
    if (workTab) {
      return workTab.id;
    }

    // No valid work tab — try active tab first
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (activeTab?.id && !this._isRestrictedUrl(activeTab.url)) {
      this.workTabId = activeTab.id;
      return activeTab.id;
    }

    // Active tab is restricted or missing
    if (step.type === 'navigate') {
      const url = step.extra?.url;
      if (!url) throw new Error('navigate: url required');
      // Create new tab for navigate
      const newTab = await chrome.tabs.create({ url });
      this.workTabId = newTab.id;
      // Wait for tab to start loading, then inject content script
      await new Promise(r => setTimeout(r, 500));
      try { await this._injectContentScript(newTab.id); } catch (e) {}
      return newTab.id;
    }

    throw new Error('当前页面不支持自动化，请切换到普通网页标签页后重试');
  }

  async _injectContentScript(tabId) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ['content.js'],
      });
      console.log('[Agent] content.js injected into tab', tabId);
    } catch (e) {
      console.warn('[Agent] content.js injection failed:', e.message);
      throw e;
    }
  }

  async _executeStepOnTab(tabId, step) {
    return await chrome.tabs.sendMessage(tabId, {
      action: 'executeStep',
      step,
    });
  }

  async _handleExecuteStep(step) {
    const { stepId, type } = step;

    try {
      // Ensure we have a valid work tab (creates new one for navigate if needed)
      const tabId = await this._ensureWorkTab(step);

      // Special case: navigate on a new tab already navigated — just confirm
      if (type === 'navigate') {
        const tab = await chrome.tabs.get(tabId);
        const targetUrl = step.extra?.url || '';
        // If the tab was just created with the target URL, skip content script execution
        if (tab.url === targetUrl || tab.pendingUrl === targetUrl) {
          this._send('stepResult', { stepId, result: { navigatedTo: targetUrl, newTab: true } });
          return;
        }
      }

      // Try sending directly; if content script is missing, inject and retry once
      let result;
      try {
        result = await this._executeStepOnTab(tabId, step);
      } catch (sendErr) {
        const msg = sendErr?.message || '';
        if (msg.includes('Receiving end does not exist') || msg.includes('Could not establish connection')) {
          await this._injectContentScript(tabId);
          await new Promise(r => setTimeout(r, 200));
          result = await this._executeStepOnTab(tabId, step);
        } else {
          throw sendErr;
        }
      }

      if (result?.status === 'success') {
        this._send('stepResult', { stepId, result: result.result });
      } else {
        this._send('stepError', { stepId, error: result?.error || 'Unknown content error' });
      }
    } catch (err) {
      console.error('[Agent] executeStep failed:', err);
      this._send('stepError', { stepId, error: err.message });
    }
  }
}

// Start agent
const agent = new AgentBackground();
agent.start();

// ── Handle messages from content scripts (e.g. captureElement) ──

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'captureElement') {
    // Forward to backend via WebSocket
    agent._send('captureElement', message.payload);
    sendResponse({ forwarded: true });
    return false;
  }
  if (message.action === 'captureScreenshot') {
    chrome.tabs.captureVisibleTab({ format: 'png' })
      .then(dataUrl => sendResponse({ dataUrl }))
      .catch(err => sendResponse({ error: err.message }));
    return true; // async response
  }

  if (message.action === 'captureElementScreenshot') {
    const { rect, dpr = 1 } = message;
    const padding = 10 * dpr;

    chrome.tabs.captureVisibleTab({ format: 'png' })
      .then(async (dataUrl) => {
        try {
          const resp = await fetch(dataUrl);
          const blob = await resp.blob();
          const bitmap = await createImageBitmap(blob);

          const sx = Math.max(0, Math.round(rect.left * dpr - padding));
          const sy = Math.max(0, Math.round(rect.top * dpr - padding));
          const sw = Math.min(bitmap.width - sx, Math.round(rect.width * dpr + padding * 2));
          const sh = Math.min(bitmap.height - sy, Math.round(rect.height * dpr + padding * 2));

          const canvas = new OffscreenCanvas(sw, sh);
          const ctx = canvas.getContext('2d');
          ctx.drawImage(bitmap, sx, sy, sw, sh, 0, 0, sw, sh);

          const croppedBlob = await canvas.convertToBlob({ type: 'image/png' });
          const reader = new FileReader();
          reader.onloadend = () => sendResponse({ dataUrl: reader.result });
          reader.readAsDataURL(croppedBlob);
        } catch (err) {
          sendResponse({ error: err.message });
        }
      })
      .catch(err => sendResponse({ error: err.message }));
    return true; // async response
  }

  if (message.action === 'notifyElementCaptured') {
    // Broadcast to all tabs so workflow editor and admin pages can refresh
    chrome.tabs.query({}, (tabs) => {
      console.log('[Agent] Broadcasting elementCaptured to', tabs.length, 'tabs');
      tabs.forEach((tab) => {
        if (!tab.id) return;
        chrome.tabs.sendMessage(tab.id, { action: 'elementCaptured', payload: message.payload })
          .then(() => console.log('[Agent] broadcast sent to tab', tab.id, tab.url))
          .catch((err) => console.warn('[Agent] broadcast failed for tab', tab.id, err.message));
      });
    });
    sendResponse({ broadcast: true });
    return false;
  }

  return false;
});
