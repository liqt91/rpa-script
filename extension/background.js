/**
 * RPA Script Browser Agent — Background Service Worker
 *
 * Architecture:
 *   Backend (FastAPI WS)  <--WebSocket-->  background.js  <--chrome.tabs.sendMessage-->  content.js  <--DOM-->  Page
 *   Side Panel  <--chrome.runtime.onMessage-->  background.js  <--chrome.tabs.sendMessage-->  content_capture.js
 */

const DEFAULT_BACKEND_HOST = 'localhost';
const DEFAULT_BACKEND_PORT = 8000;

function buildWsUrl(host, port) {
  return `ws://${host}:${port}/api/extension/ws`;
}

async function getBackendUrl() {
  const cfg = await chrome.storage.local.get(['backendHost', 'backendPort']);
  const host = cfg.backendHost || DEFAULT_BACKEND_HOST;
  const port = parseInt(cfg.backendPort || DEFAULT_BACKEND_PORT, 10);
  return buildWsUrl(host, port);
}

async function getBackendHost() {
  const cfg = await chrome.storage.local.get(['backendHost']);
  return cfg.backendHost || DEFAULT_BACKEND_HOST;
}

async function getBackendPort() {
  const cfg = await chrome.storage.local.get(['backendPort']);
  return parseInt(cfg.backendPort || DEFAULT_BACKEND_PORT, 10);
}

class AgentBackground {
  constructor() {
    this.ws = null;
    this.reconnectTimer = null;
    this.pingTimer = null;
    this.clientId = null;
    this.pendingSteps = new Map(); // stepId -> {resolve, reject, timer}
    this.workTabId = null;         // 工作流专用标签页 ID
    this.workWindowId = null;      // 工作流专用窗口 ID
    this.lastCapturePayload = null; // 最近一次捕获的元素数据（供 side panel 获取）
    this.lastCaptureTabId = null;   // 捕获来源标签页
    this.isRunning = false;         // 工作流运行中标志
    this.sidePanelOpen = false;     // side panel 是否打开
  }

  async start() {
    const wsUrl = await getBackendUrl();
    this._connect(wsUrl);

    // 点击扩展图标自动打开原生 Side Panel
    try {
      await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
    } catch (e) {
      console.warn('[Agent] sidePanel behavior not supported:', e.message);
    }

    // MV3 Service Worker keep-alive: 周期性闹钟防止浏览器暂停 Service Worker
    try {
      await chrome.alarms.create('keepAlive', { periodInMinutes: 0.5 });
    } catch (e) {
      console.warn('[Agent] alarms not supported:', e.message);
    }
  }

