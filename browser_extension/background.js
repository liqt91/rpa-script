// Background service worker
// 1. 元素截图捕获
// 2. API 请求代理(绕过 HTTPS 页面的 Mixed Content 限制)
// 3. Dispatcher 动态注入（影刀式 stub + 热更新架构）
// 4. 页面生命周期追踪
// 5. WebSocket 客户端（连接桌面应用服务端）

const LOG_PREFIX = '[操作编排器 BG]';

// ==================== WebSocket 客户端 ====================
const WS_CONFIG = {
    // WebSocket URL 探测列表（按优先级）
    // 1. 与 FastAPI 同端口（桌面应用默认启动方式）
    // 2. 独立端口（备用）
    urls: [
        'ws://127.0.0.1:8000/api/extension/ws',
        'ws://127.0.0.1:8001/api/extension/ws',
        'ws://127.0.0.1:8002/api/extension/ws',
    ],
    fallbackPorts: { start: 8765, end: 8775 },
    path: '/api/extension/ws',
    reconnectInterval: 3000,
    maxReconnectInterval: 30000,
    heartbeatInterval: 15000,
};

let ws = null;
let wsReconnectTimer = null;
let wsReconnectDelay = WS_CONFIG.reconnectInterval;
let wsHeartbeatTimer = null;
let wsConnected = false;

async function discoverWsUrl() {
    // 1. 优先使用 storage 中缓存的 URL
    const stored = await chrome.storage.local.get('wsUrl');
    if (stored.wsUrl && await testWsUrl(stored.wsUrl)) {
        return stored.wsUrl;
    }

    // 2. 尝试预设 URL 列表（FastAPI 默认端口）
    for (const url of WS_CONFIG.urls) {
        if (await testWsUrl(url)) {
            await chrome.storage.local.set({ wsUrl: url });
            return url;
        }
    }

    // 3. 备用端口探测
    for (let port = WS_CONFIG.fallbackPorts.start; port <= WS_CONFIG.fallbackPorts.end; port++) {
        const url = `ws://127.0.0.1:${port}${WS_CONFIG.path}`;
        if (await testWsUrl(url)) {
            await chrome.storage.local.set({ wsUrl: url });
            return url;
        }
    }
    return null;
}

function testWsUrl(url) {
    return new Promise((resolve) => {
        const testWs = new WebSocket(url);
        const timeout = setTimeout(() => {
            testWs.close();
            resolve(false);
        }, 800);
        testWs.onopen = () => {
            clearTimeout(timeout);
            testWs.close();
            resolve(true);
        };
        testWs.onerror = () => {
            clearTimeout(timeout);
            resolve(false);
        };
    });
}

async function connectWebSocket() {
    if (wsConnected || ws?.readyState === WebSocket.CONNECTING) return;

    const url = await discoverWsUrl();
    if (!url) {
        console.log(LOG_PREFIX, '未找到 WebSocket 服务端，将在', wsReconnectDelay, 'ms 后重试');
        scheduleReconnect();
        return;
    }

    try {
        ws = new WebSocket(url);

        ws.onopen = () => {
            console.log(LOG_PREFIX, 'WebSocket 已连接:', url);
            wsConnected = true;
            wsReconnectDelay = WS_CONFIG.reconnectInterval;
            startHeartbeat();
            // 注册扩展信息（浏览器类型）
            const browserName = navigator.userAgent.includes('Edg/') ? 'edge' : 'chrome';
            sendWsMessage('register', { browser: browserName, version: '1.0' });
            // 上报当前标签页信息
            reportTabInfo();
        };

        ws.onmessage = async (evt) => {
            try {
                const { action, payload } = JSON.parse(evt.data);
                await handleServerCommand(action, payload);
            } catch (e) {
                console.error(LOG_PREFIX, '处理服务器消息失败:', e);
            }
        };

        ws.onclose = () => {
            console.log(LOG_PREFIX, 'WebSocket 已断开');
            wsConnected = false;
            stopHeartbeat();
            scheduleReconnect();
        };

        ws.onerror = (err) => {
            console.error(LOG_PREFIX, 'WebSocket 错误:', err);
            wsConnected = false;
        };
    } catch (e) {
        console.error(LOG_PREFIX, 'WebSocket 连接失败:', e);
        scheduleReconnect();
    }
}

