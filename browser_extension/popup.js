document.addEventListener('DOMContentLoaded', () => {
    const btnToggle     = document.getElementById('btn-toggle');
    const btnExportJson = document.getElementById('btn-export-json');
    const btnExportNL   = document.getElementById('btn-export-nl');
    const btnClearSteps = document.getElementById('btn-clear-steps');
    const btnClearAll   = document.getElementById('btn-clear-all');
    const btnRefreshWf  = document.getElementById('btn-refresh-wf');
    const btnLogin      = document.getElementById('btn-login');
    const btnLogout     = document.getElementById('btn-logout');
    const authUsername  = document.getElementById('auth-username');
    const authPassword  = document.getElementById('auth-password');
    const authLoggedOut = document.getElementById('auth-logged-out');
    const authLoggedIn  = document.getElementById('auth-logged-in');
    const authUsernameDisplay = document.getElementById('auth-username-display');
    const statusText    = document.getElementById('status-text');
    const statusDot     = document.getElementById('status-dot');
    const stepCount     = document.getElementById('step-count');
    const libCount      = document.getElementById('lib-count');
    const backendUrl    = document.getElementById('backend-url');
    const workflowSelect = document.getElementById('workflow-select');

    let currentTabId = null;
    let isVisible = false;
    let authToken = null;
    let authUsernameVal = '';

    const STORAGE_BACKEND = 'orch_backend_url';
    const STORAGE_WORKFLOW = 'orch_selected_workflow';
    const STORAGE_TOKEN = 'orch_auth_token';
    const STORAGE_USERNAME = 'orch_auth_username';

    async function loadSettings() {
        const res = await chrome.storage.local.get([STORAGE_BACKEND, STORAGE_WORKFLOW, STORAGE_TOKEN, STORAGE_USERNAME]);
        if (res[STORAGE_BACKEND]) backendUrl.value = res[STORAGE_BACKEND];
        if (res[STORAGE_WORKFLOW]) workflowSelect.value = res[STORAGE_WORKFLOW];
        if (res[STORAGE_TOKEN]) {
            authToken = res[STORAGE_TOKEN];
            authUsernameVal = res[STORAGE_USERNAME] || '';
            updateAuthUI();
        }
    }

    async function saveSettings() {
        await chrome.storage.local.set({
            [STORAGE_BACKEND]: backendUrl.value.trim(),
            [STORAGE_WORKFLOW]: workflowSelect.value,
        });
    }

    function updateAuthUI() {
        if (authToken) {
            authLoggedOut.style.display = 'none';
            authLoggedIn.style.display = '';
            authUsernameDisplay.textContent = authUsernameVal || 'user';
        } else {
            authLoggedOut.style.display = '';
            authLoggedIn.style.display = 'none';
        }
    }

    function getBackendBase() {
        return (backendUrl.value || 'http://localhost:8000').replace(/\/$/, '');
    }

    function authHeaders() {
        const h = { 'Content-Type': 'application/json' };
        if (authToken) h['Authorization'] = `Bearer ${authToken}`;
        return h;
    }

    async function login() {
        const url = getBackendBase();
        const username = authUsername.value.trim();
        const password = authPassword.value;
        try {
            const res = await fetch(`${url}/api/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();
            authToken = data.access_token;
            authUsernameVal = username;
            await chrome.storage.local.set({
                [STORAGE_TOKEN]: authToken,
                [STORAGE_USERNAME]: username,
            });
            updateAuthUI();
            await fetchWorkflows();
            alert('登录成功');
        } catch (e) {
            alert('登录失败: ' + e.message);
        }
    }

    async function logout() {
        authToken = null;
        authUsernameVal = '';
        await chrome.storage.local.remove([STORAGE_TOKEN, STORAGE_USERNAME]);
        updateAuthUI();
    }

    async function fetchWorkflows() {
        const url = getBackendBase();
        try {
            const res = await fetch(`${url}/api/workflows`, { headers: authHeaders() });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const workflows = await res.json();
            const current = workflowSelect.value;
            workflowSelect.innerHTML = '<option value="">-- 选择工作流 --</option>';
            for (const wf of workflows) {
                const opt = document.createElement('option');
                opt.value = wf.id;
                opt.textContent = `${wf.id}: ${wf.name}`;
                workflowSelect.appendChild(opt);
            }
            workflowSelect.value = current;
            await saveSettings();
        } catch (e) {
            alert('拉取工作流列表失败: ' + e.message + '\n请确认后端已启动且地址正确');
        }
    }

    async function getCurrentTab() {
        const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
        return tabs[0];
    }

    async function sendToContent(action, data, retries = 2) {
        if (!currentTabId) return null;
        const payload = { action, ...data };
        let injected = false;

        for (let i = 0; i <= retries; i++) {
            try {
                const res = await chrome.tabs.sendMessage(currentTabId, payload);
                // Dispatcher 未就绪，等待后重试
                if (res && res.status === 'needInit') {
                    if (i < retries) {
                        await new Promise(r => setTimeout(r, 400));
                        continue;
                    }
                }
                return res;
            } catch (e) {
                // 首次失败：尝试注入 stub + dispatcher
                if (!injected) {
                    try {
                        await chrome.scripting.executeScript({
                            target: { tabId: currentTabId },
                            files: ['content_stub.js', 'content_dispatcher.js']
                        });
                        injected = true;
                        await new Promise(r => setTimeout(r, 300));
                        continue;
                    } catch (injectErr) {
                        console.error('注入失败:', injectErr);
                    }
                }
                if (i >= retries) {
                    alert('无法与页面通信，请刷新页面后重试');
                    return null;
                }
                // 短暂等待后重试
                await new Promise(r => setTimeout(r, 200));
            }
        }
        return null;
    }

    async function syncAuthToContent() {
        // 将当前 token/backend/workflow 同步给 content script
        const backend = backendUrl.value.trim() || 'http://localhost:8000';
        const workflowId = workflowSelect.value ? parseInt(workflowSelect.value) : null;
        await sendToContent('setBackend', {
            backendUrl: backend,
            workflowId: workflowId,
            token: authToken,
        });
    }

    async function updateStatus() {
        const tab = await getCurrentTab();
        if (!tab) return;
        currentTabId = tab.id;

        const res = await sendToContent('getStatus');
        if (!res) return;

        isVisible = res.visible;
        stepCount.textContent = res.stepCount || 0;
        libCount.textContent = res.libraryCount || 0;

        if (isVisible) {
            statusText.innerHTML = '<span class="status-dot on"></span>运行中';
            btnToggle.textContent = '⏹ 停止面板';
            btnToggle.classList.remove('btn-success');
            btnToggle.classList.add('btn-secondary');
        } else {
            statusText.innerHTML = '<span class="status-dot off"></span>未启动';
            btnToggle.textContent = '🔴 启动面板';
            btnToggle.classList.remove('btn-secondary');
            btnToggle.classList.add('btn-success');
        }
    }

    btnToggle.addEventListener('click', async () => {
        const workflowId = workflowSelect.value ? parseInt(workflowSelect.value) : null;
        const backend = backendUrl.value.trim() || 'http://localhost:8000';
        await saveSettings();
        await syncAuthToContent();
        const res = await sendToContent('toggle', { workflowId, backendUrl: backend, token: authToken });
        if (res) updateStatus();
        if (res && res.visible) window.close();
    });

    btnExportJson.addEventListener('click', async () => {
        const res = await sendToContent('exportJSON');
        if (res && res.success) updateStatus();
    });

    btnExportNL.addEventListener('click', async () => {
        const res = await sendToContent('exportNL');
        if (res && res.success) updateStatus();
    });

    btnClearSteps.addEventListener('click', async () => {
        if (!confirm('确定清空所有操作步骤？(元素库保留)')) return;
        const res = await sendToContent('clearSteps');
        if (res && res.success) updateStatus();
    });

    btnClearAll.addEventListener('click', async () => {
        if (!confirm('确定清空全部数据（步骤 + 元素库）？此操作不可恢复。')) return;
        const res = await sendToContent('clearAll');
        if (res && res.success) updateStatus();
    });

    btnRefreshWf.addEventListener('click', fetchWorkflows);
    backendUrl.addEventListener('change', saveSettings);
    workflowSelect.addEventListener('change', saveSettings);
    btnLogin.addEventListener('click', login);
    btnLogout.addEventListener('click', logout);

    // 初始化
    loadSettings().then(() => {
        if (authToken) fetchWorkflows();
        updateStatus();
    });
});
