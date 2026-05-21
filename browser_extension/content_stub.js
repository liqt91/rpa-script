(function() {
    'use strict';

    const DISPATCHER_VERSION = '1.0';
    const LOG_PREFIX = '[操作编排器]';

    // 防止重复注入 stub
    if (window.__orch_stub) {
        console.log(LOG_PREFIX, 'Stub 已存在，跳过');
        return;
    }

    // ==================== Stub 状态 ====================
    window.__orch_stub = {
        version: DISPATCHER_VERSION,
        ready: false,
        messageQueue: [],
    };

    // ==================== 工具函数 ====================
    function isDispatcherReady() {
        return window.__orch_dispatcher
            && window.__orch_dispatcher.version === DISPATCHER_VERSION
            && typeof window.__orch_dispatcher.handleMessage === 'function';
    }

    function ensureDispatcher() {
        if (isDispatcherReady()) return;
        console.log(LOG_PREFIX, '请求 background 注入 dispatcher，版本:', DISPATCHER_VERSION);
        chrome.runtime.sendMessage({
            action: 'ensureDispatcher',
            version: DISPATCHER_VERSION,
        }).catch(err => {
            // 扩展可能尚未就绪，静默忽略
            console.debug(LOG_PREFIX, 'ensureDispatcher sendMessage failed:', err.message);
        });
    }

    // ==================== 消息路由 ====================
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        // Ping：健康检查，无论 dispatcher 是否就绪都响应
        if (request.action === 'ping') {
            sendResponse({
                success: true,
                status: isDispatcherReady() ? 'ready' : 'needInit',
                stubVersion: DISPATCHER_VERSION,
                dispatcherVersion: window.__orch_dispatcher?.version || null,
            });
            return true;
        }

        // 如果 dispatcher 已就绪，直接委托
        if (isDispatcherReady()) {
            try {
                const keepOpen = window.__orch_dispatcher.handleMessage(request, sender, sendResponse);
                return keepOpen === true;
            } catch (err) {
                console.error(LOG_PREFIX, 'Dispatcher handleMessage 出错:', err);
                sendResponse({ success: false, error: err.message });
                return true;
            }
        }

        // Dispatcher 未就绪 —— 排队消息并请求注入
        console.log(LOG_PREFIX, 'Dispatcher 未就绪，消息入队:', request.action);
        window.__orch_stub.messageQueue.push({ request, sender, sendResponse });
        ensureDispatcher();

        // 返回一个”需要初始化”的响应，避免调用方无限等待
        // 调用方可选择重试或在收到 dispatcher 就绪通知后重发
        sendResponse({
            success: false,
            status: 'needInit',
            message: 'Dispatcher not ready, queued',
            version: DISPATCHER_VERSION,
        });
        return true;
    });

    // ==================== 页面可见性变化时重新检查 ====================
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && !isDispatcherReady()) {
            ensureDispatcher();
        }
    });

    // ==================== 初始化：请求注入 dispatcher ====================
    console.log(LOG_PREFIX, 'Stub 已加载，等待 dispatcher...');
    ensureDispatcher();
})();