function scheduleReconnect() {
    if (wsReconnectTimer) return;
    wsReconnectTimer = setTimeout(() => {
        wsReconnectTimer = null;
        wsReconnectDelay = Math.min(wsReconnectDelay * 1.5, WS_CONFIG.maxReconnectInterval);
        connectWebSocket();
    }, wsReconnectDelay);
}

function startHeartbeat() {
    stopHeartbeat();
    wsHeartbeatTimer = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: 'ping', payload: {} }));
        }
    }, WS_CONFIG.heartbeatInterval);
}

function stopHeartbeat() {
    if (wsHeartbeatTimer) {
        clearInterval(wsHeartbeatTimer);
        wsHeartbeatTimer = null;
    }
}

async function reportTabInfo() {
    try {
        const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tabs[0]) {
            sendWsMessage('tabInfo', {
                tabId: tabs[0].id,
                url: tabs[0].url,
                title: tabs[0].title,
            });
        }
    } catch (e) {
        console.debug(LOG_PREFIX, '上报标签页信息失败:', e);
    }
}

function sendWsMessage(action, payload) {
    if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action, payload }));
        return true;
    }
    return false;
}

// ==================== Native Messaging Host ====================
const NATIVE_HOST_NAME = 'xhs.platform';

function sendNativeMessage(action, payload) {
    return new Promise((resolve) => {
        chrome.runtime.sendNativeMessage(
            NATIVE_HOST_NAME,
            { action, payload },
            (response) => {
                if (chrome.runtime.lastError) {
                    console.warn(LOG_PREFIX, 'Native Host 错误:', chrome.runtime.lastError.message);
                    resolve({ success: false, error: chrome.runtime.lastError.message });
                } else {
                    resolve(response || { success: false, error: 'no response' });
                }
            }
        );
    });
}

async function activateWindowViaNativeHost(tabId) {
    try {
        const tab = await chrome.tabs.get(tabId);
        if (!tab?.windowId) return false;
        const processName = navigator.userAgent.includes('Edg/') ? 'msedge.exe' : 'chrome.exe';
        const res = await sendNativeMessage('activateWindow', {
            processName: processName,
            titleContains: tab.title?.slice(0, 30),
        });
        console.log(LOG_PREFIX, 'Native Host 激活结果:', res);
        return res.success;
    } catch (e) {
        console.warn(LOG_PREFIX, 'Native Host 激活失败:', e);
        return false;
    }
}

// ==================== 服务器命令处理 ====================