  _connect(wsUrl) {
    // 如果已有连接且目标 URL 相同，跳过
    if (this.ws?.url === wsUrl && (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING)) {
      return;
    }

    // 如果已有连接但目标不同，强制关闭旧连接（切换后端端口）
    if (this.ws) {
      console.log('[Agent] Switching backend from', this.ws.url, 'to', wsUrl);
      try { this.ws.close(); } catch (e) {}
      this.ws = null;
    }

    // 清除旧的重连定时器，防止多个定时器同时触发
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

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
      this.reconnectTimer = setTimeout(async () => {
        const url = await getBackendUrl();
        this._connect(url);
      }, 3000);
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
   *   - executeStep: { stepId, type, locator, selectorFamily, action, extra }
   */
  async _onBackendMessage(msg) {
    const { action, payload } = msg;

    if (action === 'pong') return;

    if (action === 'executeStep') {
      await this._handleExecuteStep(payload);
      return;
    }

    if (action === 'runStarted') {
      this.isRunning = true;
      // Reset work window/tab references so navigate opens a fresh tab/window.
      // Do NOT close the actual browser window — if it's the only window,
      // removing it kills the browser process and breaks the extension connection.
      this.workWindowId = null;
      this.workTabId = null;
      console.log('[Agent] work window/tab reset for new run');
      return;
    }

    console.log('[Agent] Unknown backend action:', action);
  }

  _isRestrictedUrl(url) {
    if (!url) return true;
    // newtab / blank are safe automation targets (browser default start pages)
    if (url === 'about:blank' || url.includes('newtab')) return false;
    const restricted = ['chrome://', 'edge://', 'chrome-extension://', 'about:', 'file://', 'data:', 'javascript:'];
    return restricted.some(p => url.startsWith(p));
  }

  async _ensureWorkTab(step) {
    const type = step.type;
    const url = step.extra?.url;

    // ── navigate: create a dedicated background window ──
    if (type === 'navigate') {
      if (!url) throw new Error('navigate: url required');

      // 1) Reuse existing work window if still valid
      if (this.workWindowId) {
        try {
          const win = await chrome.windows.get(this.workWindowId);
          if (win) {
            // 优先使用流程创建的 workTabId，而不是当前 active tab（用户可能新建了其他标签页）
            if (this.workTabId) {
              try {
                const tab = await chrome.tabs.get(this.workTabId);
                if (tab && !this._isRestrictedUrl(tab.url)) {
                  await chrome.tabs.update(this.workTabId, { url, active: true });
                  return this.workTabId;
                }
              } catch (e) {}
            }
            // workTabId 无效了，回退到 active tab
            const [tab] = await chrome.tabs.query({ windowId: this.workWindowId, active: true });
            if (tab?.id && !this._isRestrictedUrl(tab.url)) {
              await chrome.tabs.update(tab.id, { url });
              this.workTabId = tab.id;
              return tab.id;
            }
          }
        } catch (e) {}
      }

      // 2) No work window — reuse an existing browser window instead of creating a second one.
      // Prefer blank/newtab (likely the one just launched by launch_browser),
      // but fall back to any usable tab in a normal window.
      const windows = await chrome.windows.getAll({ populate: true });
      let fallbackTab = null;
      let fallbackWindowId = null;
      for (const win of windows) {
        if (win.type !== 'normal' || !win.tabs) continue;
        const blankTabs = win.tabs.filter(t =>
          !this._isRestrictedUrl(t.url) &&
          (t.url === 'about:blank' || t.url?.includes('newtab') || t.url === 'edge://newtab/')
        );
        if (blankTabs.length > 0) {
          this.workWindowId = win.id;
          const tab = blankTabs[0];
          await chrome.tabs.update(tab.id, { url, active: true });
          this.workTabId = tab.id;
          await new Promise(r => setTimeout(r, 500));
          try { await this._injectContentScript(tab.id); } catch (e) {}
          return tab.id;
        }
        // Record first usable tab as fallback
        if (!fallbackTab) {
          const usable = win.tabs.find(t => !this._isRestrictedUrl(t.url));
          if (usable) {
            fallbackTab = usable;
            fallbackWindowId = win.id;
          }
        }
      }
      if (fallbackTab) {
        this.workWindowId = fallbackWindowId;
        await chrome.tabs.update(fallbackTab.id, { url, active: true });
        this.workTabId = fallbackTab.id;
        await new Promise(r => setTimeout(r, 500));
        try { await this._injectContentScript(fallbackTab.id); } catch (e) {}
        return fallbackTab.id;
      }

      // 3) Last resort: create new unfocused window
      const newWindow = await chrome.windows.create({ url, focused: false });
      this.workWindowId = newWindow.id;
      const newTab = newWindow.tabs?.[0];
      if (newTab?.id) {
        this.workTabId = newTab.id;
        await new Promise(r => setTimeout(r, 500));
        try { await this._injectContentScript(newTab.id); } catch (e) {}
        return newTab.id;
      }

      throw new Error('Failed to create automation window');
    }

    // ── Non-navigate: workTab 必须有效，不回退到任意标签页 ──
    // 用户手动关闭工作标签页后，继续执行会导致脚本偏移到其他页面，必须停止
    if (this.workWindowId) {
      try {
        const win = await chrome.windows.get(this.workWindowId);
        if (!win) {
          throw new Error('工作窗口已被关闭，请在 navigate 步骤重新创建');
        }
        // workTabId 必须仍然有效
        if (this.workTabId) {
          try {
            const tab = await chrome.tabs.get(this.workTabId);
            if (tab && !this._isRestrictedUrl(tab.url)) {
              return this.workTabId;
            }
          } catch (e) {
            throw new Error('工作标签页已被手动关闭，请在 navigate 步骤重新创建');
          }
        }
        throw new Error('工作标签页已失效，请在 navigate 步骤重新创建');
      } catch (e) {
        if (e.message.includes('工作')) throw e;
        throw new Error('工作窗口已失效，请在 navigate 步骤重新创建');
      }
    }

    throw new Error('未找到工作窗口，请先执行 navigate 步骤');
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

      // 向页面注入运行提示
      if (tabId) {
        chrome.tabs.sendMessage(tabId, { action: 'setRunningBanner', visible: true, stepType: type })
          .catch(() => {});
      }

      // navigate is fully handled in _ensureWorkTab (URL already updated)
      if (type === 'navigate') {
        this.workTabId = tabId;
        await new Promise(r => setTimeout(r, 500));
        this._send('stepResult', { stepId, result: { navigatedTo: step.extra?.url } });
        return;
      }

      // Try sending directly; if content script is missing, inject and retry once
      let result;
      try {
        result = await this._executeStepOnTab(tabId, step);
      } catch (sendErr) {
        const msg = sendErr?.message || '';
        const isMissing = msg.includes('Receiving end does not exist') || msg.includes('Could not establish connection');
        const isClosed = msg.includes('message channel') || msg.includes('back/forward cache');
        if (isMissing || isClosed) {
          console.log('[Agent] content script missing/closed (bfcache?), re-injecting...');
          await this._injectContentScript(tabId);
          await new Promise(r => setTimeout(r, 1500));
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

// ── Handle messages from content scripts and side panel ──

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // 0) 选项页面请求立即重连
  if (message.action === 'reconnect') {
    (async () => {
      try {
        const host = message.host || DEFAULT_BACKEND_HOST;
        const port = message.port || DEFAULT_BACKEND_PORT;
        await chrome.storage.local.set({ backendHost: host, backendPort: String(port) });
        const wsUrl = buildWsUrl(host, port);
        agent._connect(wsUrl);
        await new Promise(r => setTimeout(r, 1000));
        sendResponse({ connected: agent.ws?.readyState === WebSocket.OPEN });
      } catch (e) {
        sendResponse({ connected: false, error: e.message });
      }
    })();
    return true;
  }

  // 1) Side panel 请求最近一次捕获的数据
  if (message.action === 'getCapturePayload') {
    sendResponse({
      payload: agent.lastCapturePayload,
      tabId: agent.lastCaptureTabId,
    });
    return false;
  }

  // 2) Side panel 请求校验元素 → 转发给对应标签页的 content_capture.js
  if (message.action === 'verifyElement') {
    // sidepanel.js 的 send() 把参数包在 payload 里: { action, payload: { tabId, payload } }
    const tabId = message.tabId ?? message.payload?.tabId;
    const payload = message.payload?.payload ?? message.payload;
    if (!tabId) {
      sendResponse({ error: 'tabId required' });
      return false;
    }
    chrome.tabs.sendMessage(tabId, { action: 'verifyElement', payload })
      .then(result => sendResponse(result))
      .catch(err => sendResponse({ error: err.message }));
    return true; // async
  }

  // 3) Content script 返回校验结果 → 广播给 side panel
  if (message.action === 'verifyResult') {
    // Broadcast to side panel (and anyone listening)
    chrome.runtime.sendMessage({ action: 'verifyResultBroadcast', payload: message.payload })
      .catch(() => {});
    sendResponse({ forwarded: true });
    return false;
  }

  // 4) Content script 通知捕获完成 → 缓存数据并打开 side panel（不保存到后台）
  if (message.action === 'captureElement') {
    agent.lastCapturePayload = message.payload;
    agent.lastCaptureTabId = sender.tab?.id || null;

    // Notify side panel to refresh (in case it's already open)
    chrome.runtime.sendMessage({ action: 'newCaptureAvailable' }).catch(() => {});

    // Open side panel on the capturing tab
    if (sender.tab?.id) {
      try {
        chrome.sidePanel.open({ tabId: sender.tab.id }).catch(() => {});
      } catch (_e) {}
    }
    sendResponse({ cached: true });
    return false;
  }

  // 5) Side panel 点击保存 → 转发到后端
  if (message.action === 'saveElement') {
    agent._send('captureElement', message.payload);
    sendResponse({ saved: true });
    return false;
  }

  // 5a) Side panel 请求流程列表
  if (message.action === 'getWorkflows') {
    (async () => {
      try {
        const host = await getBackendHost();
        const port = await getBackendPort();
        const resp = await fetch(`http://${host}:${port}/api/extension/workflows`);
        const data = await resp.json();
        sendResponse({ workflows: data });
      } catch (e) {
        sendResponse({ error: e.message });
      }
    })();
    return true;
  }

  // 5b) Side panel 请求流程元素列表
  if (message.action === 'getWorkflowElements') {
    (async () => {
      try {
        const host = await getBackendHost();
        const port = await getBackendPort();
        const wfId = message.workflowId;
        const resp = await fetch(`http://${host}:${port}/api/extension/elements?workflow_id=${wfId}`);
        const data = await resp.json();
        sendResponse({ elements: data });
      } catch (e) {
        sendResponse({ error: e.message });
      }
    })();
    return true;
  }

  // 6) Content script 查询当前捕获启用状态（页面刷新后同步）
  if (message.action === 'queryCaptureState') {
    sendResponse({ captureEnabled: agent.sidePanelOpen });
    return false;
  }

  if (message.action === 'captureScreenshot') {
    chrome.tabs.captureVisibleTab({ format: 'png' })
      .then(dataUrl => sendResponse({ dataUrl }))
      .catch(err => sendResponse({ error: err.message }));
    return true;
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
    return true;
  }

  if (message.action === 'notifyElementCaptured') {
    chrome.tabs.query({}, (tabs) => {
      tabs.forEach((tab) => {
        if (!tab.id) return;
        chrome.tabs.sendMessage(tab.id, { action: 'elementCaptured', payload: message.payload })
          .catch(() => {});
      });
    });
    sendResponse({ broadcast: true });
    return false;
  }

  return false;
});

// ── Side Panel 长连接生命周期（比 beforeunload 可靠）──
chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== 'sidePanel') return;

  // side panel 打开
  agent.sidePanelOpen = true;
  const enabled = true;
  chrome.tabs.query({}, (tabs) => {
    tabs.forEach((tab) => {
      if (!tab.id) return;
      chrome.tabs.sendMessage(tab.id, { action: 'setCaptureEnabled', enabled })
        .catch(() => {});
    });
  });

  port.onDisconnect.addListener(() => {
    // side panel 关闭
    agent.sidePanelOpen = false;
    const enabled = false;
    chrome.tabs.query({}, (tabs) => {
      tabs.forEach((tab) => {
        if (!tab.id) return;
        chrome.tabs.sendMessage(tab.id, { action: 'setCaptureEnabled', enabled })
          .catch(() => {});
      });
    });
  });
});

// MV3 keep-alive: 闹钟触发时检查并重连 WS，防止 Service Worker 被浏览器暂停后断连
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'keepAlive') {
    console.log('[Agent] keepAlive alarm');
    if (!agent.ws || agent.ws.readyState !== WebSocket.OPEN) {
      console.log('[Agent] reconnecting from keepAlive alarm');
      const wsUrl = await getBackendUrl();
      agent._connect(wsUrl);
    } else {
      // WS 正常，发送 ping 保持连接活跃
      agent._send('ping');
    }
  }
});
