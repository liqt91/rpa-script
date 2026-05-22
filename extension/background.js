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

  async _handleExecuteStep(step) {
    const { stepId } = step;

    try {
      // Get active tab
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id) {
        throw new Error('No active tab');
      }

      // Send to content script and await response
      const result = await chrome.tabs.sendMessage(tab.id, {
        action: 'executeStep',
        step,
      });

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