async function handleServerCommand(action, payload) {
    console.log(LOG_PREFIX, '收到服务器命令:', action, payload);

    switch (action) {
        case 'enterCaptureMode': {
            const tabId = payload.tabId;
            const targetTabId = tabId || (await getActiveTabId());
            if (!targetTabId) {
                sendWsMessage('commandError', { action, error: 'no active tab' });
                return;
            }
            // 将浏览器窗口提到前台
            let activated = false;
            try {
                activated = await activateWindowViaNativeHost(targetTabId);
            } catch (e) {
                console.warn(LOG_PREFIX, 'Native Host 激活异常:', e);
            }
            if (!activated) {
                console.log(LOG_PREFIX, 'Native Host 未成功，回退到 chrome.windows.update');
                try {
                    const tab = await chrome.tabs.get(targetTabId);
                    if (tab?.windowId) {
                        const win = await chrome.windows.get(tab.windowId);
                        if (win.state === 'minimized') {
                            await chrome.windows.update(tab.windowId, { state: 'normal', focused: true });
                        } else {
                            await chrome.windows.update(tab.windowId, { focused: true, drawAttention: true });
                        }
                        await chrome.tabs.update(targetTabId, { active: true, highlighted: true });
                    }
                } catch (e) {
                    console.warn(LOG_PREFIX, 'chrome.windows.update 激活失败:', e);
                }
            }
            const res = await sendToContent(targetTabId, 'enterCaptureMode', {});
            sendWsMessage('commandResult', { action, result: res });
            break;
        }

        case 'exitCaptureMode': {
            const targetTabId = payload.tabId || (await getActiveTabId());
            if (targetTabId) {
                const res = await sendToContent(targetTabId, 'exitCaptureMode', {});
                sendWsMessage('commandResult', { action, result: res });
            }
            break;
        }

        case 'showPanel': {
            const tabId = payload.tabId || (await getActiveTabId());
            if (!tabId) return;
            const res = await sendToContent(tabId, 'show', {
                backendUrl: payload.backendUrl,
                workflowId: payload.workflowId,
            });
            sendWsMessage('commandResult', { action, result: res });
            break;
        }

        case 'hidePanel': {
            const tabId = payload.tabId || (await getActiveTabId());
            if (!tabId) return;
            const res = await sendToContent(tabId, 'hide', {});
            sendWsMessage('commandResult', { action, result: res });
            break;
        }

        case 'getStatus': {
            const tabId = payload.tabId || (await getActiveTabId());
            if (!tabId) return;
            const res = await sendToContent(tabId, 'getStatus', {});
            sendWsMessage('commandResult', { action, result: res });
            break;
        }

        case 'runWorkflow': {
            const tabId = payload.tabId || (await getActiveTabId());
            if (!tabId) return;
            const res = await sendToContent(tabId, 'runWorkflow', {});
            sendWsMessage('commandResult', { action, result: res });
            break;
        }

        case 'startNativeCapture': {
            const tabId = payload.tabId || (await getActiveTabId());
            const res = await sendNativeMessage('startCapture', {
                backendUrl: payload.backendUrl || 'http://localhost:8000'
            });
            sendWsMessage('commandResult', { action, result: res });
            break;
        }

        case 'exitNativeCapture': {
            const res = await sendNativeMessage('exitCapture', {});
            sendWsMessage('commandResult', { action, result: res });
            break;
        }

        case 'pong':
            // 心跳响应，无需处理
            break;

        default:
            console.warn(LOG_PREFIX, '未知服务器命令:', action);
    }
}

async function getActiveTabId() {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs[0]?.id || null;
}

async function sendToContent(tabId, action, data) {
    const payload = { action, ...data };
    for (let i = 0; i < 3; i++) {
        try {
            const res = await chrome.tabs.sendMessage(tabId, payload);
            if (res && res.status === 'needInit') {
                // 注入 dispatcher
                await chrome.scripting.executeScript({
                    target: { tabId },
                    files: ['content_dispatcher.js'],
                });
                await new Promise(r => setTimeout(r, 400));
                continue;
            }
            return res;
        } catch (e) {
            if (i === 0) {
                // 首次失败：尝试注入 stub + dispatcher
                try {
                    await chrome.scripting.executeScript({
                        target: { tabId },
                        files: ['content_stub.js', 'content_dispatcher.js'],
                    });
                    await new Promise(r => setTimeout(r, 300));
                } catch (injectErr) {
                    console.error('注入失败:', injectErr);
                }
            } else {
                await new Promise(r => setTimeout(r, 200));
            }
        }
    }
    return null;
}

