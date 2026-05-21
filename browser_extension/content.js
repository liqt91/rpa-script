(function() {
    'use strict';

    // 防止重复注入
    if (window.__orchestrator_injected) {
        console.log('[操作编排器] 已注入，跳过');
        return;
    }
    window.__orchestrator_injected = true;

    // ==================== 全局状态 ====================
    let mainPanel = null;
    let libraryPanel = null;
    let currentHoverElement = null;
    let currentHoverSelector = '';
    let elementLibrary = [];
    let actionSteps = [];
    let isVisible = false;
    let updateInterval = null;
    let lockedElement = null;
    let backendUrl = 'http://localhost:8000';
    let currentWorkflowId = null;
    let authToken = null;
    let lockedSelector = '';
    // DrissionPage 定位状态
    let currentCandidates = [];
    let selectedLocatorIndex = 0;
    let lockedLocator = '';
    let lockedLocatorType = '';
    let lockedCandidates = [];
    let currentMethod = 'ele';
    let lastMouseMoveTs = 0;
    let lastHoveredEl = null;
    let highlightedMatches = [];
    // Alt 捕获模式状态(v0.2)
    let captureMode = false;          // 当前是否在捕获模式
    let captureSticky = false;        // 松开 Alt 后粘性保持,鼠标离开 lockedElement 才退出
    let dialogOpen = false;           // 录入对话框是否打开
    let altPhysicallyDown = false;    // Alt 物理按下状态
    let lastUsedMethod = 'ele';       // 上次录入用的 method(持久化)
    let lastUsedAction = 'click';     // 上次录入用的 action(持久化)
    let pendingScreenshot = null;     // 截图 dataURL,捕获时异步获取
    // Canvas overlay 高亮层(v0.3)
    let highlightHost = null;
    // Alt+Q 人工切换 stack(v0.4)
    let hoverStack = [];              // 当前坐标 elementsFromPoint stack
    let stackIndex = 0;               // 当前选中的 stack 索引
    let lastHoverX = 0;
    let lastHoverY = 0;
    let highlightShadow = null;
    let highlightCanvas = null;
    let highlightCtx = null;
    let highlightCurrentEl = null;      // 当前 canvas 高亮的目标元素
    let highlightMatchEls = [];         // 当前多匹配高亮的元素列表
    const STORAGE_KEY_LIBRARY  = 'orch_element_library_v1';
    const STORAGE_KEY_STEPS    = 'orch_action_steps_v1';
    const STORAGE_KEY_LASTUSED = 'orch_last_used_v1';
    const STORAGE_KEY_CONFIG   = 'orch_config_v1';

    // ==================== 配置加载 ====================
    async function loadConfig() {
        try {
            const res = await chrome.storage.local.get(STORAGE_KEY_CONFIG);
            if (res[STORAGE_KEY_CONFIG]) {
                const cfg = JSON.parse(res[STORAGE_KEY_CONFIG]);
                if (cfg.backendUrl) backendUrl = cfg.backendUrl;
                if (cfg.authToken) authToken = cfg.authToken;
            }
        } catch (e) {}
    }
    async function saveConfig() {
        try {
            await chrome.storage.local.set({
                [STORAGE_KEY_CONFIG]: JSON.stringify({ backendUrl, authToken })
            });
        } catch (e) {}
    }

    // ==================== 存储（chrome.storage.local） ====================
    function migrateStep(s) {
        if (s.locator && s.method) return s;
        return Object.assign({
            locator: s.selector ? 'css:' + s.selector : '',
            locator_type: 'css',
            method: 'ele',
            candidates: [],
        }, s, {
            locator: s.locator || (s.selector ? 'css:' + s.selector : ''),
            locator_type: s.locator_type || 'css',
            method: s.method || 'ele',
            candidates: s.candidates || [],
        });
    }

    function migrateLibItem(item) {
        if (item.locator && item.method && item.features) return item;
        let hostname = item.hostname || '';
        if (!hostname && item.page_url) {
            try { hostname = new URL(item.page_url).hostname; } catch (e) {}
        }
        return Object.assign({}, item, {
            locator: item.locator || (item.css_selector ? 'css:' + item.css_selector : ''),
            locator_type: item.locator_type || 'css',
            method: item.method || 'ele',
            candidates: item.candidates || [],
            features: item.features || {},
            description: item.description || '',
            hostname,
        });
    }

    async function loadLibrary() {
        // 先尝试从服务端加载当前站点的元素
        try {
            const res = await _fetchViaBackground(
                `${backendUrl}/api/elements?hostname=${encodeURIComponent(window.location.hostname)}`,
                'GET',
                _authHeaders()
            );
            if (res.ok) {
                const data = await res.json();
                elementLibrary = data.map(item => ({
                    ...item,
                    id: item.id,
                    candidates: item.candidates || [],
                    features: item.features || {},
                }));
                return;
            }
        } catch (e) {
            console.log('[loadLibrary] 服务端加载失败,回退本地:', e);
        }
        // 回退到本地 storage
        const res = await chrome.storage.local.get(STORAGE_KEY_LIBRARY);
        if (res[STORAGE_KEY_LIBRARY]) {
            try {
                const arr = JSON.parse(res[STORAGE_KEY_LIBRARY]);
                elementLibrary = Array.isArray(arr) ? arr.map(migrateLibItem) : [];
            } catch (e) {
                elementLibrary = [];
            }
        }
    }

    async function saveLibrary() {
        await chrome.storage.local.set({ [STORAGE_KEY_LIBRARY]: JSON.stringify(elementLibrary) });
    }

    async function loadSteps() {
        const res = await chrome.storage.local.get(STORAGE_KEY_STEPS);
        if (res[STORAGE_KEY_STEPS]) {
            try {
                const arr = JSON.parse(res[STORAGE_KEY_STEPS]);
                actionSteps = Array.isArray(arr) ? arr.map(migrateStep) : [];
            } catch (e) {
                actionSteps = [];
            }
        }
    }

    async function saveSteps() {
        await chrome.storage.local.set({ [STORAGE_KEY_STEPS]: JSON.stringify(actionSteps) });
    }

    // ==================== 后端同步 ====================
    function _authHeaders() {
        const h = { 'Content-Type': 'application/json' };
        if (authToken) h['Authorization'] = `Bearer ${authToken}`;
        return h;
    }

    // 通过 background script 代理请求,绕过 HTTPS 页面的 Mixed Content 限制
    async function _fetchViaBackground(url, method, headers, body) {
        return new Promise((resolve, reject) => {
            chrome.runtime.sendMessage({
                action: 'apiProxy',
                url, method, headers, body,
            }, (response) => {
                if (chrome.runtime.lastError) {
                    reject(new Error(chrome.runtime.lastError.message));
                    return;
                }
                if (!response || !response.success) {
                    reject(new Error(response?.error || '请求失败'));
                    return;
                }
                // 构造一个类 Response 对象
                resolve({
                    ok: response.status >= 200 && response.status < 300,
                    status: response.status,
                    json: async () => response.data,
                });
            });
        });
    }

    async function _fetchWithAuth(url, options, allowAnonymousFallback = false) {
        const headers = _authHeaders();
        if (options?.headers) Object.assign(headers, options.headers);
        let res = await _fetchViaBackground(url, options?.method || 'GET', headers, options?.body);
        // 401 且允许匿名回退 → 换匿名端点重试
        if (res.status === 401 && allowAnonymousFallback) {
            const anonUrl = url + '/anonymous';
            res = await _fetchViaBackground(anonUrl, options?.method || 'GET', { 'Content-Type': 'application/json' }, options?.body);
        }
        return res;
    }

    async function syncStepToBackend(step) {
        if (!currentWorkflowId || !backendUrl) return;
        const url = backendUrl.replace(/\/$/, '') + `/api/workflows/${currentWorkflowId}/nodes`;
        try {
            const payload = {
                type: step.action,
                locator: step.locator || null,
                locator_type: step.locator_type || null,
                method: step.method || 'ele',
                action: step.action,
                extra: step.extra || {},
            };
            const res = await _fetchWithAuth(url, {
                method: 'POST',
                body: JSON.stringify(payload),
            }, /*allowAnonymousFallback=*/ true);
            if (!res.ok) {
                console.warn('[操作编排器] 同步到后端失败:', res.status);
            } else {
                showToast('已同步到后端');
            }
        } catch (e) {
            console.warn('[操作编排器] 同步到后端失败:', e.message);
        }
    }

    async function fetchWorkflowNodes() {
        if (!currentWorkflowId || !backendUrl) return [];
        const url = backendUrl.replace(/\/$/, '') + `/api/workflows/${currentWorkflowId}/nodes`;
        try {
            const res = await _fetchWithAuth(url, { method: 'GET' }, /*allowAnonymousFallback=*/ true);
            if (!res.ok) return [];
            return await res.json();
        } catch (e) {
            console.warn('[操作编排器] 拉取工作流节点失败:', e.message);
            return [];
        }
    }

    // ==================== 截图 ====================
    async function captureElementScreenshot(element) {
        if (!element) return null;
        const rect = element.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;

        // Scroll element into view first
        element.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'center' });
        await new Promise(r => setTimeout(r, 150)); // wait for scroll

        try {
            const res = await chrome.runtime.sendMessage({ action: 'captureElement' });
            if (!res || !res.success) {
                console.warn('[操作编排器] 截图失败:', res?.error);
                return null;
            }

            // Crop the element region (+15px padding) from the full-page screenshot in DOM
            const fullDataUrl = res.dataUrl;
            const raw = element.getBoundingClientRect(); // re-measure after scroll
            const cropRect = {
                x: Math.max(0, raw.x - 15),
                y: Math.max(0, raw.y - 15),
                width: raw.width + 30,
                height: raw.height + 30,
            };

            return await new Promise((resolve) => {
                const img = new Image();
                img.onload = () => {
                    const canvas = document.createElement('canvas');
                    const sw = Math.round(cropRect.width * dpr);
                    const sh = Math.round(cropRect.height * dpr);
                    canvas.width = sw;
                    canvas.height = sh;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(
                        img,
                        Math.round(cropRect.x * dpr),
                        Math.round(cropRect.y * dpr),
                        sw, sh,
                        0, 0, sw, sh
                    );
                    resolve(canvas.toDataURL('image/png'));
                };
                img.onerror = () => {
                    console.warn('[操作编排器] 截图裁剪失败');
                    resolve(null);
                };
                img.src = fullDataUrl;
            });
        } catch (e) {
            console.warn('[操作编排器] 截图请求失败:', e.message);
            return null;
        }
    }

    // ==================== 保存到元素库面板 (Alt+1) ====================
    async function saveElementToLibraryConfirm() {
        console.log('[saveElementToLibraryConfirm] lockedElement:', lockedElement ? _debugLabel(lockedElement) : 'null',
                    '| lockedCandidates:', lockedCandidates ? lockedCandidates.length : 0,
                    '| currentHoverElement:', currentHoverElement ? _debugLabel(currentHoverElement) : 'null',
                    '| highlightCurrentEl:', highlightCurrentEl ? _debugLabel(highlightCurrentEl) : 'null');
        if (!lockedElement) {
            showToast('请先 hover 一个元素');
            return;
        }
        if (dialogOpen) return;
        // 快照 lockedElement,避免对话框打开后 Alt 抬起/退出 captureMode 导致外层变量被清空
        const elRef = lockedElement;
        const cands = lockedCandidates && lockedCandidates.length
            ? lockedCandidates
            : generateLocators(elRef);
        if (!cands.length) {
            showToast('该元素没有可用 locator 候选');
            return;
        }
        const top = cands[0];
        showToast('正在截图...');
        const screenshot = await captureElementScreenshot(elRef);

        dialogOpen = true;
        clearMatchHighlights();

        const overlay = document.createElement('div');
        overlay.id = 'orch-save-lib-dialog';
        overlay.style.cssText = `
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.6); z-index: 2147483647;
            display: flex; align-items: center; justify-content: center;
            font-family: 'Monaco', 'Menlo', 'Consolas', monospace; font-size: 12px;
        `;

        const box = document.createElement('div');
        box.style.cssText = `
            background: #1e1e1e; color: #d4d4d4;
            border: 1px solid #444; border-radius: 8px;
            width: 480px; max-width: 92vw; max-height: 88vh;
            display: flex; flex-direction: column; overflow: hidden;
        `;

        const tag = elRef.tagName.toLowerCase();
        const text = escapeHtml((elRef.innerText || '').slice(0, 60).replace(/\s+/g, ' '));
        const defaultName = `element_${elementLibrary.length + 1}`;
        const imgBlock = screenshot
            ? `<img src="${screenshot}" style="max-width:100%;max-height:140px;border:1px solid #444;border-radius:4px;background:#1a1a1a">`
            : '<span style="color:#888">截图不可用</span>';

        // Build candidate list HTML
        const candsHtml = cands.map((c, idx) => {
            const mc = c.matchCount === 1
                ? '<span style="color:#4caf50">1命中</span>'
                : c.matchCount > 1
                    ? `<span style="color:#ffa500">${c.matchCount}命中</span>`
                    : c.matchCount === -1
                        ? '<span style="color:#888">?</span>'
                        : '<span style="color:#888">0</span>';
            return `
                <div style="display:flex;align-items:center;gap:6px;padding:4px 6px;border-bottom:1px solid #252525;font-size:11px">
                    <span style="color:#888;min-width:18px">${idx + 1}.</span>
                    <span style="color:#ce9178;font-family:monospace;flex:1;word-break:break-all">${escapeHtml(c.syntax)}</span>
                    <span style="background:#3c3c3c;color:#999;padding:1px 5px;border-radius:3px;font-size:10px">${escapeHtml(c.type)}</span>
                    <span style="font-size:10px;width:50px;text-align:right">${mc}</span>
                    <span style="font-size:10px;color:#6a9955;width:30px;text-align:right">${c.score}</span>
                </div>
            `;
        }).join('');

        box.innerHTML = `
            <div style="padding:10px 16px;background:#2d2d2d;border-bottom:1px solid #444;display:flex;justify-content:space-between;align-items:center">
                <span style="font-weight:bold;font-size:13px">&#128190; 保存到元素库</span>
                <button id="libdlg-cancel-x" style="background:none;border:none;color:#888;cursor:pointer;font-size:14px">&#10005;</button>
            </div>
            <div style="padding:8px 16px;background:#252526;border-bottom:1px solid #444;font-size:11px;color:#bbb;word-break:break-all">
                <span style="color:#ce9178">&lt;${tag}&gt;</span> ${text} · 共 ${cands.length} 个候选
            </div>
            <div style="flex:1;overflow-y:auto;padding:12px 16px">
                <div style="margin-bottom:10px">
                    <label style="display:block;color:#888;font-size:11px;margin-bottom:3px">元素名(可选)</label>
                    <input id="libdlg-name" type="text" value="${defaultName}"
                           style="width:100%;background:#3c3c3c;border:1px solid #555;color:#fff;border-radius:4px;padding:5px 8px;font-size:12px;box-sizing:border-box">
                </div>
                <div style="margin-bottom:10px">
                    <label style="display:block;color:#888;font-size:11px;margin-bottom:4px">候选定位器 (${cands.length} 个 · 带命中数 · 分数):</label>
                    <div style="background:#1a1a1a;border:1px solid #333;border-radius:4px;max-height:180px;overflow-y:auto">
                        ${candsHtml}
                    </div>
                </div>
                <div style="margin-bottom:10px">
                    <label style="display:block;color:#888;font-size:11px;margin-bottom:4px">&#128247; 截图预览</label>
                    <div style="background:#1a1a1a;border:1px solid #333;border-radius:4px;padding:6px;text-align:center">
                        ${imgBlock}
                    </div>
                </div>
            </div>
            <div style="padding:10px 16px;background:#2d2d2d;border-top:1px solid #444;display:flex;justify-content:flex-end;gap:10px">
                <button id="libdlg-cancel" style="background:#3c3c3c;border:none;color:#fff;border-radius:4px;padding:6px 16px;cursor:pointer">取消 (Esc)</button>
                <button id="libdlg-confirm" style="background:#4a8a4a;border:none;color:#fff;border-radius:4px;padding:6px 16px;cursor:pointer">确认保存 (Ctrl+Enter)</button>
            </div>
        `;
        overlay.appendChild(box);
        document.body.appendChild(overlay);

        const nameInput = box.querySelector('#libdlg-name');
        const confirmBtn = box.querySelector('#libdlg-confirm');
        const cancelBtn = box.querySelector('#libdlg-cancel');
        const cancelXBtn = box.querySelector('#libdlg-cancel-x');

        const cleanup = () => {
            overlay.remove();
            dialogOpen = false;
            clearMatchHighlights();
            if (!altPhysicallyDown && captureMode) captureSticky = true;
        };

        const onConfirm = async () => {
            const name = nameInput.value.trim() || defaultName;
            const features = buildFeatureSnapshot(elRef);
            const item = {
                name,
                description: '',
                locator: top.syntax,
                locator_type: top.type,
                method: lastUsedMethod || 'ele',
                candidates: cands,
                features,
                css_selector: convertToCssForTest(top.syntax, top.type) || top.syntax.replace(/^css:/, ''),
                tag,
                text_preview: (elRef.innerText || '').trim().slice(0, 50),
                page_url: window.location.href,
                hostname: window.location.hostname,
                screenshot: screenshot || null,
            };

            // 先上传到服务端
            try {
                const res = await _fetchViaBackground(
                    `${backendUrl}/api/elements`,
                    'POST',
                    _authHeaders(),
                    JSON.stringify(item)
                );
                if (res.ok) {
                    const saved = await res.json();
                    elementLibrary.unshift(saved);
                    showToast(`已保存到云端: ${name}`);
                } else {
                    throw new Error(`HTTP ${res.status}`);
                }
            } catch (e) {
                console.log('[onConfirm] 云端保存失败,回退本地:', e);
                // fallback: 保存到本地
                item.id = Date.now();
                elementLibrary.unshift(item);
                saveLibrary();
                showToast(`已保存到本地: ${name}`);
            }

            if (libraryPanel) createLibraryPanel();
            cleanup();
        };

        confirmBtn.addEventListener('click', onConfirm);
        cancelBtn.addEventListener('click', cleanup);
        if (cancelXBtn) cancelXBtn.addEventListener('click', cleanup);

        const onDialogKeyDown = (ev) => {
            if (ev.key === 'Escape') {
                ev.preventDefault();
                ev.stopPropagation();
                cleanup();
            } else if (ev.key === 'Enter' && ev.ctrlKey) {
                ev.preventDefault();
                ev.stopPropagation();
                onConfirm();
            } else if (ev.key === 'Alt' || ev.key === 'AltGraph') {
                ev.preventDefault();
            }
        };
        overlay.addEventListener('keydown', onDialogKeyDown);

        setTimeout(() => nameInput.focus(), 0);
        setTimeout(() => nameInput.select(), 10);
    }

    // ==================== 执行引擎 ====================
    async function runWorkflowNodes(nodes) {
        // Build parent-child map
        const byParent = {};
        for (const n of nodes) {
            const pid = n.parent_id || 0;
            if (!byParent[pid]) byParent[pid] = [];
            byParent[pid].push(n);
        }
        for (const k in byParent) {
            byParent[k].sort((a, b) => a.order - b.order);
        }

        async function execGroup(parentId) {
            const group = byParent[parentId] || [];
            for (const node of group) {
                await execNode(node);
            }
        }

        async function execNode(node) {
            const extra = node.extra || {};
            const loc = node.locator || '';
            const method = node.method || 'ele';
            showToast(`执行: ${node.type} -> ${loc.slice(0, 30)}`);

            switch (node.type) {
                case 'click': {
                    const el = await _findElement(loc, method);
                    if (el) el.click();
                    break;
                }
                case 'input': {
                    const el = await _findElement(loc, method);
                    if (el) {
                        el.focus();
                        el.value = extra.text || '';
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    break;
                }
                case 'getText': {
                    const el = await _findElement(loc, method);
                    if (el) console.log('[Workflow] text:', el.innerText);
                    break;
                }
                case 'getAttr': {
                    const el = await _findElement(loc, method);
                    if (el) console.log('[Workflow] attr:', el.getAttribute(extra.attrName || ''));
                    break;
                }
                case 'hover': {
                    const el = await _findElement(loc, method);
                    if (el) {
                        el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                        el.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
                    }
                    break;
                }
                case 'waitFor': {
                    const sec = extra.seconds || 10;
                    const deadline = Date.now() + sec * 1000;
                    while (Date.now() < deadline) {
                        const el = _findElementSync(loc, method);
                        if (el) break;
                        await new Promise(r => setTimeout(r, 500));
                    }
                    break;
                }
                case 'forEach': {
                    const els = _findElementsSync(loc, method);
                    for (const item of els) {
                        // Execute children with item as context
                        const children = byParent[node.id] || [];
                        for (const child of children) {
                            // For children of forEach, we could scope to item
                            // For now, execute as-is since we don't have per-item scoping yet
                            await execNode(child);
                        }
                    }
                    break;
                }
                case 'if': {
                    const el = _findElementSync(loc, method);
                    if (el) {
                        const children = byParent[node.id] || [];
                        for (const child of children) {
                            await execNode(child);
                        }
                    }
                    break;
                }
                case 'custom': {
                    console.log('[Workflow] custom:', extra.description || '');
                    break;
                }
            }
        }

        async function _findElement(loc, method) {
            // Simple CSS fallback for now
            const css = _locatorToCss(loc);
            if (!css) return null;
            return document.querySelector(css);
        }

        function _findElementSync(loc, method) {
            const css = _locatorToCss(loc);
            if (!css) return null;
            return document.querySelector(css);
        }

        function _findElementsSync(loc, method) {
            const css = _locatorToCss(loc);
            if (!css) return [];
            return Array.from(document.querySelectorAll(css));
        }

        function _locatorToCss(loc) {
            if (!loc) return null;
            if (loc.startsWith('css:')) return loc.slice(4);
            if (loc.startsWith('#')) return loc;
            if (loc.startsWith('.')) return loc;
            if (loc.startsWith('tag:')) {
                const m = loc.match(/^tag:(\w+)(?:@(.+))?/);
                if (!m) return null;
                if (!m[2]) return m[1];
                const attr = m[2];
                if (attr.startsWith('text()=')) return `${m[1]}:contains(${JSON.stringify(attr.slice(7))})`;
                const am = attr.match(/^(\w+)=(.+)$/);
                if (am) return `${m[1]}[${am[1]}="${am[2].replace(/"/g, '\\"')}"]`;
                return m[1];
            }
            if (loc.startsWith('@')) {
                const m = loc.match(/^@([\w\-:]+)=(.+)$/);
                if (m) return `[${m[1]}="${m[2].replace(/"/g, '\\"')}"]`;
            }
            if (loc.startsWith('xpath:')) return null;
            return loc;
        }

        await execGroup(0);
        showToast('工作流执行完成');
    }

    async function clearAllData() {
        elementLibrary = [];
        actionSteps = [];
        await chrome.storage.local.remove([STORAGE_KEY_LIBRARY, STORAGE_KEY_STEPS]);
    }

    // ==================== DrissionPage 定位语法候选生成 ====================
    function isStableId(id) {
        if (!id) return false;
        if (id.length > 50) return false;
        // React 自动生成: :r1:, :R1q:
        if (/^:[Rr][a-z0-9]*:$/.test(id)) return false;
        // emotion / css-in-js: css-1abc23
        if (/^css-[a-z0-9]{4,}$/i.test(id)) return false;
        // 框架前缀 + hash: mui-abc123, chakra-xyz789
        if (/^(mui|chakra|ant|ember|ng|vue|svelte)[-_][a-z0-9]{4,}/i.test(id)) return false;
        // 纯 hash 段
        if (/^[a-f0-9]{10,}$/i.test(id)) return false;
        // 多个 hash 段
        const hashSegs = (id.match(/_[a-f0-9]{6,}/g) || []).length;
        if (hashSegs >= 2) return false;
        return /^[a-zA-Z][a-zA-Z0-9_\-:]*$/.test(id);
    }

    function isStableClass(cls) {
        if (!cls || cls.length < 2) return false;
        // 排除插件自己注入的 class(orch-highlight / orch-highlight-multi 等)
        if (/^orch-/i.test(cls)) return false;
        // CSS Modules: name__hash 或 name___hash
        if (/_{2,}[a-z0-9]{4,}/i.test(cls)) return false;
        // emotion: css-1abc23
        if (/^css-[a-z0-9]{4,}$/i.test(cls)) return false;
        // 纯 hash: _a8f7d2c
        if (/^_[a-f0-9]{6,}$/i.test(cls)) return false;
        return true;
    }

    function getDirectText(el) {
        let t = '';
        for (const node of el.childNodes) {
            if (node.nodeType === Node.TEXT_NODE) t += node.textContent;
        }
        return t.trim().replace(/\s+/g, ' ');
    }

    function buildFeatureSnapshot(element) {
        if (!element || element.nodeType !== Node.ELEMENT_NODE) return {};
        const EXCLUDE_ATTR_PATTERNS = [
            /^data-v-[a-f0-9]+$/i,       // Vue scoped CSS marker
            /^data-reactroot$/i,
            /^data-react/i,               // React 内部
            /^v-/i,                       // Vue 模板编译产物
            /^_ng/i,                      // Angular
            /^style$/i,                   // 太长,不存
            /^class$/i,                   // 已在 classes 字段
            /^id$/i,                      // 已在 id 字段
        ];
        const attrs = {};
        try {
            for (const attr of element.attributes) {
                const name = attr.name;
                if (EXCLUDE_ATTR_PATTERNS.some(p => p.test(name))) continue;
                let val = attr.value || '';
                if (val.length > 200) val = val.slice(0, 200) + '…';
                attrs[name] = val;
            }
        } catch (e) {}
        let innerText = '';
        try { innerText = (element.innerText || '').trim().slice(0, 200); } catch (e) {}
        let outerHtml = '';
        try {
            outerHtml = element.outerHTML || '';
            outerHtml = outerHtml.replace(/\bclass\s*=\s*"([^"]*)"/gi, (_m, cls) => {
                const kept = cls.split(/\s+/).filter(c => c && !/^orch-/i.test(c));
                return kept.length ? `class="${kept.join(' ')}"` : '';
            }).replace(/\bclass\s*=\s*'([^']*)'/gi, (_m, cls) => {
                const kept = cls.split(/\s+/).filter(c => c && !/^orch-/i.test(c));
                return kept.length ? `class='${kept.join(' ')}'` : '';
            });
            if (outerHtml.length > 500) outerHtml = outerHtml.slice(0, 500) + '…';
        } catch (e) {}
        return {
            tag: element.tagName.toLowerCase(),
            id: element.id || '',
            classes: element.classList
                ? Array.from(element.classList).filter(c => !/^orch-/i.test(c))
                : [],
            attrs,
            direct_text: getDirectText(element),
            inner_text: innerText,
            outer_html: outerHtml,
        };
    }

    function attrValNeedsCssFallback(v) {
        // DrissionPage 文档明确说:属性中包含 @ / 引号等特殊字符,@ 写法不能正确匹配,需用 css selector
        return /[@'"\n\r\t]/.test(v) || v.includes('=');
    }

    function escapeAttrVal(v) {
        return v.replace(/\n/g, ' ').trim();
    }

    function cssEscape(v) {
        // 给 [attr="..."] 里的 value 用,只处理双引号和反斜杠
        return v.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    }

    function getOldCssSelector(element) {
        if (!element || element === document.body) return 'body';
        if (element.id && /^[a-zA-Z][a-zA-Z0-9_-]*$/.test(element.id)) return '#' + element.id;
        const dataAttrs = ['data-testid', 'data-id', 'data-key', 'data-name', 'data-e2e'];
        for (const attr of dataAttrs) {
            const val = element.getAttribute(attr);
            if (val) return `[${attr}="${val}"]`;
        }
        if (element.classList && element.classList.length > 0) {
            const classes = Array.from(element.classList)
                .filter(c => c.length > 2 && !c.includes('_') && !/^orch-/i.test(c))
                .slice(0, 2);
            if (classes.length > 0) return '.' + classes.join('.');
        }
        const parent = element.parentElement;
        if (parent) {
            const siblings = Array.from(parent.children).filter(child => child.tagName === element.tagName);
            const index = siblings.indexOf(element) + 1;
            const tagName = element.tagName.toLowerCase();
            if (siblings.length === 1) return tagName;
            return `${tagName}:nth-child(${index})`;
        }
        return element.tagName.toLowerCase();
    }

    function getElementXPath(element) {
        if (!element || element === document.body) return '/html/body';
        const segs = [];
        let el = element;
        while (el && el.nodeType === Node.ELEMENT_NODE && el !== document.body) {
            const parent = el.parentElement;
            if (!parent) break;
            const sameTag = Array.from(parent.children).filter(c => c.tagName === el.tagName);
            const idx = sameTag.indexOf(el) + 1;
            const tag = el.tagName.toLowerCase();
            segs.unshift(sameTag.length === 1 ? tag : `${tag}[${idx}]`);
            el = parent;
            if (segs.length > 6) break;  // 限制深度,避免过长 xpath
        }
        return '//body/' + segs.join('/');
    }

    function convertToCssForTest(syntax, type) {
        try {
            switch (type) {
                case 'id':
                    return syntax;  // '#xxx'
                case 'class':
                    // '.xxx' 直接是 CSS,但 DP 是字面量,可能含空格 — 实际生成时只单 class,直接用
                    return syntax;
                case 'data-attr':
                case 'aria':
                case 'name': {
                    const m = syntax.match(/^@([\w\-:]+)=(.+)$/);
                    if (!m) return null;
                    return `[${m[1]}="${cssEscape(m[2])}"]`;
                }
                case 'tag_class': {
                    const m = syntax.match(/^tag:(\w+)@class=(.+)$/);
                    if (!m) return null;
                    // class 字面量可能含空格 — 用 [class~="x"] 处理
                    return `${m[1]}[class~="${cssEscape(m[2])}"]`;
                }
                case 'multi_attr': {
                    // '@@class:foo@@class:bar' or '@@a=1@@b=2'
                    const parts = syntax.split('@@').filter(Boolean);
                    return parts.map(p => {
                        const mm = p.match(/^([\w\-():]+)([=:^$])(.+)$/);
                        if (!mm) return '';
                        const opMap = { '=': '=', ':': '*=', '^': '^=', '$': '$=' };
                        let attr = mm[1];
                        if (attr === 'text()' || attr === 'text') return '';  // CSS 无法表达
                        return `[${attr}${opMap[mm[2]]}"${cssEscape(mm[3])}"]`;
                    }).join('');
                }
                case 'tag_attr': {
                    const m = syntax.match(/^tag:(\w+)@([\w\-:]+)=(.+)$/);
                    if (!m) return null;
                    return `${m[1]}[${m[2]}="${cssEscape(m[3])}"]`;
                }
                case 'css':
                    return syntax.replace(/^css:/, '');
                case 'text':
                case 'tag_text':
                case 'xpath':
                default:
                    return null;  // 无法用 CSS 验证
            }
        } catch (e) {
            return null;
        }
    }

    function verifyLocator(syntax, type) {
        if (type === 'xpath') {
            const xp = syntax.replace(/^xpath:/, '');
            try {
                const r = document.evaluate(xp, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                return r.snapshotLength;
            } catch (e) {
                return -1;
            }
        }
        const css = convertToCssForTest(syntax, type);
        if (!css) return -1;  // 未验证
        try {
            return document.querySelectorAll(css).length;
        } catch (e) {
            return -1;
        }
    }

    // 走到祖先节点,挑一个能作为 CSS 上下文锚点的简短选择器
    function getSimpleAncestorSelector(el) {
        if (!el || el === document.body) return null;
        if (el.id && isStableId(el.id)) return '#' + el.id;
        const dataAttrs = ['data-testid', 'data-test', 'data-id', 'data-name', 'data-key', 'data-e2e'];
        for (const a of dataAttrs) {
            const v = el.getAttribute(a);
            if (v && v.length < 80 && !attrValNeedsCssFallback(v)) {
                return `[${a}="${cssEscape(v)}"]`;
            }
        }
        const tag = el.tagName.toLowerCase();
        // 语义化标签做锚点很合适(header / main / nav / footer / aside / article / section)
        if (['header','main','footer','nav','aside','article','section'].includes(tag)) return tag;
        if (el.classList) {
            const stable = Array.from(el.classList).filter(isStableClass);
            if (stable.length > 0) return '.' + stable[0];
        }
        return null;
    }

    // 沿 DOM 往上拼一条带稳定 class + :nth-of-type 的结构路径,边拼边验证唯一性
    function buildStructuralCss(element) {
        if (!element || element === document.body) return null;
        const segs = [];
        let cur = element;
        while (cur && cur !== document.body && segs.length < 8) {
            const parent = cur.parentElement;
            if (!parent) break;
            const tag = cur.tagName.toLowerCase();
            const sameTagSiblings = Array.from(parent.children).filter(c => c.tagName === cur.tagName);
            const myIdx = sameTagSiblings.indexOf(cur) + 1;
            const stableClasses = cur.classList ? Array.from(cur.classList).filter(isStableClass) : [];
            let seg;
            if (cur.id && isStableId(cur.id)) {
                seg = '#' + cur.id;
            } else if (stableClasses.length > 0) {
                seg = sameTagSiblings.length === 1
                    ? `${tag}.${stableClasses[0]}`
                    : `${tag}.${stableClasses[0]}:nth-of-type(${myIdx})`;
            } else {
                seg = sameTagSiblings.length === 1 ? tag : `${tag}:nth-of-type(${myIdx})`;
            }
            segs.unshift(seg);
            const trial = segs.join(' > ');
            try {
                if (document.querySelectorAll(trial).length === 1) return trial;
            } catch (e) {}
            if (seg.startsWith('#')) break; // id 已加,停止继续往上
            cur = parent;
        }
        return segs.length ? segs.join(' > ') : null;
    }

    // xpath 的 CSS 等价完整路径(每层都带 nth-of-type,不求最简只求稳)
    function getElementCssPath(element) {
        if (!element || element === document.body) return 'body';
        const segs = [];
        let cur = element;
        while (cur && cur !== document.body && segs.length < 10) {
            const parent = cur.parentElement;
            if (!parent) break;
            const tag = cur.tagName.toLowerCase();
            const sameTag = Array.from(parent.children).filter(c => c.tagName === cur.tagName);
            const idx = sameTag.indexOf(cur) + 1;
            const stableClasses = cur.classList ? Array.from(cur.classList).filter(isStableClass) : [];
            let seg;
            if (cur.id && isStableId(cur.id)) {
                seg = '#' + cur.id;
            } else if (stableClasses.length > 0) {
                seg = `${tag}.${stableClasses[0]}:nth-of-type(${idx})`;
            } else {
                seg = `${tag}:nth-of-type(${idx})`;
            }
            segs.unshift(seg);
            if (seg.startsWith('#')) break;
            cur = parent;
        }
        return segs.join(' > ');
    }

    function generateLocators(element) {
        if (!element || element === document.body) {
            return [{ syntax: 'tag:body', label: 'body', type: 'tag', score: 10, matchCount: 1 }];
        }
        const tag = element.tagName.toLowerCase();
        const candidates = [];

        // 1. id
        const id = element.id;
        if (id) {
            const stable = isStableId(id);
            candidates.push({
                syntax: '#' + id,
                label: 'id: ' + id,
                type: 'id',
                score: stable ? 100 : 35,
            });
        }

        // 2. data-* 测试属性(高优先级)
        const dataAttrs = ['data-testid', 'data-test', 'data-test-id', 'data-cy',
                           'data-qa', 'data-e2e', 'data-id', 'data-key', 'data-name'];
        for (const attr of dataAttrs) {
            const v = element.getAttribute(attr);
            if (!v || v.length > 80) continue;
            if (attrValNeedsCssFallback(v)) {
                candidates.push({
                    syntax: `css:[${attr}="${cssEscape(v)}"]`,
                    label: `${attr}=${v} (css)`,
                    type: 'css',
                    score: 92,
                });
            } else {
                candidates.push({
                    syntax: `@${attr}=${escapeAttrVal(v)}`,
                    label: `${attr}=${v}`,
                    type: 'data-attr',
                    score: 95,
                });
            }
        }

        // 3. 语义属性
        const semanticAttrs = [
            { name: 'aria-label', score: 88, type: 'aria' },
            { name: 'name', score: 85, type: 'name' },
            { name: 'role', score: 60, type: 'aria' },
            { name: 'placeholder', score: 65, type: 'aria' },
            { name: 'title', score: 60, type: 'aria' },
        ];
        for (const { name, score, type } of semanticAttrs) {
            const v = element.getAttribute(name);
            if (!v || v.length > 80) continue;
            if (attrValNeedsCssFallback(v)) {
                candidates.push({
                    syntax: `css:[${name}="${cssEscape(v)}"]`,
                    label: `${name}=${v} (css)`,
                    type: 'css',
                    score: score - 5,
                });
            } else {
                candidates.push({
                    syntax: `@${name}=${escapeAttrVal(v)}`,
                    label: `${name}=${v}`,
                    type,
                    score,
                });
            }
        }

        // 4. 直接文本(短文本才用)
        const directText = getDirectText(element);
        if (directText && directText.length > 0 && directText.length < 30 && !/['"]/.test(directText)) {
            candidates.push({
                syntax: `tag:${tag}@text()=${directText}`,
                label: `${tag} + 文本: "${directText}"`,
                type: 'tag_text',
                score: 82,
            });
            candidates.push({
                syntax: `text=${directText}`,
                label: `text: "${directText}"`,
                type: 'text',
                score: 75,
            });
        }

        // 5. type 属性(input/button 类)
        if (tag === 'input' || tag === 'button') {
            const typeAttr = element.getAttribute('type');
            if (typeAttr) {
                candidates.push({
                    syntax: `tag:${tag}@type=${typeAttr}`,
                    label: `${tag}[type=${typeAttr}]`,
                    type: 'tag_attr',
                    score: 50,
                });
            }
        }

        // 6. class
        if (element.classList && element.classList.length > 0) {
            const stableClasses = Array.from(element.classList).filter(isStableClass);
            if (stableClasses.length === 1) {
                const c = stableClasses[0];
                candidates.push({
                    syntax: '.' + c,
                    label: 'class: .' + c,
                    type: 'class',
                    score: 65,
                });
                candidates.push({
                    syntax: `tag:${tag}@class=${c}`,
                    label: `${tag}.${c}`,
                    type: 'tag_class',
                    score: 70,
                });
            } else if (stableClasses.length >= 2) {
                const top2 = stableClasses.slice(0, 2);
                candidates.push({
                    syntax: `@@class:${top2[0]}@@class:${top2[1]}`,
                    label: `class 包含: ${top2[0]} & ${top2[1]}`,
                    type: 'multi_attr',
                    score: 72,
                });
                candidates.push({
                    syntax: '.' + top2[0],
                    label: 'class: .' + top2[0],
                    type: 'class',
                    score: 55,
                });
                candidates.push({
                    syntax: `tag:${tag}@class=${top2[0]}`,
                    label: `${tag}.${top2[0]}`,
                    type: 'tag_class',
                    score: 60,
                });
            } else if (element.classList.length > 0) {
                // 全是不稳定 class,只给一个弱兜底(跳过插件自己注入的 orch-* class)
                const first = Array.from(element.classList).find(c => !/^orch-/i.test(c));
                if (first) {
                    candidates.push({
                        syntax: '.' + first,
                        label: 'class(弱): .' + first.slice(0, 30),
                        type: 'class',
                        score: 25,
                    });
                }
            }
        }

        // 6.5 子元素特征定位(如 :has(>svg) )
        const stableClassesForChild = element.classList ? Array.from(element.classList).filter(isStableClass) : [];
        const childTags = [...new Set(Array.from(element.children).map(c => c.tagName.toLowerCase()))].slice(0, 3);
        for (const childTag of childTags) {
            if (stableClassesForChild.length > 0) {
                candidates.push({
                    syntax: `css:${tag}.${stableClassesForChild[0]}:has(>${childTag})`,
                    label: `${tag}.${stableClassesForChild[0]}:has(>${childTag}) (子元素特征)`,
                    type: 'css',
                    score: 64,
                });
            }
            candidates.push({
                syntax: `css:${tag}:has(>${childTag})`,
                label: `${tag}:has(>${childTag}) (子元素特征)`,
                type: 'css',
                score: 60,
            });
        }

        // 7. xpath 兜底
        candidates.push({
            syntax: 'xpath:' + getElementXPath(element),
            label: 'xpath (路径)',
            type: 'xpath',
            score: 15,
        });

        // 7.5 完整结构 CSS 路径(xpath 的 CSS 等价版,每层 nth-of-type)
        candidates.push({
            syntax: 'css:' + getElementCssPath(element),
            label: 'css (完整结构)',
            type: 'css',
            score: 16,
        });

        // 8. CSS 原算法兜底
        candidates.push({
            syntax: 'css:' + getOldCssSelector(element),
            label: 'css (原算法)',
            type: 'css',
            score: 12,
        });

        // 9. 验证 + 排序
        candidates.forEach(c => {
            c.matchCount = verifyLocator(c.syntax, c.type);
        });

        // 9.5 若无 CSS 类 1 命中候选(xpath 不算),用祖先节点收窄,保证至少一个 CSS 命中 1
        const hasCssUnique = candidates.some(c => c.type !== 'xpath' && c.matchCount === 1);
        if (!hasCssUnique && element !== document.body) {
            const seenBase = new Set();
            const bases = [];
            for (const c of candidates) {
                if (c.type === 'xpath' || c.matchCount === 0) continue;
                const css = convertToCssForTest(c.syntax, c.type);
                if (css && !seenBase.has(css)) {
                    seenBase.add(css);
                    bases.push(css);
                }
            }
            let cur = element.parentElement;
            let depth = 0;
            let foundUnique = false;
            while (cur && cur !== document.body && depth < 6 && !foundUnique) {
                const ancSel = getSimpleAncestorSelector(cur);
                if (ancSel) {
                    for (const base of bases) {
                        const combined = `${ancSel} ${base}`;
                        let count = -1;
                        try { count = document.querySelectorAll(combined).length; } catch (e) {}
                        if (count >= 1) {
                            candidates.push({
                                syntax: `css:${combined}`,
                                label: `${combined} (祖先收窄)`,
                                type: 'css',
                                score: count === 1 ? 78 : 28,
                                matchCount: count,
                            });
                            if (count === 1) foundUnique = true;
                        }
                    }
                }
                cur = cur.parentElement;
                depth++;
            }
        }

        // 9.6 若祖先收窄后仍无 CSS 1 命中,用 :nth-of-type 拼带稳定类的结构路径兜底
        const stillNoCssUnique = !candidates.some(c => c.type !== 'xpath' && c.matchCount === 1);
        if (stillNoCssUnique && element !== document.body) {
            const struct = buildStructuralCss(element);
            if (struct) {
                let count = -1;
                try { count = document.querySelectorAll(struct).length; } catch (e) {}
                if (count >= 1) {
                    candidates.push({
                        syntax: 'css:' + struct,
                        label: struct + ' (结构路径)',
                        type: 'css',
                        score: count === 1 ? 76 : 22,
                        matchCount: count,
                    });
                }
            }
        }

        return candidates
            .filter(c => c.matchCount !== 0)  // 已验证为 0 命中的丢掉,-1 未验证的保留
            .sort((a, b) => {
                const aUnique = a.matchCount === 1 ? 2 : (a.matchCount === -1 ? 1 : 0);
                const bUnique = b.matchCount === 1 ? 2 : (b.matchCount === -1 ? 1 : 0);
                if (aUnique !== bUnique) return bUnique - aUnique;
                return b.score - a.score;
            });
    }

    // ==================== 元素库管理 ====================
    function saveCurrentElement(name, element, locator, locatorType, candidates, features, description) {
        if (!element) {
            alert('请先悬浮到要保存的元素上');
            return;
        }
        const finalName = name || `element_${elementLibrary.length + 1}`;
        const cssEquiv = convertToCssForTest(locator, locatorType) || (locator || '').replace(/^css:/, '');
        let hostname = '';
        try { hostname = new URL(window.location.href).hostname; } catch (e) {}
        const item = {
            id: Date.now(),
            name: finalName,
            description: description || '',
            locator: locator || '',
            locator_type: locatorType || 'css',
            method: lastUsedMethod || currentMethod || 'ele',
            candidates: candidates || [],
            features: features || buildFeatureSnapshot(element),
            css_selector: cssEquiv,
            tag: element.tagName.toLowerCase(),
            text_preview: (element.innerText || '').trim().slice(0, 50),
            created_at: new Date().toLocaleString(),
            page_url: window.location.href,
            hostname,
        };
        elementLibrary.push(item);
        saveLibrary();
        showToast(`已保存元素: ${finalName}`);
        if (libraryPanel) createLibraryPanel();
    }

    // ==================== 操作步骤管理 ====================
    function addActionStep(actionType, elementId, elementName, locator, locatorType, method, extraData, candidates, screenshot) {
        const cssEquiv = convertToCssForTest(locator, locatorType) || (locator || '').replace(/^css:/, '');
        const step = {
            id: Date.now() + Math.random(),
            action: actionType,
            element_id: elementId,
            element_name: elementName,
            locator: locator || '',
            locator_type: locatorType || 'css',
            method: method || 'ele',
            selector: cssEquiv,
            candidates: candidates || [],
            extra: extraData || {},
            screenshot: screenshot || null,
            timestamp: new Date().toLocaleTimeString()
        };
        actionSteps.push(step);
        saveSteps();
        refreshStepsPanel();
        showToast(`已添加: ${actionType}`);
        syncStepToBackend(step);
        return step;
    }

    function deleteStep(stepId) {
        actionSteps = actionSteps.filter(s => s.id !== stepId);
        saveSteps();
        refreshStepsPanel();
    }

    function onKeyDown(e) {
        if (!isVisible) return;
        if (dialogOpen) return;  // dialog 自己接管键盘
        // 输入框内按键不处理(但 Alt 单按例外:用户可能想从输入框进入捕获模式)
        const inTextField = e.target.matches && e.target.matches('input, textarea, [contenteditable]');

        // Alt 物理单按:进入捕获模式 + 阻浏览器菜单激活
        if (e.key === 'Alt' || e.key === 'AltGraph') {
            altPhysicallyDown = true;
            e.preventDefault();
            if (!captureMode) enterCaptureMode();
            return;
        }

        if (inTextField) return;

        // Alt + 修饰键
        if (e.altKey && captureMode) {
            switch (e.key) {
                case '1':
                    e.preventDefault();
                    saveElementToLibraryConfirm();
                    return;
                case '2':
                    e.preventDefault();
                    openCaptureDialogForCurrentHoverWithScreenshot();
                    return;
                case 'q': case 'Q':
                    e.preventDefault();
                    if (!lockedElement) {
                        showToast('请先 hover 一个元素');
                        return;
                    }
                    // 在 lockedElement 的 children 中找合适的子元素
                    // 1) 优先找包含鼠标位置的 child
                    let nextEl = null;
                    const hx = lastHoverX, hy = lastHoverY;
                    for (const child of lockedElement.children) {
                        if (isGhostElement(child)) continue;
                        const r = child.getBoundingClientRect();
                        if (r.width <= 0 || r.height <= 0) continue;
                        if (hx >= r.left && hx <= r.right && hy >= r.top && hy <= r.bottom) {
                            nextEl = child;
                            break; // 命中第一个包含鼠标的 child
                        }
                    }
                    // 2) 如果没命中(鼠标在 padding 区域),找 children 中离鼠标最近的
                    if (!nextEl) {
                        let minDist = Infinity;
                        for (const child of lockedElement.children) {
                            if (isGhostElement(child)) continue;
                            const r = child.getBoundingClientRect();
                            if (r.width <= 0 || r.height <= 0) continue;
                            const cx = r.left + r.width / 2;
                            const cy = r.top + r.height / 2;
                            const dist = Math.sqrt((hx - cx) ** 2 + (hy - cy) ** 2);
                            if (dist < minDist) {
                                minDist = dist;
                                nextEl = child;
                            }
                        }
                    }
                    if (nextEl && nextEl !== lockedElement) {
                        lockedElement = nextEl;
                        currentHoverElement = nextEl;
                        highlightCurrentEl = nextEl;
                        lastHoveredEl = nextEl;
                        redrawHighlights();
                        const cands = generateLocators(nextEl);
                        lockedCandidates = cands;
                        currentCandidates = cands;
                        selectedLocatorIndex = 0;
                        if (cands.length > 0) {
                            lockedLocator = cands[0].syntax;
                            lockedLocatorType = cands[0].type;
                            const cssEquiv = convertToCssForTest(cands[0].syntax, cands[0].type);
                            lockedSelector = cssEquiv || getOldCssSelector(nextEl);
                            currentHoverSelector = lockedSelector;
                        }
                        renderLocatorChooser();
                        showToast(`深入: ${_debugLabel(nextEl)}`);
                    } else {
                        showToast('无更深层子元素');
                    }
                    return;
                case 'w': case 'W': {
                    e.preventDefault();
                    if (!lockedElement) {
                        showToast('请先 hover 一个元素');
                        return;
                    }
                    const parent = lockedElement.parentElement;
                    if (!parent) {
                        showToast('无父元素,无法切换兄弟');
                        return;
                    }
                    // 收集可见兄弟元素(始终包含 lockedElement 自身,过滤其它幽灵/扩展面板/零尺寸)
                    const sibs = [];
                    for (const sib of parent.children) {
                        if (sib === lockedElement) {
                            sibs.push(sib);
                            continue;
                        }
                        if (isGhostElement(sib)) continue;
                        if (isExtensionElement(sib)) continue;
                        const r = sib.getBoundingClientRect();
                        if (r.width <= 0 || r.height <= 0) continue;
                        sibs.push(sib);
                    }
                    if (sibs.length <= 1) {
                        showToast('无可切换的兄弟元素');
                        return;
                    }
                    const curIdx = sibs.indexOf(lockedElement);
                    const dir = e.shiftKey ? -1 : 1;
                    const nextIdx = (curIdx + dir + sibs.length) % sibs.length;
                    const sibEl = sibs[nextIdx];
                    lockedElement = sibEl;
                    currentHoverElement = sibEl;
                    highlightCurrentEl = sibEl;
                    lastHoveredEl = sibEl;
                    redrawHighlights();
                    const sibCands = generateLocators(sibEl);
                    lockedCandidates = sibCands;
                    currentCandidates = sibCands;
                    selectedLocatorIndex = 0;
                    if (sibCands.length > 0) {
                        lockedLocator = sibCands[0].syntax;
                        lockedLocatorType = sibCands[0].type;
                        const cssEquiv = convertToCssForTest(sibCands[0].syntax, sibCands[0].type);
                        lockedSelector = cssEquiv || getOldCssSelector(sibEl);
                        currentHoverSelector = lockedSelector;
                    }
                    renderLocatorChooser();
                    showToast(`兄弟 ${nextIdx + 1}/${sibs.length}: ${_debugLabel(sibEl)}`);
                    return;
                }
                case 'e': case 'E': {
                    e.preventDefault();
                    if (!lockedElement) {
                        showToast('请先 hover 一个元素');
                        return;
                    }
                    const parent = lockedElement.parentElement;
                    if (!parent || parent === document.documentElement) {
                        showToast('已到顶层元素');
                        return;
                    }
                    if (isExtensionElement(parent)) {
                        showToast('父元素属扩展面板,跳过');
                        return;
                    }
                    lockedElement = parent;
                    currentHoverElement = parent;
                    highlightCurrentEl = parent;
                    lastHoveredEl = parent;
                    redrawHighlights();
                    const parCands = generateLocators(parent);
                    lockedCandidates = parCands;
                    currentCandidates = parCands;
                    selectedLocatorIndex = 0;
                    if (parCands.length > 0) {
                        lockedLocator = parCands[0].syntax;
                        lockedLocatorType = parCands[0].type;
                        const cssEquiv = convertToCssForTest(parCands[0].syntax, parCands[0].type);
                        lockedSelector = cssEquiv || getOldCssSelector(parent);
                        currentHoverSelector = lockedSelector;
                    }
                    renderLocatorChooser();
                    showToast(`父级: ${_debugLabel(parent)}`);
                    return;
                }
                case 'n': case 'N':
                    e.preventDefault();
                    exportAsNaturalLanguage();
                    return;
                case 'j': case 'J':
                    e.preventDefault();
                    exportAsJSON();
                    return;
            }
        }

        if (e.key === 'Escape') {
            e.preventDefault();
            hide();
        }
    }

    function onKeyUp(e) {
        if (!isVisible) return;
        if (e.key === 'Alt' || e.key === 'AltGraph') {
            altPhysicallyDown = false;
            e.preventDefault();  // 关键:防 Chrome/Edge 在 Windows 上 keyup 时激活菜单栏
            if (!captureMode) return;
            if (dialogOpen) return;
            // Sticky:不立刻退出,让 mousemove 检测鼠标离开 lockedElement 时再退出
            captureSticky = true;
        }
    }

    async function onClick(e) {
        if (!isVisible) return;
        if (!e.altKey) return;                  // 只在 Alt 物理按住时拦截
        if (dialogOpen) return;

        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();

        // 优先使用 lockedElement(可能通过 Alt+Q 深入选择),fallback 到坐标解析
        let target = lockedElement;
        if (!target) {
            target = resolveTargetFromPoint();
        }
        if (!target) return;
        if (mainPanel && mainPanel.contains(target)) return;
        if (libraryPanel && libraryPanel.contains(target)) return;
        const dlg = document.getElementById('orch-capture-dialog');
        if (dlg && dlg.contains(target)) return;

        const cands = generateLocators(target);
        showToast('正在截图...');
        pendingScreenshot = await captureElementScreenshot(target);
        openCaptureDialog(target, cands, { screenshot: pendingScreenshot });
    }

    async function openCaptureDialogForCurrentHoverWithScreenshot() {
        if (!lockedElement) {
            showToast('请先 hover 一个元素');
            return;
        }
        const cands = lockedCandidates && lockedCandidates.length
            ? lockedCandidates
            : generateLocators(lockedElement);
        showToast('正在截图...');
        pendingScreenshot = await captureElementScreenshot(lockedElement);
        openCaptureDialog(lockedElement, cands, { screenshot: pendingScreenshot });
    }

    // 保留旧函数名作为兼容入口(Alt+click 直接调用带截图的版本)
    function openCaptureDialogForCurrentHover() {
        openCaptureDialogForCurrentHoverWithScreenshot();
    }

    // ==================== 录入对话框 ====================
    const ACTION_LABELS = {
        click:      '点击 click()',
        getText:    '获取文本 .text',
        input:      '输入 input(text)',
        getAttr:    '获取属性 .attr(name)',
        hover:      '悬停 hover()',
        findWithin: '内嵌查找 .ele(子)',
        waitFor:    '等待出现 wait.ele_displayed',
        custom:     '自定义(仅描述)',
    };
    const ACTION_EXTRA = {
        input:      { field: 'text',        label: '要填入的文本',      type: 'text',   default: '' },
        getAttr:    { field: 'attrName',    label: '属性名',            type: 'text',   default: '' },
        findWithin: { field: 'subSelector', label: '子元素 locator (DrissionPage 语法,如 .item 或 tag:div@text()=xxx)', type: 'text', default: '' },
        waitFor:    { field: 'seconds',     label: '超时秒数',          type: 'number', default: '10' },
    };

    function openCaptureDialog(element, candidates, options) {
        if (dialogOpen) return;
        const opts = options || {};
        const editStepId = opts.editStepId || null;
        const editingStep = editStepId
            ? actionSteps.find(s => s.id === editStepId) || null
            : null;
        if (!element && !editingStep) return;

        // 候选来源:编辑模式优先用 step.candidates;否则 element.generateLocators
        let cands = candidates && candidates.length ? candidates : null;
        if (!cands) {
            cands = editingStep && editingStep.candidates && editingStep.candidates.length
                ? editingStep.candidates
                : (element ? generateLocators(element) : []);
        }
        if (cands.length === 0) {
            alert('该元素没有可用 locator 候选,无法录入');
            return;
        }

        dialogOpen = true;
        clearMatchHighlights();

        // 初始值
        let selectedIdx = 0;
        let selectedMethod = (editingStep ? editingStep.method : lastUsedMethod) || 'ele';
        let selectedAction = (editingStep ? editingStep.action : lastUsedAction) || 'click';
        if (editingStep) {
            const i = cands.findIndex(c => c.syntax === editingStep.locator);
            if (i >= 0) selectedIdx = i;
        }
        const editStepIdx = editingStep ? actionSteps.findIndex(s => s.id === editStepId) : -1;

        const overlay = document.createElement('div');
        overlay.id = 'orch-capture-dialog';
        overlay.style.cssText = `
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.6); z-index: 2147483647;
            display: flex; align-items: center; justify-content: center;
            font-family: 'Monaco', 'Menlo', 'Consolas', monospace; font-size: 12px;
        `;

        const box = document.createElement('div');
        box.style.cssText = `
            background: #1e1e1e; color: #d4d4d4;
            border: 1px solid #444; border-radius: 8px;
            width: 600px; max-width: 92vw; max-height: 88vh;
            display: flex; flex-direction: column; overflow: hidden;
        `;
        box.innerHTML = buildCaptureDialogHTML(element, cands, selectedIdx, selectedMethod, selectedAction,
            { editStepId, editStepIdx, screenshot: opts.screenshot || null });
        overlay.appendChild(box);
        document.body.appendChild(overlay);

        // ---- 引用 ----
        const locatorList   = box.querySelector('#dlg-locator-list');
        const actionSelect  = box.querySelector('#dlg-action');
        const extraBox      = box.querySelector('#dlg-extra');
        const confirmBtn    = box.querySelector('#dlg-confirm');
        const cancelBtn     = box.querySelector('#dlg-cancel');
        const cancelXBtn    = box.querySelector('#dlg-cancel-x');
        const saveCheck     = box.querySelector('#dlg-save-to-lib');     // 编辑模式下不存在
        const saveNameInput = box.querySelector('#dlg-save-name');
        const nameInput     = box.querySelector('#dlg-name');
        const descInput     = box.querySelector('#dlg-desc');

        // 预填编辑值
        if (editingStep) {
            nameInput.value = editingStep.element_name || '';
            descInput.value = editingStep.description || '';
        }

        let expanded = false;

        function bindLocatorRadios() {
            box.querySelectorAll('input[name="dlg-locator"]').forEach(r => {
                r.addEventListener('change', () => {
                    selectedIdx = parseInt(r.value);
                    const c = cands[selectedIdx];
                    highlightMatches(c.syntax, c.type);
                    // 重渲染列表以更新高亮样式
                    locatorList.innerHTML = renderLocatorRadios(cands, selectedIdx, expanded);
                    bindLocatorRadios();
                });
            });
            const expandBtn = locatorList.querySelector('#dlg-locator-expand');
            if (expandBtn) {
                expandBtn.addEventListener('click', () => {
                    expanded = !expanded;
                    locatorList.innerHTML = renderLocatorRadios(cands, selectedIdx, expanded);
                    bindLocatorRadios();
                });
            }
        }
        bindLocatorRadios();

        function refreshMethodStyles() {
            box.querySelectorAll('.dlg-method-btn').forEach(lbl => {
                const m = lbl.getAttribute('data-method');
                const checked = (m === selectedMethod);
                lbl.style.background = checked ? '#4caf50' : '#3c3c3c';
                lbl.style.color = checked ? '#fff' : '#ce9178';
                lbl.style.borderColor = checked ? '#4caf50' : '#555';
                lbl.style.fontWeight = checked ? '600' : 'normal';
            });
        }
        box.querySelectorAll('input[name="dlg-method"]').forEach(r => {
            r.addEventListener('change', () => {
                selectedMethod = r.value;
                refreshMethodStyles();
            });
        });

        actionSelect.addEventListener('change', () => {
            selectedAction = actionSelect.value;
            renderActionExtra(extraBox, selectedAction);
        });
        renderActionExtra(extraBox, selectedAction);
        // 编辑模式:预填 extra
        if (editingStep && editingStep.extra) {
            const ex = editingStep.extra;
            const fillExtra = (field, val) => {
                const el = box.querySelector(`#dlg-extra-${field}`);
                if (el) el.value = (val != null ? val : '');
            };
            if (ex.text != null)        fillExtra('text', ex.text);
            if (ex.attrName)            fillExtra('attrName', ex.attrName);
            if (ex.subSelector)         fillExtra('subSelector', ex.subSelector);
            if (ex.seconds != null)     fillExtra('seconds', ex.seconds);
            if (ex.description != null) descInput.value = descInput.value || ex.description;
        }

        // 保存复选框联动(编辑模式无此区块)
        if (saveCheck) {
            saveCheck.addEventListener('change', () => {
                saveNameInput.disabled = !saveCheck.checked;
                if (saveCheck.checked && !saveNameInput.value && nameInput.value) {
                    saveNameInput.value = nameInput.value;
                }
            });
            saveNameInput.disabled = !saveCheck.checked;
            nameInput.addEventListener('input', () => {
                if (saveCheck.checked && !saveNameInput.value) saveNameInput.value = nameInput.value;
            });
        }

        // 关闭路径
        const cleanup = () => {
            overlay.remove();
            dialogOpen = false;
            clearMatchHighlights();
            // dialog 关闭后:Alt 没按住则启动 sticky
            if (!altPhysicallyDown && captureMode) captureSticky = true;
        };

        const onCancel = () => cleanup();
        const onConfirm = () => {
            const c = cands[selectedIdx];
            if (!c) { alert('请选一个 locator'); return; }
            const extra = collectActionExtra(box, selectedAction, descInput.value.trim());
            if (extra === null) return;

            const elementName = nameInput.value.trim() || (c.label || '').slice(0, 30);
            const description = descInput.value.trim();
            const screenshot = opts.screenshot || pendingScreenshot || null;

            if (editingStep) {
                // 编辑:就地更新步骤
                editingStep.action = selectedAction;
                editingStep.element_name = elementName;
                editingStep.description = description;
                editingStep.locator = c.syntax;
                editingStep.locator_type = c.type;
                editingStep.method = selectedMethod;
                editingStep.extra = extra;
                editingStep.candidates = cands;
                editingStep.screenshot = screenshot;
                const cssEquiv = convertToCssForTest(c.syntax, c.type);
                editingStep.selector = cssEquiv || (c.syntax || '').replace(/^css:/, '');
                saveSteps();
                refreshStepsPanel();
            } else {
                // 新增
                addActionStep(
                    selectedAction, null, elementName,
                    c.syntax, c.type, selectedMethod,
                    extra, cands, screenshot
                );
                // 同时保存到元素库?
                if (saveCheck && saveCheck.checked) {
                    const libName = saveNameInput.value.trim()
                                  || elementName
                                  || `${c.type}_${(c.syntax || '').slice(0, 20).replace(/[^\w]/g, '_')}`
                                  || `element_${elementLibrary.length + 1}`;
                    const features = buildFeatureSnapshot(element);
                    saveCurrentElement(libName, element, c.syntax, c.type, cands, features, description);
                }
            }

            // 记住默认(编辑模式也记住,反映用户最近偏好)
            lastUsedMethod = selectedMethod;
            lastUsedAction = selectedAction;
            persistLastUsed();

            cleanup();
        };

        confirmBtn.addEventListener('click', onConfirm);
        cancelBtn.addEventListener('click', onCancel);
        if (cancelXBtn) cancelXBtn.addEventListener('click', onCancel);

        // 弹框级 keydown
        const onDialogKeyDown = (ev) => {
            if (ev.key === 'Escape') {
                ev.preventDefault();
                ev.stopPropagation();
                onCancel();
            } else if (ev.key === 'Enter' && ev.ctrlKey) {
                ev.preventDefault();
                ev.stopPropagation();
                onConfirm();
            } else if (ev.key === 'Alt' || ev.key === 'AltGraph') {
                ev.preventDefault();
            }
        };
        overlay.addEventListener('keydown', onDialogKeyDown);

        // 初始焦点
        setTimeout(() => {
            if (editingStep) {
                // 编辑模式焦点放描述(最常改)
                if (descInput) descInput.focus();
            } else {
                if (nameInput) nameInput.focus();
            }
        }, 0);

        // 初始高亮
        if (cands[selectedIdx]) {
            highlightMatches(cands[selectedIdx].syntax, cands[selectedIdx].type);
        }
    }

    function renderLocatorRadios(cands, selectedIdx, expanded) {
        const visible = expanded ? cands : cands.slice(0, 5);
        let html = '';
        visible.forEach((c, idx) => {
            const isChecked = idx === selectedIdx;
            const checked = isChecked ? 'checked' : '';
            const rowBg = isChecked ? 'rgba(76,175,80,0.14)' : 'transparent';
            const rowBorder = isChecked ? '#4caf50' : 'transparent';
            const mc = c.matchCount === 1
                ? '<span style="color:#4caf50">1命中</span>'
                : c.matchCount > 1
                    ? `<span style="color:#ffa500">${c.matchCount}命中⚠</span>`
                    : c.matchCount === -1
                        ? '<span style="color:#888">?</span>'
                        : '<span style="color:#888">0</span>';
            html += `
                <label class="dlg-locator-row" data-idx="${idx}" style="display:flex;align-items:center;gap:8px;padding:5px 8px;cursor:pointer;background:${rowBg};border-left:3px solid ${rowBorder};border-radius:0 4px 4px 0;margin:2px 0;transition:background 0.1s">
                    <input type="radio" name="dlg-locator" value="${idx}" ${checked} style="width:14px;height:14px;margin:0;cursor:pointer;accent-color:#4caf50">
                    <span style="color:${isChecked ? '#fff' : '#ce9178'};flex:1;font-family:monospace;font-size:11px;word-break:break-all;font-weight:${isChecked ? '600' : 'normal'}">${escapeHtml(c.syntax)}</span>
                    <span style="background:#3c3c3c;color:#999;padding:1px 5px;border-radius:3px;font-size:10px">${escapeHtml(c.type)}</span>
                    <span style="font-size:10px;width:62px;text-align:right">${mc}</span>
                </label>
            `;
        });
        if (cands.length > 5) {
            const label = expanded ? `△ 收起` : `▽ 展开剩余 ${cands.length - 5} 个`;
            html += `<div id="dlg-locator-expand" style="text-align:center;color:#888;cursor:pointer;padding:4px;font-size:10px">${label}</div>`;
        }
        return html;
    }

    function buildCaptureDialogHTML(element, cands, selectedIdx, defaultMethod, defaultAction, options) {
        const opts = options || {};
        const isEdit = !!opts.editStepId;
        const headerTitle = isEdit ? `&#9999; 编辑步骤 ${opts.editStepIdx != null ? '#' + (opts.editStepIdx + 1) : ''}` : '&#9999; 录入操作步骤';
        const lockedLine = element
            ? `锁定: <span style="color:#ce9178">&lt;${element.tagName.toLowerCase()}&gt;</span> · ${escapeHtml((element.innerText || '').slice(0, 60).replace(/\s+/g, ' '))} · ${cands.length} 候选`
            : `编辑现有步骤 · 候选 ${cands.length} 个 (从录制时快照载入)`;
        const actionOptions = Object.keys(ACTION_LABELS).map(k =>
            `<option value="${k}" ${k === defaultAction ? 'selected' : ''}>${ACTION_LABELS[k]}</option>`
        ).join('');
        const methodRadios = ['ele','eles','s_ele','s_eles'].map(m => {
            const isChecked = m === defaultMethod;
            const bg = isChecked ? '#4caf50' : '#3c3c3c';
            const fg = isChecked ? '#fff' : '#ce9178';
            const border = isChecked ? '#4caf50' : '#555';
            return `
                <label class="dlg-method-btn" data-method="${m}" style="cursor:pointer;display:inline-flex;align-items:center;gap:5px;padding:6px 12px;background:${bg};color:${fg};border:1px solid ${border};border-radius:4px;font-family:monospace;font-size:11px;font-weight:${isChecked?'600':'normal'};transition:background 0.1s">
                    <input type="radio" name="dlg-method" value="${m}" ${isChecked ? 'checked' : ''} style="width:13px;height:13px;margin:0;cursor:pointer;accent-color:#fff">
                    ${m}()
                </label>`;
        }).join('');

        const screenshot = opts.screenshot || null;
        const screenshotBlock = screenshot ? `
            <div style="margin-bottom:10px">
                <label style="display:block;color:#888;font-size:11px;margin-bottom:4px">&#128247; 截图预览:</label>
                <img src="${screenshot}" style="max-width:100%;max-height:120px;border:1px solid #444;border-radius:4px;background:#1a1a1a">
            </div>
        ` : '';

        const saveBlock = isEdit ? '' : `
                <div style="margin-bottom:10px;display:flex;align-items:center;gap:8px;padding-top:8px;border-top:1px dashed #333">
                    <label id="dlg-save-toggle" style="cursor:pointer;display:inline-flex;align-items:center;gap:8px;padding:6px 12px;background:#2a2a2a;border:1px solid #444;border-radius:4px;color:#bbb;font-size:11px;white-space:nowrap;user-select:none">
                        <input id="dlg-save-to-lib" type="checkbox" style="width:14px;height:14px;cursor:pointer;accent-color:#4caf50;margin:0">
                        <span>&#128190; 同时保存到元素库</span>
                    </label>
                    <input id="dlg-save-name" type="text" placeholder="库内元素名(可选)" style="flex:1;background:#3c3c3c;border:1px solid #555;color:#fff;border-radius:4px;padding:5px 8px;font-size:11px">
                </div>
        `;

        return `
            <div style="padding:10px 16px;background:#2d2d2d;border-bottom:1px solid #444;display:flex;justify-content:space-between;align-items:center">
                <span style="font-weight:bold;font-size:13px">${headerTitle}</span>
                <button id="dlg-cancel-x" style="background:none;border:none;color:#888;cursor:pointer;font-size:14px">&#10005;</button>
            </div>
            <div style="padding:8px 16px;background:#252526;border-bottom:1px solid #444;font-size:11px;color:#bbb;word-break:break-all">
                ${lockedLine}
            </div>
            <div style="flex:1;overflow-y:auto;padding:12px 16px">
                <div style="margin-bottom:10px">
                    <label style="display:block;color:#888;font-size:11px;margin-bottom:3px">元素名(可选)</label>
                    <input id="dlg-name" type="text" placeholder="如: 搜索框" style="width:100%;background:#3c3c3c;border:1px solid #555;color:#fff;border-radius:4px;padding:5px 8px;font-size:12px;box-sizing:border-box">
                </div>

                <div style="margin-bottom:10px">
                    <label style="display:block;color:#888;font-size:11px;margin-bottom:4px">定位 (locator):</label>
                    <div id="dlg-locator-list" style="background:#1a1a1a;border:1px solid #333;border-radius:4px;padding:4px 10px;max-height:200px;overflow-y:auto">
                        ${renderLocatorRadios(cands, selectedIdx, false)}
                    </div>
                </div>

                <div style="margin-bottom:10px">
                    <label style="display:block;color:#888;font-size:11px;margin-bottom:4px">method:</label>
                    <div style="display:flex;flex-wrap:wrap;gap:6px">${methodRadios}</div>
                </div>

                <div style="margin-bottom:10px">
                    <label style="display:block;color:#888;font-size:11px;margin-bottom:4px">action:</label>
                    <select id="dlg-action" style="background:#3c3c3c;border:1px solid #555;color:#ce9178;border-radius:4px;padding:5px 8px;font-size:12px;cursor:pointer">
                        ${actionOptions}
                    </select>
                    <div id="dlg-extra" style="margin-top:8px"></div>
                    <div style="margin-top:8px">
                        <label style="display:block;color:#888;font-size:11px;margin-bottom:3px">动作补充描述（可选）</label>
                        <input id="dlg-desc" type="text" placeholder="如: 小红书首页搜索按钮,点击展开搜索框" style="width:100%;background:#3c3c3c;border:1px solid #555;color:#fff;border-radius:4px;padding:5px 8px;font-size:12px;box-sizing:border-box">
                    </div>
                </div>

                ${screenshotBlock}

                ${saveBlock}

                <div>
                    <button disabled title="DrissionPage 高级语法构造器,v0.3 支持" style="background:#2a2a2a;border:1px dashed #444;color:#666;border-radius:4px;padding:4px 10px;font-size:11px;cursor:not-allowed">&#9999; 切换手动模式 (v0.3)</button>
                </div>
            </div>

            <div style="padding:10px 16px;background:#2d2d2d;border-top:1px solid #444;display:flex;justify-content:flex-end;gap:10px">
                <button id="dlg-cancel" style="background:#3c3c3c;border:none;color:#fff;border-radius:4px;padding:6px 16px;cursor:pointer">取消 (Esc)</button>
                <button id="dlg-confirm" style="background:#4a6a8a;border:none;color:#fff;border-radius:4px;padding:6px 16px;cursor:pointer">${isEdit ? '保存' : '确认'} (Ctrl+Enter)</button>
            </div>
        `;
    }

    function renderActionExtra(box, action) {
        const spec = ACTION_EXTRA[action];
        if (!spec) {
            box.innerHTML = '';
            return;
        }
        box.innerHTML = `
            <label style="display:block;color:#888;font-size:11px;margin-bottom:3px">${escapeHtml(spec.label)}:</label>
            <input id="dlg-extra-${spec.field}" data-field="${spec.field}" type="${spec.type}" value="${escapeHtml(spec.default)}"
                style="width:100%;background:#3c3c3c;border:1px solid #555;color:#fff;border-radius:4px;padding:5px 8px;font-size:12px;box-sizing:border-box">
        `;
        setTimeout(() => box.querySelector(`#dlg-extra-${spec.field}`)?.focus(), 0);
    }

    function collectActionExtra(dialogBox, action, desc) {
        switch (action) {
            case 'custom':
                return { description: desc || '(自定义,无描述)' };
            case 'click': case 'getText': case 'hover':
                return {};
            case 'input': {
                const v = dialogBox.querySelector('#dlg-extra-text')?.value ?? '';
                return { text: v };
            }
            case 'getAttr': {
                const v = (dialogBox.querySelector('#dlg-extra-attrName')?.value || '').trim();
                if (!v) { alert('属性名不能为空'); return null; }
                return { attrName: v };
            }
            case 'findWithin': {
                const v = (dialogBox.querySelector('#dlg-extra-subSelector')?.value || '').trim();
                if (!v) { alert('子元素 locator 不能为空'); return null; }
                return { subSelector: v };
            }
            case 'waitFor': {
                const v = parseFloat(dialogBox.querySelector('#dlg-extra-seconds')?.value);
                if (isNaN(v) || v <= 0) { alert('超时秒数无效'); return null; }
                return { seconds: v };
            }
            default:
                return {};
        }
    }

    function enterCaptureMode() {
        if (captureMode) return;
        captureMode = true;
        captureSticky = false;
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseleave', onMouseLeave);
        console.log('[操作编排器] 进入捕获模式');
    }

    function exitCaptureMode() {
        if (!captureMode) return;
        captureMode = false;
        captureSticky = false;
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseleave', onMouseLeave);
        console.log('[操作编排器] 退出捕获模式');
        highlightCurrentEl = null;
        currentHoverElement = null;
        clearHighlightCanvas();
        clearMatchHighlights();
        lockedElement = null;
        lockedLocator = '';
        lockedLocatorType = '';
        lockedCandidates = [];
        lockedSelector = '';
        lastHoveredEl = null;
        renderLocatorChooser();
    }


    async function persistLastUsed() {
        try {
            await chrome.storage.local.set({
                [STORAGE_KEY_LASTUSED]: JSON.stringify({ method: lastUsedMethod, action: lastUsedAction })
            });
        } catch (e) {}
    }

    async function loadLastUsed() {
        try {
            const res = await chrome.storage.local.get(STORAGE_KEY_LASTUSED);
            if (res[STORAGE_KEY_LASTUSED]) {
                const o = JSON.parse(res[STORAGE_KEY_LASTUSED]);
                lastUsedMethod = o.method || 'ele';
                lastUsedAction = o.action || 'click';
            }
        } catch (e) {}
    }

    function moveStep(stepId, direction) {
        const idx = actionSteps.findIndex(s => s.id === stepId);
        if (idx === -1) return;
        const newIdx = idx + direction;
        if (newIdx < 0 || newIdx >= actionSteps.length) return;
        [actionSteps[idx], actionSteps[newIdx]] = [actionSteps[newIdx], actionSteps[idx]];
        saveSteps();
        refreshStepsPanel();
    }

    // ==================== 导出 ====================
    async function exportAsJSON() {
        const name = prompt('给这个流程起个名字', '未命名流程');
        if (name === null) return;
        const exportData = {
            name: name,
            url: window.location.href,
            hostname: window.location.hostname,
            framework: 'DrissionPage',
            created: new Date().toLocaleString(),
            steps: actionSteps.map(s => ({
                action: s.action,
                element_name: s.element_name,
                method: s.method || 'ele',
                locator: s.locator || ('css:' + (s.selector || '')),
                locator_type: s.locator_type || 'css',
                selector_css: s.selector || '',
                candidates: s.candidates || [],
                extra: s.extra
            })),
            library: elementLibrary.map(item => ({
                name: item.name,
                method: item.method || 'ele',
                locator: item.locator || (item.css_selector ? 'css:' + item.css_selector : ''),
                locator_type: item.locator_type || 'css',
                tag: item.tag,
                text_preview: item.text_preview,
                page_url: item.page_url
            }))
        };
        const jsonStr = JSON.stringify(exportData, null, 2);
        await copyToClipboard(jsonStr);
        alert('流程已复制为 JSON 格式到剪贴板');
        return jsonStr;
    }

    function buildDpCall(step) {
        const m = step.method || 'ele';
        const loc = (step.locator || ('css:' + (step.selector || ''))).replace(/'/g, "\\'");
        return `tab.${m}('${loc}')`;
    }

    function exportAsNaturalLanguage() {
        if (actionSteps.length === 0) {
            alert('还没有任何操作步骤');
            return;
        }
        let nl = `需求: 自动化操作流程 - ${window.location.hostname}\n\n`;
        nl += `页面URL: ${window.location.href}\n`;
        nl += `使用的框架: DrissionPage (每步骤后括号内为定位语法,请严格照搬不要改写)\n`;
        nl += `约定: tab 是已连接的 ChromiumPage / SessionPage 对象\n\n`;
        nl += `操作步骤:\n`;

        actionSteps.forEach((step, idx) => {
            const n = idx + 1;
            const desc = step.element_name ? `「${step.element_name}」` : `定位为 ${step.locator || step.selector || '?'} 的元素`;
            const call = buildDpCall(step);
            switch (step.action) {
                case 'custom':
                    nl += `${n}. ${step.extra.description || '自定义操作'} [元素: ${desc}] -> ${call}\n`;
                    break;
                case 'click':
                    nl += `${n}. 点击 ${desc} -> ${call}.click()\n`;
                    break;
                case 'getText':
                    nl += `${n}. 获取 ${desc} 的文本 -> ${call}.text\n`;
                    break;
                case 'input': {
                    const txt = (step.extra.text || '').replace(/'/g, "\\'");
                    nl += `${n}. 在 ${desc} 中输入: "${step.extra.text || ''}" -> ${call}.input('${txt}')\n`;
                    break;
                }
                case 'getAttr':
                    nl += `${n}. 获取 ${desc} 的 ${step.extra.attrName || ''} 属性 -> ${call}.attr('${step.extra.attrName || ''}')\n`;
                    break;
                case 'hover':
                    nl += `${n}. 鼠标悬停 ${desc} -> ${call}.hover()\n`;
                    break;
                case 'findWithin': {
                    const sub = (step.extra.subSelector || '').replace(/'/g, "\\'");
                    nl += `${n}. 在 ${desc} 内查找子元素 -> ${call}.ele('${sub}')\n`;
                    break;
                }
                case 'waitFor': {
                    const loc = (step.locator || ('css:' + (step.selector || ''))).replace(/'/g, "\\'");
                    nl += `${n}. 等待 ${desc} 出现(最长 ${step.extra.seconds || 10} 秒) -> tab.wait.ele_displayed('${loc}', timeout=${step.extra.seconds || 10})\n`;
                    break;
                }
                default:
                    nl += `${n}. ${step.action} ${desc} -> ${call}\n`;
            }
        });
        nl += `\n请根据以上步骤生成完整的 DrissionPage Python 脚本:\n`;
        nl += `1. 用 ChromiumOptions 显式设置浏览器路径和用户数据目录后启动 ChromiumPage:\n`;
        nl += `\n`;
        nl += "```python\n";
        nl += `from DrissionPage import ChromiumPage, ChromiumOptions\n`;
        nl += `\n`;
        nl += `chrome_path = r'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'\n`;
        nl += `user_data_path = r'D:\\Chrome_Work'\n`;
        nl += `\n`;
        nl += `co = ChromiumOptions()\n`;
        nl += `co.set_browser_path(chrome_path)\n`;
        nl += `co.set_user_data_path(user_data_path)\n`;
        nl += `co.set_argument('--no-sandbox')\n`;
        nl += `co.set_argument('--disable-blink-features=AutomationControlled')\n`;
        nl += `tab = ChromiumPage(addr_or_opts=co)\n`;
        nl += `tab.get('${window.location.href}')\n`;
        nl += "```\n";
        nl += `\n`;
        nl += `2. 严格按上述定位语法,不要自行改写为 CSS 或 xpath\n`;
        nl += `3. 加随机延迟(random.uniform(0.5, 1.5))模拟人类操作\n`;
        nl += `4. 加 try/except 错误处理,关键步骤打印日志\n`;
        nl += `5. eles/s_eles 返回列表时遍历处理\n`;
        nl += `6. 不要写 tab.quit(),让 Chrome 保持运行以便用户继续观察\n`;
        copyToClipboard(nl);
        alert('自然语言描述已复制到剪贴板');
        return nl;
    }

    async function copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            showToast('已复制到剪贴板');
        } catch (e) {
            // 降级：创建临时 textarea
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
            showToast('已复制到剪贴板');
        }
    }

    function showToast(message) {
        let toast = document.querySelector('#orchestrator-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'orchestrator-toast';
            toast.style.cssText = `
                position: fixed; bottom: 80px; right: 20px;
                background: #4caf50; color: white;
                padding: 8px 16px; border-radius: 4px;
                font-family: monospace; font-size: 12px;
                z-index: 2147483647; box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                transition: opacity 0.3s; pointer-events: none;
            `;
            document.body.appendChild(toast);
        }
        toast.textContent = message;
        toast.style.opacity = '1';
        setTimeout(() => { toast.style.opacity = '0'; }, 2000);
    }

    // ==================== 鼠标高亮 ====================
    function isGhostElement(el) {
        if (!el || el.nodeType !== Node.ELEMENT_NODE) return false;
        const style = getComputedStyle(el);
        return style.display === 'none'
            || style.visibility === 'hidden';
    }

    // 扩展自身注入的面板/对话框/高亮/toast 均以 orch- 或 orchestrator- 为 id 前缀
    function isExtensionElement(el) {
        if (!el || el.nodeType !== Node.ELEMENT_NODE) return false;
        let cur = el;
        while (cur && cur !== document.body && cur !== document.documentElement) {
            const id = cur.id || '';
            if (id.startsWith('orch-') || id.startsWith('orchestrator-')) return true;
            cur = cur.parentElement;
        }
        return false;
    }

    function resolveTargetFromPoint() {
        // 返回当前 hoverStack[stackIndex],不做额外处理
        if (!hoverStack.length) return null;
        return hoverStack[stackIndex] || null;
    }

    function onMouseMove(e) {
        if (!captureMode) return;
        if (dialogOpen) return;

        // 鼠标位置变化时重新获取 stack
        const moved = (Math.abs(e.clientX - lastHoverX) > 2 || Math.abs(e.clientY - lastHoverY) > 2);
        if (moved || !hoverStack.length) {
            lastHoverX = e.clientX;
            lastHoverY = e.clientY;
            stackIndex = 0;
            let rawStack;
            try {
                rawStack = document.elementsFromPoint(e.clientX, e.clientY);
            } catch (err) {
                rawStack = [];
            }
            // 过滤 ghost 和 body/html,保留有效元素
            hoverStack = [];
            for (const el of rawStack) {
                if (isGhostElement(el)) continue;
                if (el === document.body || el === document.documentElement) continue;
                // 跳过面积=0
                const r = el.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) continue;
                hoverStack.push(el);
            }
            if (!hoverStack.length && rawStack.length) {
                hoverStack = rawStack.filter(el => el !== document.body && el !== document.documentElement);
            }
        }

        let target = resolveTargetFromPoint();
        if (!target) return;

        const inPanel = mainPanel && mainPanel.contains(target);
        const inLib = libraryPanel && libraryPanel.contains(target);
        const inDialog = document.getElementById('orch-capture-dialog') && document.getElementById('orch-capture-dialog').contains(target);
        if (inPanel || inLib || inDialog) return;

        // Sticky 退出判定
        if (captureSticky && !altPhysicallyDown && lockedElement
            && target !== lockedElement && !lockedElement.contains(target)) {
            exitCaptureMode();
            return;
        }

        const sameElement = (target === lastHoveredEl);
        if (sameElement) {
            const now = performance.now();
            if (now - lastMouseMoveTs < 80) return;
            lastMouseMoveTs = now;
        } else {
            lastHoveredEl = target;
            lastMouseMoveTs = performance.now();
        }

        currentHoverElement = target;
        highlightCurrentEl = target;
        redrawHighlights();

        // 生成候选
        const cands = generateLocators(target);
        currentCandidates = cands;
        lockedCandidates = cands;
        selectedLocatorIndex = 0;
        lockedElement = target;
        if (cands.length > 0) {
            lockedLocator = cands[0].syntax;
            lockedLocatorType = cands[0].type;
            const cssEquiv = convertToCssForTest(cands[0].syntax, cands[0].type);
            lockedSelector = cssEquiv || getOldCssSelector(target);
            currentHoverSelector = lockedSelector;
        } else {
            lockedLocator = '';
            lockedLocatorType = '';
            lockedSelector = '';
            currentHoverSelector = '';
        }

        if (!sameElement || moved) renderLocatorChooser();
    }

    function onMouseLeave() {
        highlightCurrentEl = null;
        currentHoverElement = null;
        clearHighlightCanvas();
        lockedElement = null;
        lockedSelector = '';
        lockedLocator = '';
        lockedLocatorType = '';
        lockedCandidates = [];
        currentCandidates = [];
        clearMatchHighlights();
        lastHoveredEl = null;
        renderLocatorChooser();
    }

    function clearMatchHighlights() {
        highlightMatchEls = [];
        redrawHighlights();
    }

    function highlightMatches(syntax, type) {
        clearMatchHighlights();
        const css = convertToCssForTest(syntax, type);
        if (!css) return -1;  // 无法验证
        let list;
        try {
            list = document.querySelectorAll(css);
        } catch (e) {
            return -1;
        }
        const total = list.length;
        const limit = Math.min(total, 50);
        for (let i = 0; i < limit; i++) {
            highlightMatchEls.push(list[i]);
        }
        redrawHighlights();
        return total;
    }

    function renderLocatorChooser() {
        // v0.2:chooser radio 列表已搬到录入对话框;此函数仅更新顶部简略锁定行
        const info = document.getElementById('orch-current-info');
        if (!info) return;
        if (!lockedElement || !lockedCandidates || lockedCandidates.length === 0) {
            const hint = captureMode
                ? '<span style="color:#888">&#128205; 捕获中 · hover 元素查看候选</span>'
                : '<span style="color:#888">&#128205; 按住 Alt + 鼠标 hover 进入捕获模式</span>';
            if (info.innerHTML !== hint) info.innerHTML = hint;
            return;
        }
        const tag = lockedElement.tagName.toLowerCase();
        const text = (lockedElement.innerText || '').slice(0, 40).replace(/\s+/g, ' ');
        const top = lockedCandidates[0];
        const topSyntax = top ? top.syntax : '';
        const totalCands = lockedCandidates.length;
        const hasChildren = lockedElement && lockedElement.children && lockedElement.children.length > 0;
        const hasSiblings = lockedElement && lockedElement.parentElement && lockedElement.parentElement.children.length > 1;
        const hasParent = lockedElement && lockedElement.parentElement && lockedElement.parentElement !== document.documentElement;
        const stackHint = (hasChildren ? ` <span style="color:#ff9800">Alt+Q↓</span>` : '')
            + (hasSiblings ? ` <span style="color:#ff9800">Alt+W→</span>` : '')
            + (hasParent ? ` <span style="color:#ff9800">Alt+E↑</span>` : '');
        // 列出所有 attribute(框架可能注入很多 data-*,加滚动)
        const attrs = Array.from(lockedElement.attributes || []);
        const attrsHtml = attrs.length
            ? attrs.map(a => `<span style="color:#9cdcfe">${escapeHtml(a.name)}</span><span style="color:#888">=</span><span style="color:#ce9178">"${escapeHtml(a.value)}"</span>`).join(' ')
            : '<span style="color:#888">(无属性)</span>';
        info.innerHTML = `
            <div><span style="color:#4caf50">&#128274; 锁定:</span> <span style="color:#ce9178">&lt;${tag}&gt;</span> <span style="color:#999">${escapeHtml(text)}</span>${stackHint}</div>
            <div style="margin-top:3px;color:#888;font-size:10px">首选: <span style="color:#ce9178;font-family:monospace">${escapeHtml(topSyntax)}</span> · 共 ${totalCands} 候选 · Alt+click / Alt+1 录入 · Alt+Q 子 · Alt+W 兄弟 · Alt+E 父</div>
            <div style="margin-top:4px;font-size:10px;line-height:1.5;max-height:70px;overflow:auto;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:3px;padding:3px 5px;word-break:break-all">${attrsHtml}</div>
        `;
    }

    function setSelectedLocator(idx) {
        if (!lockedCandidates[idx]) return;
        selectedLocatorIndex = idx;
        const c = lockedCandidates[idx];
        lockedLocator = c.syntax;
        lockedLocatorType = c.type;
        const cssEquiv = convertToCssForTest(c.syntax, c.type);
        lockedSelector = cssEquiv || lockedSelector;
        highlightMatches(c.syntax, c.type);
    }

    // ==================== Canvas overlay 高亮层(v0.3) ====================
    function initHighlightCanvas() {
        if (highlightHost) return;
        highlightHost = document.createElement('div');
        highlightHost.id = 'orch-highlight-host';
        highlightHost.style.cssText = 'all:initial;position:fixed;top:0;left:0;width:100%;height:100%;z-index:2147483647;pointer-events:none;';
        highlightShadow = highlightHost.attachShadow({mode: 'open'});
        highlightShadow.innerHTML = `
            <style>
                :host { all: initial; }
                canvas { display: block; }
            </style>
            <canvas id="orch-hl-canvas" style="position:fixed;top:0;left:0;pointer-events:none;"></canvas>
        `;
        document.body.appendChild(highlightHost);
        highlightCanvas = highlightShadow.getElementById('orch-hl-canvas');
        highlightCtx = highlightCanvas.getContext('2d');
        resizeHighlightCanvas();
        window.addEventListener('resize', resizeHighlightCanvas);
        window.addEventListener('scroll', onHighlightScrollResize, true);
    }
    function resizeHighlightCanvas() {
        if (!highlightCanvas) return;
        highlightCanvas.width = window.innerWidth;
        highlightCanvas.height = window.innerHeight;
        highlightCanvas.style.width = window.innerWidth + 'px';
        highlightCanvas.style.height = window.innerHeight + 'px';
    }
    function onHighlightScrollResize() {
        if (!captureMode) return;
        resizeHighlightCanvas();
        redrawHighlights();
    }
    function redrawHighlights() {
        clearHighlightCanvas();
        if (highlightMatchEls.length > 0) {
            for (const el of highlightMatchEls) drawElementBox(el, 'match');
        } else if (highlightCurrentEl) {
            drawElementBox(highlightCurrentEl, 'single');
        }
    }
    function clearHighlightCanvas() {
        if (!highlightCtx || !highlightCanvas) return;
        highlightCtx.clearRect(0, 0, highlightCanvas.width, highlightCanvas.height);
    }
    function drawElementBox(el, style) {
        if (!highlightCtx || !el || !document.body.contains(el)) return;
        const rect = el.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        if (style === 'single') {
            // 主高亮:红色实线框 + 半透明填充 + label
            highlightCtx.save();
            highlightCtx.strokeStyle = '#ff4444';
            highlightCtx.lineWidth = 2 * dpr;
            highlightCtx.fillStyle = 'rgba(255, 68, 68, 0.08)';
            highlightCtx.fillRect(rect.left * dpr, rect.top * dpr, rect.width * dpr, rect.height * dpr);
            highlightCtx.strokeRect(rect.left * dpr, rect.top * dpr, rect.width * dpr, rect.height * dpr);
            // 左上角 tag label
            const tag = el.tagName.toLowerCase();
            let cls = '';
            if (el.className && typeof el.className === 'string' && el.className.trim()) {
                const parts = el.className.trim().split(/\s+/).filter(Boolean);
                cls = '.' + (parts.length > 3 ? parts.slice(0, 3).join('.') + '..' : parts.join('.'));
            }
            const text = tag + (el.id ? '#' + el.id : '') + cls;
            highlightCtx.font = (11 * dpr) + 'px monospace';
            const tw = highlightCtx.measureText(text).width;
            const pad = 3 * dpr;
            highlightCtx.fillStyle = '#ff4444';
            highlightCtx.fillRect((rect.left + 2) * dpr, (rect.top - 16) * dpr, tw + pad * 2, 14 * dpr);
            highlightCtx.fillStyle = '#fff';
            highlightCtx.fillText(text, (rect.left + 2 + pad) * dpr, (rect.top - 5) * dpr);
            highlightCtx.restore();
        } else {
            // 多匹配高亮:橙色虚线框 + 淡填充
            highlightCtx.save();
            highlightCtx.strokeStyle = '#ffa500';
            highlightCtx.lineWidth = 1.5 * dpr;
            highlightCtx.setLineDash([4 * dpr, 3 * dpr]);
            highlightCtx.fillStyle = 'rgba(255, 165, 0, 0.06)';
            highlightCtx.fillRect(rect.left * dpr, rect.top * dpr, rect.width * dpr, rect.height * dpr);
            highlightCtx.strokeRect(rect.left * dpr, rect.top * dpr, rect.width * dpr, rect.height * dpr);
            highlightCtx.restore();
        }
    }

    // ==================== 深度 hit testing:穿透 iframe / shadow DOM ====================
    function deepElementsFromPoint(x, y, doc) {
        doc = doc || document;
        let stack;
        try {
            stack = doc.elementsFromPoint(x, y);
        } catch (e) {
            return [];
        }
        if (!stack || stack.length === 0) return [];

        const result = [];
        for (const el of stack) {
            result.push(el);
            // iframe 穿透:坐标转换到 iframe 内部坐标系
            if (el.tagName === 'IFRAME') {
                try {
                    const iframeDoc = el.contentDocument || el.contentWindow?.document;
                    if (iframeDoc) {
                        const iframeRect = el.getBoundingClientRect();
                        const innerX = x - iframeRect.left;
                        const innerY = y - iframeRect.top;
                        const innerStack = deepElementsFromPoint(innerX, innerY, iframeDoc);
                        result.push(...innerStack);
                    }
                } catch (e) { /* cross-origin */ }
            }
            // shadow DOM 穿透:shadowRoot 与宿主共享坐标系
            if (el.shadowRoot) {
                const innerStack = deepElementsFromPoint(x, y, el.shadowRoot);
                result.push(...innerStack);
            }
        }
        return result;
    }

    function _debugLabel(el) {
        if (!el || !el.tagName) return String(el);
        const t = el.tagName.toLowerCase();
        const id = el.id ? '#' + el.id : '';
        const cls = el.className && typeof el.className === 'string' ? '.' + el.className.split(/\s+/).filter(Boolean).slice(0, 2).join('.') : '';
        return t + id + cls;
    }

    function injectStyles() {
        if (document.getElementById('orch-style')) return;
        const style = document.createElement('style');
        style.id = 'orch-style';
        style.textContent = `
            .orch-highlight {
                outline: 3px solid #ff4444 !important;
                background-color: rgba(255, 68, 68, 0.08) !important;
                cursor: crosshair !important;
            }
            .orch-highlight-multi {
                outline: 2px dashed #ffa500 !important;
                background-color: rgba(255, 165, 0, 0.06) !important;
            }
        `;
        document.head.appendChild(style);
    }

    // ==================== 主面板 ====================
    function createMainPanel() {
        initHighlightCanvas();
        if (mainPanel) mainPanel.remove();

        mainPanel = document.createElement('div');
        mainPanel.id = 'orchestrator-panel';
        mainPanel.style.cssText = `
            position: fixed; top: 20px; right: 20px;
            width: 400px; max-height: 85vh;
            background: #1e1e1e; color: #d4d4d4;
            font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
            font-size: 12px; border-radius: 8px;
            z-index: 2147483646; box-shadow: 0 4px 20px rgba(0,0,0,0.5);
            display: flex; flex-direction: column;
            overflow: hidden; border: 1px solid #444;
        `;

        // 头部
        const header = document.createElement('div');
        header.style.cssText = `
            padding: 10px 15px; background: #2d2d2d;
            border-bottom: 1px solid #444;
            display: flex; justify-content: space-between;
            align-items: center; cursor: move; user-select: none;
        `;
        header.innerHTML = `
            <span style="font-weight:bold;font-size:13px">&#127909; 操作编排器</span>
            <div>
                <button id="orch-toggle-lib" style="background:#3c3c3c;border:none;color:#fff;border-radius:4px;padding:4px 8px;margin-right:5px;cursor:pointer;font-size:11px">&#128218; 元素库</button>
                <button id="orch-minimize" style="background:#5a5a2a;border:none;color:#fff;border-radius:4px;padding:4px 8px;margin-right:5px;cursor:pointer;font-size:11px">&#8212;</button>
                <button id="orch-close" style="background:#5a2a2a;border:none;color:#fff;border-radius:4px;padding:4px 8px;cursor:pointer;font-size:11px">&#10005;</button>
            </div>
        `;

        // 当前元素 简略锁定提示行
        const currentInfo = document.createElement('div');
        currentInfo.id = 'orch-current-info';
        currentInfo.style.cssText = `
            padding: 8px 12px; background: #252526;
            border-bottom: 1px solid #444; font-size: 11px;
            word-break: break-all; min-height: 32px;
        `;
        currentInfo.innerHTML = '<span style="color:#888">&#128205; 按住 Alt + 鼠标 hover 进入捕获模式</span>';

        // 服务端配置区域
        const configArea = document.createElement('div');
        configArea.style.cssText = `
            padding: 6px 12px; background: #1e1e1e;
            border-bottom: 1px solid #333; font-size: 11px;
        `;
        configArea.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;cursor:pointer;" id="orch-config-toggle">
                <span style="color:#888">&#9881; 服务端配置</span>
                <span id="orch-config-arrow" style="color:#666">&#9654;</span>
            </div>
            <div id="orch-config-body" style="display:none;margin-top:6px;">
                <div style="margin-bottom:4px;">
                    <label style="color:#888;display:block;margin-bottom:2px;">后端地址</label>
                    <input id="orch-config-url" type="text" value="${backendUrl}" placeholder="http://localhost:8000"
                           style="width:100%;background:#333;border:1px solid #555;color:#fff;padding:3px 6px;border-radius:3px;font-size:11px;font-family:monospace;box-sizing:border-box;">
                </div>
                <div style="margin-bottom:4px;">
                    <label style="color:#888;display:block;margin-bottom:2px;">Token</label>
                    <input id="orch-config-token" type="text" value="${authToken || ''}" placeholder="JWT token"
                           style="width:100%;background:#333;border:1px solid #555;color:#fff;padding:3px 6px;border-radius:3px;font-size:11px;font-family:monospace;box-sizing:border-box;">
                </div>
                <div style="display:flex;gap:6px;">
                    <button id="orch-config-save" style="flex:1;background:#4a8a4a;border:none;color:#fff;border-radius:3px;padding:3px 0;cursor:pointer;font-size:11px;">保存</button>
                    <button id="orch-config-test" style="flex:1;background:#4a6a8a;border:none;color:#fff;border-radius:3px;padding:3px 0;cursor:pointer;font-size:11px;">测试连接</button>
                </div>
                <div id="orch-config-status" style="margin-top:4px;color:#888;font-size:10px;"></div>
            </div>
        `;

        // 步骤列表头部
        const stepsHeader = document.createElement('div');
        stepsHeader.style.cssText = `
            padding: 8px 12px; background: #2d2d2d;
            border-bottom: 1px solid #444;
            display: flex; justify-content: space-between; align-items: center;
        `;
        stepsHeader.innerHTML = `
            <span>&#128203; 操作步骤 (${actionSteps.length})</span>
            <div>
                <button id="orch-clear-steps" style="background:#5a2a2a;border:none;color:#ff8888;border-radius:4px;padding:2px 8px;margin-right:5px;cursor:pointer;font-size:11px">清空</button>
                <button id="orch-export-json" style="background:#4a6a8a;border:none;color:#fff;border-radius:4px;padding:2px 8px;margin-right:5px;cursor:pointer;font-size:11px">&#128203; JSON</button>
                <button id="orch-export-nl" style="background:#6a4a8a;border:none;color:#fff;border-radius:4px;padding:2px 8px;margin-right:5px;cursor:pointer;font-size:11px">&#128221; 自然语言</button>
                <button id="orch-run-wf" style="background:#4a8a4a;border:none;color:#fff;border-radius:4px;padding:2px 8px;margin-right:5px;cursor:pointer;font-size:11px">&#9654; 执行</button>
            </div>
        `;

        // 步骤列表
        const stepsList = document.createElement('div');
        stepsList.id = 'orch-steps-list';
        stepsList.style.cssText = `
            flex: 1; overflow-y: auto; max-height: 300px; padding: 5px 0;
        `;

        mainPanel.appendChild(header);
        mainPanel.appendChild(currentInfo);
        mainPanel.appendChild(configArea);
        mainPanel.appendChild(stepsHeader);
        mainPanel.appendChild(stepsList);
        document.body.appendChild(mainPanel);

        // 配置区域事件
        const configToggle = document.getElementById('orch-config-toggle');
        const configBody = document.getElementById('orch-config-body');
        const configArrow = document.getElementById('orch-config-arrow');
        configToggle.addEventListener('click', () => {
            const show = configBody.style.display === 'none';
            configBody.style.display = show ? 'block' : 'none';
            configArrow.textContent = show ? '▼' : '▶';
        });
        document.getElementById('orch-config-save').addEventListener('click', async () => {
            backendUrl = document.getElementById('orch-config-url').value.trim() || backendUrl;
            authToken = document.getElementById('orch-config-token').value.trim() || null;
            await saveConfig();
            document.getElementById('orch-config-status').textContent = '已保存';
            setTimeout(() => { document.getElementById('orch-config-status').textContent = ''; }, 2000);
        });
        document.getElementById('orch-config-test').addEventListener('click', async () => {
            const url = document.getElementById('orch-config-url').value.trim() || backendUrl;
            const token = document.getElementById('orch-config-token').value.trim() || authToken;
            const statusEl = document.getElementById('orch-config-status');
            try {
                const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
                const res = await _fetchViaBackground(`${url}/api/elements/hosts`, 'GET', headers);
                if (res.ok) {
                    statusEl.textContent = '✅ 连接成功';
                    statusEl.style.color = '#4caf50';
                } else if (res.status === 401) {
                    statusEl.textContent = '❌ Token 无效(401)';
                    statusEl.style.color = '#ff4444';
                } else {
                    statusEl.textContent = `❌ 错误 ${res.status}`;
                    statusEl.style.color = '#ff4444';
                }
            } catch (e) {
                statusEl.textContent = '❌ 连接失败';
                statusEl.style.color = '#ff4444';
            }
            setTimeout(() => { statusEl.textContent = ''; statusEl.style.color = '#888'; }, 3000);
        });

        // 拖拽
        let isDragging = false;
        let dragOffset = { x: 0, y: 0 };
        header.addEventListener('mousedown', (e) => {
            if (e.target.tagName === 'BUTTON') return;
            isDragging = true;
            dragOffset.x = e.clientX - mainPanel.offsetLeft;
            dragOffset.y = e.clientY - mainPanel.offsetTop;
        });
        document.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            mainPanel.style.left = (e.clientX - dragOffset.x) + 'px';
            mainPanel.style.top = (e.clientY - dragOffset.y) + 'px';
            mainPanel.style.right = 'auto';
        });
        document.addEventListener('mouseup', () => { isDragging = false; });

        // 清空步骤
        document.getElementById('orch-clear-steps').addEventListener('click', () => {
            if (confirm('清空所有步骤？')) {
                actionSteps = [];
                saveSteps();
                refreshStepsPanel();
            }
        });

        // 导出
        document.getElementById('orch-export-json').addEventListener('click', exportAsJSON);
        document.getElementById('orch-export-nl').addEventListener('click', exportAsNaturalLanguage);
        document.getElementById('orch-run-wf').addEventListener('click', async () => {
            if (!currentWorkflowId) {
                showToast('请先在后端配置工作流');
                return;
            }
            showToast('正在拉取工作流节点...');
            const nodes = await fetchWorkflowNodes();
            if (!nodes.length) {
                showToast('工作流无节点或拉取失败');
                return;
            }
            showToast(`开始执行 ${nodes.length} 个节点...`);
            await runWorkflowNodes(nodes);
        });

        // 关闭
        document.getElementById('orch-close').addEventListener('click', hide);

        // 最小化（隐藏但保留注入状态）
        document.getElementById('orch-minimize').addEventListener('click', () => {
            mainPanel.style.display = 'none';
        });

        // 元素库按钮
        document.getElementById('orch-toggle-lib').addEventListener('click', () => {
            if (libraryPanel && libraryPanel.style.display !== 'none') {
                libraryPanel.remove();
                libraryPanel = null;
            } else {
                createLibraryPanel();
            }
        });

        // mousemove/mouseleave 由 enterCaptureMode 注册(Alt 按下才进入捕获)

        // 快捷键提示栏
        const shortcutBar = document.createElement('div');
        shortcutBar.style.cssText = `
            padding: 5px 10px; background: #1a1a1a;
            border-top: 1px solid #333; font-size: 10px;
            color: #777; text-align: center; line-height: 1.6;
        `;
        shortcutBar.innerHTML = `
            <span style="color:#ce9178">按住 Alt</span> 进入捕获模式 · <span style="color:#ce9178">Alt+click / Alt+2</span> 录入步骤 |
            <span style="color:#ce9178">Alt+1</span>保存到元素库 · <span style="color:#ce9178">Alt+Q</span>子 · <span style="color:#ce9178">Alt+W</span>兄弟 · <span style="color:#ce9178">Alt+E</span>父 · <span style="color:#ce9178">Alt+N</span>导出 NL · <span style="color:#ce9178">Alt+J</span>导出 JSON · <span style="color:#ce9178">Esc</span>关闭面板
        `;
        mainPanel.appendChild(shortcutBar);

        // 绑定键盘快捷键
        document.addEventListener('keydown', onKeyDown);
        document.addEventListener('keyup', onKeyUp);
        document.addEventListener('click', onClick, true);

        refreshStepsPanel();
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function changeStepMethod(stepId, newMethod) {
        const s = actionSteps.find(s => s.id === stepId);
        if (!s) return;
        s.method = newMethod;
        saveSteps();
        refreshStepsPanel();
    }

    function editStep(stepId) {
        const s = actionSteps.find(s => s.id === stepId);
        if (!s) return;
        openCaptureDialog(null, s.candidates || [], { editStepId: stepId });
    }

    function refreshStepsPanel() {
        const list = document.getElementById('orch-steps-list');
        if (!list) return;
        const header = list.previousElementSibling;
        if (header) {
            const title = header.querySelector('span');
            if (title) title.textContent = `📋 操作步骤 (${actionSteps.length})`;
        }

        if (actionSteps.length === 0) {
            list.innerHTML = '<div style="padding:20px;text-align:center;color:#888">暂无步骤<br>按住 Alt + 点击页面元素 录入第一步</div>';
            return;
        }

        list.innerHTML = '';
        actionSteps.forEach((step, idx) => {
            const icons = {
                custom: '✏️', click: '🖱',
                getText: '📄', input: '⌨',
                getAttr: '🏷️', hover: '✋',
                findWithin: '🔍', waitFor: '⏱'
            };
            const icon = icons[step.action] || '📌';
            const method = step.method || 'ele';
            const locator = step.locator || ('css:' + (step.selector || ''));

            let summary = `${idx + 1}. ${icon} ${step.action}`;
            if (step.action === 'custom' && step.extra.description) {
                summary += ` "${step.extra.description.slice(0, 60)}"`;
            } else {
                if (step.element_name) summary += ` [${step.element_name}]`;
                if (step.extra.text) summary += ` "${step.extra.text}"`;
                if (step.extra.attrName) summary += ` attr=${step.extra.attrName}`;
                if (step.extra.subSelector) summary += ` find=${step.extra.subSelector}`;
                if (step.extra.seconds) summary += ` ${step.extra.seconds}s`;
            }

            const methodOpts = ['ele', 'eles', 's_ele', 's_eles']
                .map(m => `<option value="${m}" ${m === method ? 'selected' : ''}>${m}()</option>`)
                .join('');

            const div = document.createElement('div');
            div.style.cssText = 'padding: 8px 12px; border-bottom: 1px solid #333;';
            div.innerHTML = `
                <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px">
                    <div style="flex:1;word-break:break-word">${escapeHtml(summary)}</div>
                    <select class="orch-step-method" data-id="${step.id}" style="background:#3c3c3c;border:1px solid #555;color:#ce9178;border-radius:3px;padding:1px 4px;margin:0 6px;font-size:10px;cursor:pointer">${methodOpts}</select>
                    <button class="orch-edit-step" data-id="${step.id}" title="编辑步骤" style="background:#3c4a6a;border:none;color:#ce9178;border-radius:3px;padding:2px 6px;margin:0 1px;cursor:pointer">&#9999;</button>
                    <button class="orch-move-up" data-id="${step.id}" title="上移" style="background:#3c3c3c;border:none;color:#888;border-radius:3px;padding:2px 6px;margin:0 1px;cursor:pointer">&#8593;</button>
                    <button class="orch-move-down" data-id="${step.id}" title="下移" style="background:#3c3c3c;border:none;color:#888;border-radius:3px;padding:2px 6px;margin:0 1px;cursor:pointer">&#8595;</button>
                    <button class="orch-delete-step" data-id="${step.id}" title="删除" style="background:#5a2a2a;border:none;color:#ff8888;border-radius:3px;padding:2px 6px;margin:0 1px;cursor:pointer">&#128465;</button>
                </div>
                <div style="color:#888;font-family:monospace;font-size:10px;word-break:break-all;padding-left:20px;margin-top:2px">${escapeHtml(locator)}</div>
            `;
            list.appendChild(div);
        });

        list.querySelectorAll('.orch-step-method').forEach(sel => {
            sel.addEventListener('change', (e) => {
                const id = parseFloat(e.currentTarget.getAttribute('data-id'));
                changeStepMethod(id, e.currentTarget.value);
            });
        });
        list.querySelectorAll('.orch-edit-step').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const id = parseFloat(e.currentTarget.getAttribute('data-id'));
                editStep(id);
            });
        });
        list.querySelectorAll('.orch-move-up').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const id = parseFloat(e.currentTarget.getAttribute('data-id'));
                moveStep(id, -1);
            });
        });
        list.querySelectorAll('.orch-move-down').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const id = parseFloat(e.currentTarget.getAttribute('data-id'));
                moveStep(id, 1);
            });
        });
        list.querySelectorAll('.orch-delete-step').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const id = parseFloat(e.currentTarget.getAttribute('data-id'));
                deleteStep(id);
            });
        });
    }

    function createLibraryPanel() {
        if (libraryPanel) libraryPanel.remove();

        libraryPanel = document.createElement('div');
        libraryPanel.id = 'orchestrator-library';
        libraryPanel.style.cssText = `
            position: fixed; top: 100px; left: 20px;
            width: 360px; max-height: 400px;
            background: #1e1e1e; color: #d4d4d4;
            font-family: monospace; font-size: 12px;
            border-radius: 8px; z-index: 2147483646;
            box-shadow: 0 4px 20px rgba(0,0,0,0.5);
            display: flex; flex-direction: column;
            border: 1px solid #444;
        `;

        const header = document.createElement('div');
        header.style.cssText = `
            padding: 8px 12px; background: #2d2d2d;
            border-bottom: 1px solid #444;
            display: flex; justify-content: space-between; align-items: center;
        `;
        header.innerHTML = `<span>&#128218; 元素库 (${elementLibrary.length})</span><button id="lib-close" style="background:none;border:none;color:#888;cursor:pointer;font-size:14px">&#10005;</button>`;

        const list = document.createElement('div');
        list.style.cssText = 'overflow-y: auto; flex:1; padding: 5px 0;';

        if (elementLibrary.length === 0) {
            list.innerHTML = '<div style="padding:20px;text-align:center;color:#888">暂无保存的元素，悬浮鼠标后点"保存到库"</div>';
        } else {
            elementLibrary.forEach(item => {
                const itemDiv = document.createElement('div');
                itemDiv.style.cssText = 'padding: 8px 12px; border-bottom: 1px solid #333;';
                const locator = item.locator || (item.css_selector ? 'css:' + item.css_selector : '');
                const locType = item.locator_type || 'css';
                const method = item.method || 'ele';
                itemDiv.innerHTML = `
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <span style="color:#ff6b6b;font-weight:bold">&#128230; ${escapeHtml(item.name)} <span style="color:#999;font-size:10px;font-weight:normal">[${escapeHtml(locType)} / ${escapeHtml(method)}]</span></span>
                        <div>
                            <button class="lib-use" data-id="${item.id}" style="background:#3c3c3c;border:none;color:#ce9178;border-radius:3px;padding:2px 6px;cursor:pointer;font-size:11px">使用</button>
                            <button class="lib-copy" data-id="${item.id}" style="background:#3c3c3c;border:none;color:#ce9178;border-radius:3px;padding:2px 6px;margin-left:4px;cursor:pointer;font-size:11px">复制</button>
                            <button class="lib-delete" data-id="${item.id}" style="background:#5a2a2a;border:none;color:#ff8888;border-radius:3px;padding:2px 6px;margin-left:4px;cursor:pointer;font-size:11px">删除</button>
                        </div>
                    </div>
                    <div style="font-size:10px;color:#888;word-break:break-all;margin-top:2px;font-family:monospace">${escapeHtml(locator)}</div>
                    <div style="font-size:10px;color:#6a9955">${escapeHtml(item.text_preview || '')}</div>
                `;
                list.appendChild(itemDiv);
            });
        }

        libraryPanel.appendChild(header);
        libraryPanel.appendChild(list);
        document.body.appendChild(libraryPanel);

        document.getElementById('lib-close').addEventListener('click', () => {
            libraryPanel.remove();
            libraryPanel = null;
        });

        const findItem = (id) => elementLibrary.find(i => i.id === id);

        list.querySelectorAll('.lib-use').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const item = findItem(parseInt(btn.getAttribute('data-id')));
                if (!item) return;
                const locator = item.locator || (item.css_selector ? 'css:' + item.css_selector : '');
                lockedLocator = locator;
                lockedLocatorType = item.locator_type || 'css';
                currentHoverSelector = locator;
                showToast('已加载: ' + locator.slice(0, 50));
            });
        });

        list.querySelectorAll('.lib-copy').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const item = findItem(parseInt(btn.getAttribute('data-id')));
                if (!item) return;
                const locator = item.locator || (item.css_selector ? 'css:' + item.css_selector : '');
                copyToClipboard(locator);
            });
        });

        list.querySelectorAll('.lib-delete').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const id = parseInt(btn.getAttribute('data-id'));
                elementLibrary = elementLibrary.filter(item => item.id !== id);
                await saveLibrary();
                createLibraryPanel();
                showToast('已删除元素');
            });
        });
    }

    // ==================== 显示/隐藏控制 ====================
    async function show(opts) {
        if (isVisible) {
            if (mainPanel) mainPanel.style.display = 'flex';
            return;
        }
        isVisible = true;
        await loadConfig();
        if (opts) {
            if (opts.backendUrl) backendUrl = opts.backendUrl;
            if (opts.workflowId) currentWorkflowId = opts.workflowId;
        }
        injectStyles();
        await loadLibrary();
        await loadSteps();
        await loadLastUsed();
        createMainPanel();
        console.log('[操作编排器] 面板已显示, workflowId:', currentWorkflowId);
    }

    function hide() {
        isVisible = false;
        if (captureMode) exitCaptureMode();
        altPhysicallyDown = false;
        if (mainPanel) {
            mainPanel.remove();
            mainPanel = null;
        }
        if (libraryPanel) {
            libraryPanel.remove();
            libraryPanel = null;
        }
        if (updateInterval) {
            clearInterval(updateInterval);
            updateInterval = null;
        }
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseleave', onMouseLeave);
        document.removeEventListener('keydown', onKeyDown);
        document.removeEventListener('keyup', onKeyUp);
        document.removeEventListener('click', onClick, true);
        highlightCurrentEl = null;
        currentHoverElement = null;
        clearHighlightCanvas();
        lockedElement = null;
        lockedSelector = '';
        lockedLocator = '';
        lockedLocatorType = '';
        lockedCandidates = [];
        currentCandidates = [];
        clearMatchHighlights();
        console.log('[操作编排器] 面板已隐藏');
    }

    function toggle(opts) {
        if (isVisible) hide(); else show(opts);
    }

    // ==================== 消息通信 ====================
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        const handle = async () => {
            switch (request.action) {
                case 'show':
                    await show({ backendUrl: request.backendUrl, workflowId: request.workflowId });
                    return { success: true, visible: true, stepCount: actionSteps.length };
                case 'hide':
                    hide();
                    return { success: true, visible: false };
                case 'toggle':
                    toggle({ backendUrl: request.backendUrl, workflowId: request.workflowId });
                    return { success: true, visible: isVisible, stepCount: actionSteps.length };
                case 'getStatus':
                    return { visible: isVisible, stepCount: actionSteps.length, libraryCount: elementLibrary.length };
                case 'clearSteps':
                    actionSteps = [];
                    await chrome.storage.local.remove(STORAGE_KEY_STEPS);
                    refreshStepsPanel();
                    return { success: true };
                case 'clearAll':
                    await clearAllData();
                    refreshStepsPanel();
                    if (libraryPanel) createLibraryPanel();
                    return { success: true };
                case 'exportJSON':
                    const json = await exportAsJSON();
                    return { success: true, data: json };
                case 'exportNL':
                    const nl = exportAsNaturalLanguage();
                    return { success: true, data: nl };
                case 'runWorkflow':
                    const nodes = await fetchWorkflowNodes();
                    if (nodes.length === 0) {
                        return { success: false, error: '无节点或拉取失败' };
                    }
                    await runWorkflowNodes(nodes);
                    return { success: true };
                case 'setBackend':
                    if (request.backendUrl) backendUrl = request.backendUrl;
                    if (request.workflowId) currentWorkflowId = request.workflowId;
                    if (request.token !== undefined) authToken = request.token;
                    return { success: true };
                case 'enterCaptureMode':
                    await enterCaptureMode(true);
                    return { success: true, captureMode: true };
                case 'exitCaptureMode':
                    exitCaptureMode();
                    return { success: true, captureMode: false };
                default:
                    return { success: false, error: 'Unknown action' };
            }
        };
        handle().then(sendResponse);
        return true; // async response
    });

    console.log('[操作编排器] Content script 已加载，点击扩展图标启动面板');
})();