// ==================== chrome.runtime.onMessage ====================

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    // === 截图捕获 ===
    if (request.action === 'captureElement') {
        if (!sender.tab || !sender.tab.id) {
            sendResponse({ success: false, error: 'missing tab' });
            return false;
        }
        chrome.tabs.captureVisibleTab(undefined, { format: 'png' })
            .then(dataUrl => sendResponse({ success: true, dataUrl }))
            .catch(err => sendResponse({ success: false, error: err.message }));
        return true;
    }

    // === API 代理 ===
    if (request.action === 'apiProxy') {
        const { url, method, headers, body } = request;
        fetch(url, {
            method: method || 'GET',
            headers: headers || {},
            body: body || undefined,
        })
            .then(async res => {
                const data = await res.json().catch(() => null);
                sendResponse({
                    success: res.ok,
                    status: res.status,
                    data: data,
                });
            })
            .catch(err => {
                sendResponse({ success: false, error: err.message });
            });
        return true;
    }

    // === 截图结果上报（content script 调用）===
    if (request.action === 'reportCapture') {
        const sent = sendWsMessage('captureResult', {
            tabId: sender.tab?.id,
            ...request.data,
        });
        sendResponse({ success: sent });
        return true;
    }

    // === Dispatcher 注入（从本地文件） ===
    if (request.action === 'ensureDispatcher') {
        const tabId = sender.tab?.id;
        if (!tabId) {
            sendResponse({ success: false, error: 'missing tab' });
            return false;
        }
        chrome.scripting.executeScript({
            target: { tabId: tabId },
            files: ['content_dispatcher.js'],
        })
            .then(() => {
                console.log(LOG_PREFIX, 'Dispatcher 注入成功, tab:', tabId);
                sendResponse({ success: true });
            })
            .catch(err => {
                console.error(LOG_PREFIX, 'Dispatcher 注入失败:', err.message);
                sendResponse({ success: false, error: err.message });
            });
        return true;
    }

    // === Dispatcher 热更新（从服务器拉取的代码字符串） ===
    if (request.action === 'updateDispatcher') {
        const tabId = request.tabId || sender.tab?.id;
        const code = request.code;
        if (!tabId) {
            sendResponse({ success: false, error: 'missing tabId' });
            return false;
        }
        if (!code || typeof code !== 'string') {
            sendResponse({ success: false, error: 'missing code' });
            return false;
        }
        function injectCode(codeStr) {
            try {
                eval(codeStr);
            } catch (e) {
                console.error('[操作编排器] 热更新代码执行失败:', e);
            }
        }
        chrome.scripting.executeScript({
            target: { tabId: tabId },
            func: injectCode,
            args: [code],
        })
            .then(() => {
                console.log(LOG_PREFIX, 'Dispatcher 热更新成功, tab:', tabId);
                sendResponse({ success: true });
            })
            .catch(err => {
                console.error(LOG_PREFIX, 'Dispatcher 热更新失败:', err.message);
                sendResponse({ success: false, error: err.message });
            });
        return true;
    }

    // === 向所有标签页广播消息 ===
    if (request.action === 'broadcast') {
        chrome.tabs.query({})
            .then(tabs => {
                const sends = tabs.map(tab =>
                    chrome.tabs.sendMessage(tab.id, request.payload).catch(() => null)
                );
                return Promise.all(sends);
            })
            .then(() => sendResponse({ success: true }))
            .catch(err => sendResponse({ success: false, error: err.message }));
        return true;
    }

    return false;
});

// ==================== 页面生命周期追踪 ====================

chrome.webNavigation?.onCompleted?.addListener((details) => {
    if (details.frameId !== 0) return;
    console.log(LOG_PREFIX, '页面加载完成, tab:', details.tabId, 'url:', details.url);
    // 新页面加载后，可以自动尝试连接 WebSocket
    if (!wsConnected) connectWebSocket();
});

chrome.tabs?.onActivated?.addListener(() => {
    if (wsConnected) reportTabInfo();
});

// ==================== Service Worker 保活（MV3） ====================

chrome.alarms?.onAlarm?.addListener((alarm) => {
    if (alarm.name === 'keepAlive') {
        console.debug(LOG_PREFIX, 'keepAlive alarm');
        if (!wsConnected) connectWebSocket();
    }
});

if (chrome.alarms) {
    chrome.alarms.create('keepAlive', { periodInMinutes: 4.5 });
}

// ==================== 启动 ====================
console.log(LOG_PREFIX, 'Service Worker 已启动');
connectWebSocket();
