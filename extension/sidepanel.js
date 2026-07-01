/**
 * sidepanel.js — Chrome Side Panel UI for element editor.
 *
 * Communicates via chrome.runtime.sendMessage instead of iframe postMessage.
 */
(function () {
  'use strict';

  // ─── State ───────────────────────────────────────────────────────
  let elementData = null;
  let selectedPathIndex = -1;
  let activeChoice = 'css';

  function choiceFamily(choice) {
    return choice === 'xpath' ? 'xpath' : 'css';
  }

  function inferFamilyFromSelector(selector) {
    if (!selector) return 'css';
    const lowered = selector.trim().toLowerCase();
    if (lowered.startsWith('xpath:')) return 'xpath';
    if (lowered.startsWith('//') || lowered.startsWith('.//')) return 'xpath';
    return 'css';
  }

  let selectedCandidateType = null;
  let currentTabId = null;
  let pathEnabled = [];   // bool[]: whether each path level is enabled
  let attrEnabled = {};   // { levelIndex: { attrName: bool } }
  let workflows = [];
  let selectedWorkflowId = localStorage.getItem('rpa_selected_workflow_id') || '';
  let screenshotOpen = false;

  // ─── DOM refs ────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const domPanel = $('domPanel');
  const propList = $('propPanel');
  const selectorPreview = $('selectorPreview');
  const verifyResult = $('verifyResult');
  const screenshotPanel = $('screenshotPanel');
  const screenshotToggle = $('screenshotToggle');
  const elName = $('elName');
  const anchorCard = $('anchorCard');
  const useRelativeChk = $('useRelativeChk');
  const anchorSelectorInput = $('anchorSelectorInput');
  const relativeSelectorInput = $('relativeSelectorInput');
  const anchorModeLabel = $('anchorMode');
  // Merged loop-anchor control (top row) — drives both pre-capture highlight
  // and the captured element's anchor selection.
  const activeAnchorSelect = $('activeAnchorSelect');
  const btnClearActiveAnchor = $('btnClearActiveAnchor');
  const activeAnchorStatus = $('activeAnchorStatus');
  let activeAnchorName = '';
  // Tracks whether the user manually edited the relative selector this capture.
  let relativeManuallyEdited = false;
  // Existing elements of the selected workflow, loaded for anchor selection.
  let workflowElements = [];

  // Populate the relative-selector detail from a capture payload. The loop
  // anchor lives in the merged #activeAnchorSelect control above.
  function loadAnchorData(data) {
    relativeManuallyEdited = false;
    const rel = data?.relativeSelector || '';
    const anchorElName = data?.anchorElementName || '';
    relativeSelectorInput.value = rel;
    anchorSelectorInput.value = data?.anchorSelector || '';
    useRelativeChk.checked = !!rel || !!anchorElName;
    anchorCard.classList.toggle('disabled', !useRelativeChk.checked);
    // Reflect the captured element's anchor in the merged loop-anchor control.
    if (activeAnchorSelect && anchorElName) {
      activeAnchorName = anchorElName;
      renderActiveAnchorOptions();
      activeAnchorSelect.value = anchorElName;
    }
    const mode = data?.anchorMode || '';
    anchorModeLabel.textContent = mode === 'manual' ? '手动' : (mode === 'backfill' ? '回填' : '锚定');
  }

  // Capture mode, driven by the top tabs:
  //  - 'new'   → clean global capture, no anchor (原方案);
  //  - 'child' → anchored capture: loop-anchor row + relative card primary,
  //              global selector demoted to a collapsible fallback.
  let captureMode = 'new';

  function refreshAnchorBadge() {
    const badge = $('anchorBadge');
    const name = activeAnchorSelect && activeAnchorSelect.value;
    if (badge) badge.textContent = name ? `基于 ${name}` : '';
  }

  function applyCaptureMode(mode) {
    captureMode = mode === 'child' ? 'child' : 'new';
    const child = captureMode === 'child';
    document.querySelectorAll('.capture-tab').forEach((b) => {
      b.classList.toggle('active', b.dataset.capmode === captureMode);
    });
    const anchorRow = $('activeAnchorRow');
    if (anchorRow) anchorRow.style.display = child ? '' : 'none';
    if (anchorCard) anchorCard.style.display = child ? 'block' : 'none';
    const header = $('globalSelectorHeader');
    if (header) header.style.display = child ? '' : 'none';
    // 新元素: global selector is the primary output (open, no header).
    // 子元素: global selector is the fallback (collapsed under the header).
    setCollapsibleOpen('globalSelectorHeader', 'globalSelectorBody', !child);
    if (!child && activeAnchorSelect && activeAnchorSelect.value) {
      // Leaving anchored mode drops any active loop anchor + page highlight.
      activeAnchorSelect.value = '';
      applyActiveAnchor('');
    }
    refreshAnchorBadge();
  }

  document.querySelectorAll('.capture-tab').forEach((btn) => {
    btn.addEventListener('click', () => applyCaptureMode(btn.dataset.capmode));
  });

  // Recompute the relative selector when the global target changes while anchored.
  function maybeRecomputeRelative() {
    if (captureMode === 'child' && activeAnchorSelect && activeAnchorSelect.value) {
      computeRelativeForSelectedAnchor();
    }
  }

  if (relativeSelectorInput) {
    relativeSelectorInput.addEventListener('input', () => {
      relativeManuallyEdited = true;
      anchorModeLabel.textContent = '手动';
    });
  }

  if (elName) {
    elName.addEventListener('input', () => {
      renderActiveAnchorOptions();
    });
  }

  // ─── Screenshot toggle ───────────────────────────────────────────

  function updateScreenshotToggle(dataUrl) {
    if (dataUrl) {
      screenshotToggle.disabled = false;
      screenshotToggle.classList.add('has-thumb');
      screenshotToggle.innerHTML = `<img class="thumb" src="${dataUrl}" alt="screenshot">`;
      screenshotToggle.title = '查看截图';
    } else {
      screenshotToggle.disabled = true;
      screenshotToggle.classList.remove('has-thumb');
      screenshotToggle.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
          <circle cx="8.5" cy="8.5" r="1.5"></circle>
          <polyline points="21 15 16 10 5 21"></polyline>
        </svg>`;
      screenshotToggle.title = '暂无截图';
    }
  }

  function setScreenshotOpen(open) {
    screenshotOpen = open;
    screenshotPanel.classList.toggle('open', open);
  }

  if (screenshotToggle) {
    screenshotToggle.addEventListener('click', () => {
      setScreenshotOpen(!screenshotOpen);
    });
  }

  // ─── Collapsible sections ────────────────────────────────────────

  function initCollapsible(headerId, bodyId, defaultOpen) {
    const header = $(headerId);
    const body = $(bodyId);
    if (!header || !body) return;
    header.classList.toggle('open', defaultOpen);
    body.classList.toggle('open', defaultOpen);
    header.addEventListener('click', () => {
      const open = body.classList.toggle('open');
      header.classList.toggle('open', open);
    });
  }

  function setCollapsibleOpen(headerId, bodyId, open) {
    const header = $(headerId);
    const body = $(bodyId);
    if (!header || !body) return;
    header.classList.toggle('open', open);
    body.classList.toggle('open', open);
  }

  initCollapsible('domCollapseHeader', 'domCollapseBody', false);
  initCollapsible('propCollapseHeader', 'propCollapseBody', false);
  initCollapsible('globalSelectorHeader', 'globalSelectorBody', true);
  // Default to the clean 捕获新元素 mode until an element is loaded.
  applyCaptureMode('new');

  // ─── Mode toggle (Recommend / Manual) ─────────────────────────────

  let editMode = 'recommend';

  function setEditMode(mode) {
    editMode = mode;
    $('modeRecommend').classList.toggle('active', mode === 'recommend');
    $('modeManual').classList.toggle('active', mode === 'manual');
    $('recommendPanel').classList.toggle('active', mode === 'recommend');
    $('manualPanel').classList.toggle('active', mode === 'manual');
    if (mode === 'manual') {
      setCollapsibleOpen('domCollapseHeader', 'domCollapseBody', true);
      setCollapsibleOpen('propCollapseHeader', 'propCollapseBody', true);
    } else {
      setCollapsibleOpen('domCollapseHeader', 'domCollapseBody', false);
      setCollapsibleOpen('propCollapseHeader', 'propCollapseBody', false);
    }
  }

  $('modeRecommend').addEventListener('click', () => setEditMode('recommend'));
  $('modeManual').addEventListener('click', () => setEditMode('manual'));

  // ─── Runtime Message API ─────────────────────────────────────────

  function send(action, payload) {
    return chrome.runtime.sendMessage({ action, payload });
  }

  function broadcastSelectedCandidate() {
    const selector = selectorPreview.value;
    const type = selectedCandidateType || inferFamilyFromSelector(selector) || choiceFamily(activeChoice);
    if (!selector) return;
    chrome.runtime.sendMessage({ action: 'selectCandidate', payload: { selector, type } }).catch(() => {});
  }

  // Listen for background broadcasts
  chrome.runtime.onMessage.addListener((msg) => {
    if (!msg) return;
    if (msg.action === 'verifyResultBroadcast' && msg.payload) {
      showVerifyResult(msg.payload);
    }
    if (msg.action === 'newCaptureAvailable') {
      loadPayloadFromBackground();
    }
  });

  // ─── Load data ───────────────────────────────────────────────────

  async function loadWorkflows() {
    try {
      const resp = await chrome.runtime.sendMessage({ action: 'getWorkflows' });
      if (resp?.workflows) {
        workflows = resp.workflows;
        const select = $('workflowSelect');
        select.innerHTML = '<option value="">选择流程...</option>';
        workflows.forEach((wf) => {
          const opt = document.createElement('option');
          opt.value = wf.id;
          opt.textContent = wf.name;
          select.appendChild(opt);
        });
        // Restore previous selection
        if (selectedWorkflowId) {
          select.value = selectedWorkflowId;
          await loadWorkflowElements(selectedWorkflowId);
        }
      }
    } catch (e) {
      console.warn('[SidePanel] failed to load workflows:', e);
    }
  }

  async function loadWorkflowElements(workflowId) {
    if (!workflowId) {
      workflowElements = [];
      renderActiveAnchorOptions();
      return;
    }
    try {
      const resp = await chrome.runtime.sendMessage({ action: 'getWorkflowElements', workflowId });
      workflowElements = resp?.elements || [];
      renderActiveAnchorOptions();
    } catch (e) {
      console.warn('[SidePanel] failed to load workflow elements:', e);
      workflowElements = [];
      renderActiveAnchorOptions();
    }
  }

  function getCurrentAnchorElement() {
    const name = activeAnchorSelect?.value;
    if (!name) return null;
    return workflowElements.find((el) => el.name === name) || null;
  }

  // ─── Loop anchor (merged control) ────────────────────────────────
  // Populate the loop-anchor dropdown from the loaded workflow elements,
  // excluding the element currently being edited (it can't be its own anchor).
  function renderActiveAnchorOptions() {
    if (!activeAnchorSelect) return;
    const current = activeAnchorName;
    const excludeName = (elName?.value || elementData?.name || '').trim();
    activeAnchorSelect.innerHTML = '<option value="">全局捕获（无锚点）</option>';
    workflowElements.forEach((el) => {
      if (!el?.name || el.name === excludeName) return;
      const opt = document.createElement('option');
      opt.value = el.name;
      opt.textContent = el.name;
      activeAnchorSelect.appendChild(opt);
    });
    // Keep the selection only if the element still exists and isn't excluded.
    if (current && current !== excludeName && workflowElements.some((el) => el.name === current)) {
      activeAnchorSelect.value = current;
    } else {
      activeAnchorSelect.value = '';
      activeAnchorName = '';
    }
  }

  // Push the chosen anchor to the page: persistent highlight + capture context.
  async function applyActiveAnchor(name) {
    activeAnchorName = name || '';
    if (!activeAnchorName) {
      if (activeAnchorStatus) activeAnchorStatus.textContent = '';
      try { await send('setActiveAnchor', { anchorSelector: '', anchorElementName: '' }); } catch (_e) {}
      return;
    }
    const el = workflowElements.find((e) => e.name === activeAnchorName);
    const anchorSelector = el?.webSelector || '';
    if (!anchorSelector) {
      if (activeAnchorStatus) activeAnchorStatus.textContent = '无选择器';
      return;
    }
    if (activeAnchorStatus) activeAnchorStatus.textContent = '定位中...';
    try {
      const res = await send('setActiveAnchor', { anchorSelector, anchorElementName: activeAnchorName });
      if (res?.error) {
        if (activeAnchorStatus) activeAnchorStatus.textContent = '失败';
      } else {
        const n = res?.count ?? 0;
        if (activeAnchorStatus) activeAnchorStatus.textContent = n > 0 ? `${n} 个锚点` : '未匹配';
      }
    } catch (err) {
      if (activeAnchorStatus) activeAnchorStatus.textContent = '失败';
    }
  }

  function clearActiveAnchor() {
    if (activeAnchorSelect) activeAnchorSelect.value = '';
    applyActiveAnchor('');
    refreshAnchorBadge();
  }

  if (activeAnchorSelect) {
    activeAnchorSelect.addEventListener('change', () => {
      const name = activeAnchorSelect.value;
      applyActiveAnchor(name);
      // In 捕获子元素 mode the anchor card is always visible. Recompute the
      // relative selector against the newly chosen anchor, or clear it.
      if (name) {
        computeRelativeForSelectedAnchor();
      } else {
        relativeSelectorInput.value = '';
        anchorSelectorInput.value = '';
        useRelativeChk.checked = false;
        anchorCard.classList.add('disabled');
      }
      refreshAnchorBadge();
    });
  }
  if (btnClearActiveAnchor) {
    btnClearActiveAnchor.addEventListener('click', () => {
      clearActiveAnchor();
    });
  }

  async function computeRelativeForSelectedAnchor() {
    const anchorEl = getCurrentAnchorElement();
    if (!anchorEl) {
      anchorSelectorInput.value = '';
      relativeSelectorInput.value = '';
      useRelativeChk.checked = false;
      anchorCard.classList.add('disabled');
      return;
    }
    anchorSelectorInput.value = anchorEl.webSelector || '';
    useRelativeChk.checked = true;
    anchorCard.classList.remove('disabled');

    const targetSelector = selectorPreview.value;
    const anchorSelector = anchorEl.webSelector || '';
    if (!targetSelector || !anchorSelector || !currentTabId) {
      verifyResult.textContent = '请确认目标元素和锚点元素';
      verifyResult.className = 'verify-meta err';
      return;
    }
    verifyResult.textContent = '计算相对选择器中...';
    verifyResult.className = 'verify-meta';
    try {
      const res = await send('computeRelativeFromAnchor', {
        tabId: currentTabId,
        payload: { targetSelector, anchorSelector },
      });
      if (res && res.error) {
        verifyResult.textContent = '相对选择器计算失败: ' + res.error;
        verifyResult.className = 'verify-meta err';
        return;
      }
      relativeSelectorInput.value = res.relativeSelector || '';
      relativeManuallyEdited = false;
      anchorModeLabel.textContent = '锚定';
      verifyResult.textContent = '相对选择器已生成: ' + (res.relativeSelector || '');
      verifyResult.className = 'verify-meta ok';
    } catch (err) {
      verifyResult.textContent = '计算失败: ' + err.message;
      verifyResult.className = 'verify-meta err';
    }
  }

  async function loadPayloadFromBackground() {
    try {
      const resp = await chrome.runtime.sendMessage({ action: 'getCapturePayload' });
      if (resp?.payload) {
        currentTabId = resp.tabId;
        loadElementData(resp.payload);
      } else {
        const loading = $('loadingOverlay');
        if (loading) loading.classList.add('hidden');
      }
    } catch (e) {
      console.warn('[SidePanel] failed to get payload:', e);
      const loading = $('loadingOverlay');
      if (loading) loading.classList.add('hidden');
    }
  }

  function loadElementData(data) {
    const loading = $('loadingOverlay');
    if (loading) loading.classList.add('hidden');
    elementData = data;
    resetSaveButton();
    if (!data) return;

    elName.value = data.name || '';

    // Screenshot
    if (data.screenshot) {
      screenshotPanel.innerHTML = `<img src="${data.screenshot}" alt="screenshot">`;
      updateScreenshotToggle(data.screenshot);
      setScreenshotOpen(false);
    } else {
      screenshotPanel.innerHTML = '<div class="screenshot-empty">暂无截图</div>';
      updateScreenshotToggle(null);
      setScreenshotOpen(false);
    }

    // Initialize path: all enabled by default
    const path = data.path || [];
    pathEnabled = path.map(() => true);
    attrEnabled = {};
    path.forEach((_, i) => { attrEnabled[i] = {}; });

    // Default: select the deepest (target) level
    selectedPathIndex = path.length - 1;

    // Restore active choice from selector prefix or payload family.
    activeChoice = inferFamilyFromSelector(data.selector) || data.selectorFamily || 'css';
    document.querySelectorAll('.choice-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.choice === activeChoice);
    });

    renderDomTree();
    renderCandidates();
    renderProperties();

    // Default: select the first usable (css/xpath) candidate and sync output format.
    const first = (data.candidates || []).find((c) => {
      const f = c.family || c.type || 'css';
      return f === 'css' || f === 'xpath';
    });
    if (first) {
      activeChoice = first.family || first.type || 'css';
      syncChoiceButtons();
      selectorPreview.value = first.syntax;
      selectedCandidateType = first.family || first.type || choiceFamily(activeChoice);
      applyCandidateToUI(first);
      const statusText = first.matchCount === 1 ? '唯一匹配' : (first.isList ? `列表 (${first.matchCount}个)` : first.matchCount + ' 匹配');
      verifyResult.textContent = `${statusText} | score:${first.score}`;
      verifyResult.className = 'verify-meta ' + (first.matchCount === 1 ? 'ok' : '');
      broadcastSelectedCandidate();
    } else {
      updateSelector();
    }

    // Loop-relative anchoring. An element with an anchor/relative selector opens
    // in 捕获子元素 mode; otherwise the clean 捕获新元素 mode.
    loadAnchorData(data);
    const anchored = !!(data?.relativeSelector || data?.anchorElementName);
    applyCaptureMode(anchored ? 'child' : 'new');
  }

  // ─── DOM Tree rendering ──────────────────────────────────────────

  function renderDomTree() {
    domPanel.innerHTML = '';
    const path = elementData?.path || [];
    path.forEach((node, i) => {
      const row = document.createElement('div');
      row.className = 'dom-item' + (i === selectedPathIndex ? ' active' : '');

      // Orange indicator when any attribute is used at this level
      const hasAttr = Object.keys(attrEnabled[i] || {}).some((k) => attrEnabled[i][k]);
      if (hasAttr) {
        row.style.borderLeft = '3px solid #fa8c16';
        row.style.paddingLeft = '7px';
      }

      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = pathEnabled[i];
      cb.addEventListener('change', () => {
        pathEnabled[i] = cb.checked;
        updateSelector();
      });

      const tag = document.createElement('span');
      tag.className = 'dom-tag';
      tag.textContent = '<' + (node.tag || 'div') + ' /' + '>';

      const preview = document.createElement('span');
      preview.className = 'dom-preview';
      const attrs = [];
      if (node.id) attrs.push(`#${node.id}`);
      if (node.classes?.length) attrs.push('.' + node.classes.slice(0, 2).join('.'));
      preview.textContent = attrs.join('');

      row.appendChild(cb);
      row.appendChild(tag);
      row.appendChild(preview);

      row.addEventListener('click', (e) => {
        if (e.target === cb) return;
        selectedPathIndex = i;
        renderDomTree();
        renderProperties();
      });

      domPanel.appendChild(row);
    });
  }

  // ─── Apply candidate selection to DOM tree / properties ──────────

  function applyCandidateToUI(c) {
    if (!elementData?.path?.length) return;
    const path = elementData.path;

    // Reset
    pathEnabled = path.map(() => false);
    attrEnabled = {};
    path.forEach((_, i) => { attrEnabled[i] = {}; });

    let syntax = c.syntax;
    const family = c.family || c.type || choiceFamily(activeChoice);

    // Strip prefix
    if (syntax.startsWith('css:')) syntax = syntax.slice(4);
    else if (syntax.startsWith('xpath:')) syntax = syntax.slice(6);
    else if (syntax.startsWith('verse:')) {
      pathEnabled[path.length - 1] = false;
      selectedPathIndex = path.length - 1;
      attrEnabled[path.length - 1]['verse_fp'] = true;
      renderDomTree();
      renderProperties();
      return;
    }

    // If candidate carries pathMapping, apply directly without reverse guessing
    if (c.pathMapping && c.pathMapping.length > 0) {
      const segs = family === 'xpath'
        ? syntax.split('/').filter(Boolean)
        : syntax.split(/\s*>\s*|\s+/).filter(Boolean);
      segs.forEach((segStr, idx) => {
        const pathIdx = c.pathMapping[idx];
        if (pathIdx === undefined) return;
        const seg = family === 'xpath' ? parseXPathSeg(segStr) : parseSeg(segStr);
        applySegToNode(seg, pathIdx);
      });
      selectedPathIndex = pathEnabled.lastIndexOf(true);
      renderDomTree();
      renderProperties();
      return;
    }

    // Convert tag: prefixed syntax to CSS-like for parsing
    if (syntax.startsWith('tag:')) {
      syntax = syntax.slice(4);
      syntax = syntax.replace(/@class=([a-zA-Z0-9_-]+)/g, '.$1');
      syntax = syntax.replace(/@([a-zA-Z0-9_-]+)=([^@]+)$/g, '[$1="$2"]');
    }

    // Sibling / text-based selectors cannot be mapped to ancestor path
    if (/[+~]/.test(syntax) || syntax.startsWith('text=') || syntax.startsWith('@')) {
      pathEnabled[path.length - 1] = /[+~]/.test(syntax);
      selectedPathIndex = path.length - 1;

      if (/[+~]/.test(syntax)) {
        const sibMatch = syntax.match(/(.+?)([+~])([a-zA-Z0-9_*-]+)/);
        if (sibMatch) {
          const ancPart = sibMatch[1];
          const ancSeg = parseSeg(ancPart);
          const targetNode = path[path.length - 1];
          if (targetNode.siblings) {
            targetNode.siblings.forEach((sib, idx) => {
              if (ancSeg.id && ancSeg.id !== sib.id) return;
              if (ancSeg.classes.length && !ancSeg.classes.every(c => sib.classes?.includes(c))) return;
              if (ancSeg.tag && ancSeg.tag !== '*' && ancSeg.tag !== sib.tag) return;
              attrEnabled[path.length - 1]['sib:' + idx] = true;
            });
          }
        }
      }

      renderDomTree();
      renderProperties();
      return;
    }

    // Helper: parse a CSS selector segment
    function parseSeg(seg) {
      let tag = seg.match(/^([a-zA-Z0-9_*-]+)/)?.[1] || '';
      let id = seg.match(/#([a-zA-Z0-9_-]+)/)?.[1] || '';
      const classes = [...seg.matchAll(/\.([a-zA-Z0-9_-]+)/g)].map(m => m[1]);
      let attrs = [...seg.matchAll(/\[([a-zA-Z0-9_-]+)(?:=["']([^"']*)["'])?\]/g)];
      const nth = seg.match(/:nth-of-type\((\d+)\)/)?.[1] || '';
      const nthChild = seg.match(/:nth-child\((\d+)\)/)?.[1] || '';

      // Extract id from [id="foo"] so it matches node.id (not node.attrs)
      const idAttr = attrs.find(a => a[1] === 'id');
      if (idAttr && idAttr[2]) {
        id = idAttr[2];
        attrs = attrs.filter(a => a[1] !== 'id');
      }
      // Extract classes from [class="foo bar"]
      const classAttr = attrs.find(a => a[1] === 'class');
      if (classAttr && classAttr[2]) {
        classAttr[2].split(/\s+/).filter(Boolean).forEach(c => {
          if (!classes.includes(c)) classes.push(c);
        });
        attrs = attrs.filter(a => a[1] !== 'class');
      }

      return { tag, id, classes, attrs, nth, nthChild };
    }

    // Helper: parse an XPath segment like div[@id='foo'][2][contains(text(),'x')]
    function parseXPathSeg(seg) {
      const tagMatch = seg.match(/^([a-zA-Z0-9_*-]+)/);
      const tag = tagMatch ? tagMatch[1] : '';
      const predicates = [];
      const regex = /\[([^\[\]]+)\]/g;
      let m;
      while ((m = regex.exec(seg)) !== null) {
        predicates.push(m[1]);
      }

      let id = '';
      const classes = [];
      const attrs = [];
      let nth = '';
      let nthChild = '';
      let text = '';

      for (const p of predicates) {
        const idMatch = p.match(/^@id\s*=\s*'([^']*)'$/);
        if (idMatch) { id = idMatch[1]; continue; }
        const idMatch2 = p.match(/^@id\s*=\s*"([^"]*)"$/);
        if (idMatch2) { id = idMatch2[1]; continue; }

        const clsMatch = p.match(/^contains\(@class\s*,\s*'([^']*)'\)$/);
        if (clsMatch) { classes.push(clsMatch[1]); continue; }
        const clsMatch2 = p.match(/^contains\(@class\s*,\s*"([^"]*)"\)$/);
        if (clsMatch2) { classes.push(clsMatch2[1]); continue; }

        const textMatch = p.match(/^contains\(text\(\)\s*,\s*'([^']*)'\)$/);
        if (textMatch) { text = textMatch[1]; continue; }
        const textMatch2 = p.match(/^contains\(text\(\)\s*,\s*"([^"]*)"\)$/);
        if (textMatch2) { text = textMatch2[1]; continue; }

        const posMatch = p.match(/^position\(\)\s*=\s*(\d+)$/);
        if (posMatch) { nthChild = posMatch[1]; continue; }

        const numMatch = p.match(/^(\d+)$/);
        if (numMatch) { nth = numMatch[1]; continue; }

        const attrMatch = p.match(/^(?:@)?([a-zA-Z0-9_-]+)\s*=\s*'([^']*)'$/);
        if (attrMatch) { attrs.push([p, attrMatch[1], attrMatch[2]]); continue; }
        const attrMatch2 = p.match(/^(?:@)?([a-zA-Z0-9_-]+)\s*=\s*"([^"]*)"$/);
        if (attrMatch2) { attrs.push([p, attrMatch2[1], attrMatch2[2]]); continue; }
      }

      return { tag, id, classes, attrs, nth, nthChild, text };
    }

    function segMatchesNode(seg, node) {
      if (seg.tag && seg.tag !== '*' && seg.tag !== node.tag) return false;
      if (seg.id && seg.id !== node.id) return false;
      if (seg.classes.length && !seg.classes.every(c => node.classes?.includes(c))) return false;
      if (seg.nth) {
        const expectedIdx = String((node.index || 0) + 1);
        if (seg.nth !== expectedIdx) return false;
      }
      if (seg.nthChild) {
        const expectedIdx = String((node.realIndex ?? node.index ?? 0) + 1);
        if (seg.nthChild !== expectedIdx) return false;
      }
      for (const [_, name, val] of seg.attrs) {
        if (val !== undefined) {
          // Unescape CSS escapes (e.g. \{\} -> {}) before comparing with raw DOM values
          const unescaped = val.replace(/\\(.)/g, '$1');
          const actual = (node.attrs?.[name] || '').toString().trim();
          if (actual !== unescaped.trim()) return false;
        } else {
          if (!node.attrs?.hasOwnProperty(name)) return false;
        }
      }
      return true;
    }

    function applySegToNode(seg, i) {
      const node = path[i];
      // pathEnabled now means "tag is explicitly used in the selector"
      pathEnabled[i] = !!(seg.tag && seg.tag !== '*');
      if (seg.id) attrEnabled[i]['id'] = true;
      seg.classes.forEach(c => { if (node.classes?.includes(c)) attrEnabled[i]['class:' + c] = true; });
      seg.attrs.forEach(([_, name]) => {
        if (node.attrs?.[name] !== undefined) attrEnabled[i][name] = true;
      });
      if (seg.nth) attrEnabled[i]['index-of-type'] = true;
      if (seg.nthChild) attrEnabled[i]['nth-child'] = true;
      if (seg.text) attrEnabled[i]['innerText'] = true;
    }

    function applySegToNodeLoose(seg, i) {
      const node = path[i];
      pathEnabled[i] = !!(seg.tag && seg.tag !== '*');
      if (seg.id && node.id) attrEnabled[i]['id'] = true;
      seg.classes.forEach(c => { if (node.classes?.includes(c)) attrEnabled[i]['class:' + c] = true; });
      seg.attrs.forEach(([_, name]) => {
        if (node.attrs?.[name] !== undefined) attrEnabled[i][name] = true;
      });
      if (seg.nth && node.index !== undefined) attrEnabled[i]['index-of-type'] = true;
      if (seg.nthChild && node.realIndex !== undefined) attrEnabled[i]['nth-child'] = true;
      if (seg.text) attrEnabled[i]['innerText'] = true;
    }

    const isXPath = family === 'xpath';
    const segDelimiter = isXPath ? /\// : /\s*>\s*|\s+/;

    // Compound selector
    const segs = syntax.split(segDelimiter).filter(Boolean);
    const parseFn = isXPath ? parseXPathSeg : parseSeg;

    if (segs.length >= 1) {
      let segIdx = segs.length - 1;
      for (let i = path.length - 1; i >= 0 && segIdx >= 0; i--) {
        const seg = parseFn(segs[segIdx]);
        if (!segMatchesNode(seg, path[i])) continue;
        applySegToNode(seg, i);
        segIdx--;
      }
      // Fallback: loose match remaining segs against any path element (check attr name only)
      if (segIdx >= 0) {
        for (let j = segIdx; j >= 0; j--) {
          const seg = parseFn(segs[j]);
          for (let k = path.length - 1; k >= 0; k--) {
            const node = path[k];
            if (seg.tag && seg.tag !== '*' && seg.tag !== node.tag) continue;
            if (seg.id && seg.id !== node.id) continue;
            if (seg.classes.length && !seg.classes.every(c => node.classes?.includes(c))) continue;
            let allNamesExist = true;
            for (const [_, name] of seg.attrs) {
              if (node.attrs?.[name] === undefined && node.attrs?.[name] !== '') {
                allNamesExist = false;
                break;
              }
            }
            if (!allNamesExist) continue;
            applySegToNodeLoose(seg, k);
            break;
          }
        }
      }
      selectedPathIndex = pathEnabled.lastIndexOf(true);
      renderDomTree();
      renderProperties();
      return;
    }

    // Fallback: check target element only
    pathEnabled[path.length - 1] = true;
    selectedPathIndex = path.length - 1;
    renderDomTree();
    renderProperties();
  }

  // ─── Candidates rendering ────────────────────────────────────────

  function renderCandidates() {
    const list = $('candidatesList');
    list.innerHTML = '';
    const cands = (elementData?.candidates || []).filter((c) => {
      const f = c.family || c.type || 'css';
      return f === 'css' || f === 'xpath';
    });
    // Deduplicate by syntax; generation phases may emit identical selectors.
    const seen = new Set();
    const uniqueCands = [];
    for (const c of cands) {
      if (seen.has(c.syntax)) continue;
      seen.add(c.syntax);
      uniqueCands.push(c);
    }
    if (uniqueCands.length === 0) {
      list.innerHTML = '<div class="candidates-empty">暂无推荐方案</div>';
      return;
    }
    uniqueCands.forEach((c) => {
      const row = document.createElement('div');
      row.className = 'prop-row';
      row.style.cursor = 'pointer';
      row.title = c.syntax;

      const family = c.family || c.type || 'css';
      const mode = c.isList ? 'list' : 'single';
      const familyPill = `<span style="background:${family === 'css' ? '#fff2e8' : '#f6ffed'};color:${family === 'css' ? '#fa8c16' : '#52c41a'};font-size:10px;padding:1px 5px;border-radius:3px;white-space:nowrap;border:1px solid ${family === 'css' ? '#ffbb96' : '#b7eb8f'};">${family.toUpperCase()}</span>`;
      const modePill = c.isList
        ? '<span style="background:#f9f0ff;color:#722ed1;font-size:10px;padding:1px 5px;border-radius:3px;white-space:nowrap;border:1px solid #d3adf7;">列表</span>'
        : '<span style="background:#f0f0f0;color:#666;font-size:10px;padding:1px 5px;border-radius:3px;white-space:nowrap;">单个</span>';
      const matchPill = c.matchCount === 1
        ? '<span style="background:#52c41a;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;white-space:nowrap;">唯一</span>'
        : `<span style="background:#f0f0f0;color:#666;font-size:10px;padding:1px 5px;border-radius:3px;white-space:nowrap;">${c.matchCount} 匹配</span>`;

      row.innerHTML = `
        <span style="flex:1;min-width:0;font-family:monospace;font-size:11px;color:#333;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(c.syntax)}</span>
        <span style="display:flex;gap:4px;flex-shrink:0;">${familyPill}${modePill}${matchPill}</span>
      `;

      row.addEventListener('click', () => {
        activeChoice = family;
        syncChoiceButtons();
        selectorPreview.value = c.syntax;
        selectedCandidateType = family;
        applyCandidateToUI(c);
        const statusText = c.matchCount === 1 ? '唯一匹配' : (c.isList ? `列表 (${c.matchCount}个)` : c.matchCount + ' 匹配');
        verifyResult.textContent = `${statusText} | score:${c.score}`;
        verifyResult.className = 'verify-meta ' + (c.matchCount === 1 ? 'ok' : '');
        broadcastSelectedCandidate();
        maybeRecomputeRelative();
      });

      list.appendChild(row);
    });
  }

  function escapeHtml(str) {
    return str.replace(/[<>"&]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '"': '&quot;', '&': '&amp;' }[c]));
  }

  function syncChoiceButtons() {
    document.querySelectorAll('.choice-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.choice === activeChoice);
    });
  }

  // ─── Properties rendering ────────────────────────────────────────

  function renderProperties() {
    propList.innerHTML = '';
    const path = elementData?.path || [];
    if (selectedPathIndex < 0 || selectedPathIndex >= path.length) return;

    const node = path[selectedPathIndex];
    const enabledMap = attrEnabled[selectedPathIndex] || {};

    // Section: attributes
    const section = document.createElement('div');
    section.className = 'prop-section';

    const title = document.createElement('div');
    title.className = 'prop-section-title';
    title.textContent = '属性';
    section.appendChild(title);

    // id
    if (node.id) addPropRow(section, 'id', node.id, enabledMap);

    // classes
    (node.classes || []).forEach((cls) => addPropRow(section, 'class:' + cls, cls, enabledMap, false, 'class'));

    // other attributes
    const attrs = node.attrs || {};
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === 'id' || k === 'class') return;
      addPropRow(section, k, v, enabledMap);
    });

    // structural: index-of-type / nth-child
    const parent = selectedPathIndex > 0 ? path[selectedPathIndex - 1] : null;
    if (parent) {
      const sameTagSiblings = parent.childrenTags?.filter((t) => t === node.tag).length || 1;
      if (sameTagSiblings > 1 || enabledMap['index-of-type']) {
        addPropRow(section, 'index-of-type', String((node.index || 0) + 1), enabledMap, false, 'index-of-type');
      }
      const allSiblings = parent.childrenTags?.length || 1;
      if (allSiblings > 1 || enabledMap['nth-child']) {
        addPropRow(section, 'nth-child', String((node.realIndex ?? node.index ?? 0) + 1), enabledMap, false, 'nth-child');
      }
    }

    propList.appendChild(section);

    // 目标元素额外展示：文本内容与 verse 指纹（只读）
    const isTarget = selectedPathIndex === path.length - 1;
    if (isTarget) {
      const contentSection = document.createElement('div');
      contentSection.className = 'prop-section';

      const contentTitle = document.createElement('div');
      contentTitle.className = 'prop-section-title';
      contentTitle.textContent = '内容';
      contentSection.appendChild(contentTitle);

      if (elementData?.inner_text) {
        addPropRow(contentSection, 'innerText', elementData.inner_text, attrEnabled[selectedPathIndex] || {}, false, 'innerText');
      }
      if (elementData?.verse_fp) {
        addPropRow(contentSection, 'verse_fp', elementData.verse_fp, attrEnabled[selectedPathIndex] || {}, false, 'verse');
      }

      propList.appendChild(contentSection);

      // 相邻兄弟（只对目标元素展示，可勾选作为 sibling 锚点）
      if (node.siblings?.length) {
        const sibSection = document.createElement('div');
        sibSection.className = 'prop-section';

        const sibTitle = document.createElement('div');
        sibTitle.className = 'prop-section-title';
        sibTitle.textContent = '相邻兄弟';
        sibSection.appendChild(sibTitle);

        const myIdx = node.realIndex ?? node.index ?? 0;
        node.siblings.forEach((sib, idx) => {
          const isMe = idx === myIdx;

          const row = document.createElement('div');
          row.className = 'prop-row';
          row.style.fontSize = '11px';

          let label = '';
          if (sib.id) label += '#' + escapeHtml(sib.id);
          if (sib.classes?.length) label += '.' + escapeHtml(sib.classes.slice(0, 2).join('.'));
          if (!label) label = sib.tag;

          if (isMe) {
            const meSpan = document.createElement('span');
            meSpan.style.color = '#1677ff';
            meSpan.style.flex = '1';
            meSpan.textContent = `● 当前 <${sib.tag}> ${label}`;
            row.appendChild(meSpan);
          } else if (idx < myIdx) {
            // 前兄弟可作为 sibling 锚点（CSS +/~ 语义）
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = !!enabledMap['sib:' + idx];
            cb.addEventListener('change', () => {
              // Only one sibling anchor at a time
              Object.keys(enabledMap).forEach((k) => {
                if (k.startsWith('sib:')) enabledMap[k] = false;
              });
              enabledMap['sib:' + idx] = cb.checked;
              updateSelector();
            });

            const nameEl = document.createElement('span');
            nameEl.style.flex = '1';
            nameEl.style.color = '#666';
            nameEl.textContent = `<${sib.tag}> ${label}`;

            row.appendChild(cb);
            row.appendChild(nameEl);
          } else {
            // 后兄弟不能作为锚点，只读展示
            const roSpan = document.createElement('span');
            roSpan.style.flex = '1';
            roSpan.style.color = '#999';
            roSpan.textContent = `<${sib.tag}> ${label}`;
            row.appendChild(roSpan);
          }

          sibSection.appendChild(row);
        });

        propList.appendChild(sibSection);
      }
    }
  }

  function addPropRow(container, name, value, enabledMap, disabled, displayName) {
    const row = document.createElement('div');
    row.className = 'prop-row';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = !!enabledMap[name];
    cb.disabled = !!disabled;
    cb.addEventListener('change', () => {
      enabledMap[name] = cb.checked;
      updateSelector();
    });

    const nameEl = document.createElement('span');
    nameEl.className = 'prop-name';
    nameEl.textContent = displayName || name;

    const matchEl = document.createElement('select');
    matchEl.className = 'prop-match';
    matchEl.innerHTML = `
      <option value="equals">等于</option>
      <option value="contains">包含</option>
      <option value="not_contains">不包含</option>
      <option value="starts_with">开头为</option>
      <option value="not_starts_with">开头不为</option>
      <option value="ends_with">结尾为</option>
      <option value="not_ends_with">结尾不为</option>
      <option value="not_equals">不等于</option>
      <option value="gt">大于</option>
      <option value="gte">大于等于</option>
      <option value="lt">小于</option>
      <option value="lte">小于等于</option>
    `;
    matchEl.value = enabledMap[name + ':operator'] || 'equals';
    matchEl.disabled = !!disabled;
    matchEl.addEventListener('change', () => {
      enabledMap[name + ':operator'] = matchEl.value;
      updateSelector();
    });

    const valEl = document.createElement('input');
    valEl.className = 'prop-value';
    valEl.value = value;
    valEl.disabled = !!disabled;
    valEl.addEventListener('input', () => {
      const node = elementData.path[selectedPathIndex];
      if (name.startsWith('class:')) {
        const oldCls = name.slice(6);
        const idx = node.classes.indexOf(oldCls);
        if (idx >= 0) node.classes[idx] = valEl.value;
      } else if (name === 'innerText' || name === 'verse_fp') {
        // 非 DOM 属性，不写入 node.attrs
      } else if (node.attrs) {
        node.attrs[name] = valEl.value;
      }
      updateSelector();
    });

    row.appendChild(cb);
    row.appendChild(nameEl);
    row.appendChild(matchEl);
    row.appendChild(valEl);
    container.appendChild(row);
    return row;
  }

  // ─── Selector assembly ───────────────────────────────────────────

  function cssEsc(v) { return v.replace(/(["\\])/g, '\\$1').replace(/\n/g, ' '); }
  function xpathLiteral(v) {
    if (typeof v !== 'string') v = String(v);
    if (!v.includes("'")) return `'${v}'`;
    if (!v.includes('"')) return `"${v}"`;
    return `concat('${v.split("'").join(`', "'", '`)}')`;
  }

  function buildAttrPredicate(key, value, operator) {
    if (activeChoice === 'css') {
      switch (operator) {
        case 'contains': return `[${key}*="${cssEsc(value)}"]`;
        case 'starts_with': return `[${key}^="${cssEsc(value)}"]`;
        case 'ends_with': return `[${key}$="${cssEsc(value)}"]`;
        case 'not_equals': return `:not([${key}="${cssEsc(value)}"])`;
        case 'not_contains': return `:not([${key}*="${cssEsc(value)}"])`;
        case 'not_starts_with': return `:not([${key}^="${cssEsc(value)}"])`;
        case 'not_ends_with': return `:not([${key}$="${cssEsc(value)}"])`;
        default: return `[${key}="${cssEsc(value)}"]`;
      }
    }
    // XPath
    switch (operator) {
      case 'contains': return `[contains(@${key},${xpathLiteral(value)})]`;
      case 'not_contains': return `[not(contains(@${key},${xpathLiteral(value)}))]`;
      case 'starts_with': return `[starts-with(@${key},${xpathLiteral(value)})]`;
      case 'not_starts_with': return `[not(starts-with(@${key},${xpathLiteral(value)}))]`;
      case 'ends_with': return `[substring(@${key}, string-length(@${key}) - string-length(${xpathLiteral(value)}) + 1) = ${xpathLiteral(value)}]`;
      case 'not_ends_with': return `[not(substring(@${key}, string-length(@${key}) - string-length(${xpathLiteral(value)}) + 1) = ${xpathLiteral(value)})]`;
      case 'not_equals': return `[@${key}!=${xpathLiteral(value)}]`;
      case 'gt': return `[@${key}>${value}]`;
      case 'gte': return `[@${key}>=${value}]`;
      case 'lt': return `[@${key}<${value}]`;
      case 'lte': return `[@${key}<=${value}]`;
      default: return `[@${key}=${xpathLiteral(value)}]`;
    }
  }

  function buildXPathSeg(node, attrMap, includeTag, innerTextValue) {
    let seg = includeTag ? (node.tag || '*') : '*';
    const predicates = [];

    if (attrMap.id && node.id) {
      predicates.push(`@id=${xpathLiteral(node.id)}`);
    }

    (node.classes || []).forEach((cls) => {
      if (attrMap['class:' + cls]) {
        predicates.push(`contains(@class,${xpathLiteral(cls)})`);
      }
    });

    Object.entries(node.attrs || {}).forEach(([k, v]) => {
      if (k === 'verse_fp') return;
      if (!attrMap[k]) return;
      const op = attrMap[k + ':operator'] || 'equals';
      predicates.push(buildAttrPredicate(k, v, op).slice(1, -1));
    });

    if (attrMap['index-of-type']) {
      predicates.push(String((node.index || 0) + 1));
    }
    if (attrMap['nth-child']) {
      predicates.push(`position()=${(node.realIndex ?? node.index ?? 0) + 1}`);
    }
    if (innerTextValue) {
      predicates.push(`contains(text(),${xpathLiteral(innerTextValue)})`);
    }

    return seg + predicates.map((p) => `[${p}]`).join('');
  }

  function joinSegs(segs, segIndices, type) {
    if (segs.length === 0) return '';
    let result = segs[0];
    for (let j = 1; j < segs.length; j++) {
      const diff = segIndices[j] - segIndices[j - 1];
      if (type === 'xpath') {
        result += (diff === 1 ? '/' : '//') + segs[j];
      } else {
        result += (diff === 1 ? ' > ' : ' ') + segs[j];
      }
    }
    return result;
  }

  function updateSelector() {
    if (!elementData) return;
    const path = elementData.path || [];
    const segs = [];
    const segIndices = [];

    if (activeChoice === 'xpath') {
      for (let i = 0; i < path.length; i++) {
        const node = path[i];
        const attrMap = attrEnabled[i] || {};
        const hasId = attrMap.id && node.id;
        const hasClass = (node.classes || []).some((cls) => attrMap['class:' + cls]);
        const hasAttr = Object.keys(node.attrs || {}).some((k) => attrMap[k]);
        const hasNth = attrMap['index-of-type'];
        const hasNthChild = attrMap['nth-child'];
        const hasText = attrMap['innerText'] && elementData?.inner_text && i === path.length - 1;
        const hasSib = Object.keys(attrMap).some((k) => k.startsWith('sib:') && attrMap[k]);
        const hasAny = pathEnabled[i] || hasId || hasClass || hasAttr || hasNth || hasNthChild || hasText || hasSib;
        if (!hasAny) continue;
        const innerTextValue = hasText ? elementData.inner_text.slice(0, 80) : null;
        segs.push(buildXPathSeg(node, attrMap, pathEnabled[i], innerTextValue));
        segIndices.push(i);
      }
    } else {
      for (let i = 0; i < path.length; i++) {
        const node = path[i];
        const attrMap = attrEnabled[i] || {};
        const hasId = attrMap.id && node.id;
        const hasClass = (node.classes || []).some((cls) => attrMap['class:' + cls]);
        const hasAttr = Object.keys(node.attrs || {}).some((k) => attrMap[k]);
        const hasNth = attrMap['index-of-type'];
        const hasNthChild = attrMap['nth-child'];
        const hasSib = Object.keys(attrMap).some((k) => k.startsWith('sib:') && attrMap[k]);

        const hasAny = pathEnabled[i] || hasId || hasClass || hasAttr || hasNth || hasNthChild || hasSib;
        if (!hasAny) continue;

        const parts = [];

        if (pathEnabled[i]) {
          parts.push(node.tag || 'div');
        }

        if (hasId) {
          if (!pathEnabled[i]) parts.length = 0;
          parts.push('#' + CSS.escape(node.id));
        } else if (hasClass) {
          if (!pathEnabled[i]) parts.length = 0;
          (node.classes || []).forEach((cls) => {
            if (attrMap['class:' + cls]) {
              parts.push('.' + CSS.escape(cls));
            }
          });
        } else if (hasAttr && !pathEnabled[i]) {
          // No tag wanted, ensure parts is empty so only attributes are emitted
          parts.length = 0;
        }

        const attrs = node.attrs || {};
        Object.entries(attrs).forEach(([k, v]) => {
          if (k === 'verse_fp') return;
          if (!attrMap[k]) return;
          const op = attrMap[k + ':operator'] || 'equals';
          parts.push(buildAttrPredicate(k, v, op));
        });

        if (hasNth) {
          const idx = (node.index || 0) + 1;
          parts.push(`:nth-of-type(${idx})`);
        }
        if (hasNthChild) {
          const idx = (node.realIndex ?? node.index ?? 0) + 1;
          parts.push(`:nth-child(${idx})`);
        }

        segs.push(parts.join(''));
        segIndices.push(i);
      }
    }

    // Apply sibling anchor prefix to the last segment
    if (activeChoice === 'css') {
      const targetIdx = path.length - 1;
      const targetAttrMap = attrEnabled[targetIdx] || {};
      for (const key of Object.keys(targetAttrMap)) {
        if (key.startsWith('sib:') && targetAttrMap[key]) {
          const sibIdx = parseInt(key.slice(4), 10);
          const targetNode = path[targetIdx];
          const sib = targetNode.siblings?.[sibIdx];
          if (sib) {
            let prefix = '';
            if (sib.id) prefix = '#' + CSS.escape(sib.id) + '+';
            else if (sib.classes?.length) prefix = '.' + CSS.escape(sib.classes[0]) + '+';
            else prefix = CSS.escape(sib.tag) + '+';
            if (segs.length > 0) {
              segs[segs.length - 1] = prefix + segs[segs.length - 1];
            }
          }
        }
      }
    } else if (activeChoice === 'xpath') {
      const targetIdx = path.length - 1;
      const targetAttrMap = attrEnabled[targetIdx] || {};
      for (const key of Object.keys(targetAttrMap)) {
        if (key.startsWith('sib:') && targetAttrMap[key]) {
          const sibIdx = parseInt(key.slice(4), 10);
          const targetNode = path[targetIdx];
          const sib = targetNode.siblings?.[sibIdx];
          if (sib) {
            let sibPred = '';
            if (sib.id) {
              sibPred = `@id=${xpathLiteral(sib.id)}`;
            } else if (sib.classes?.length) {
              sibPred = `contains(@class,${xpathLiteral(sib.classes[0])})`;
            } else {
              sibPred = `self::${sib.tag || '*'}`;
            }
            if (segs.length > 0) {
              segs[segs.length - 1] = segs[segs.length - 1] + `[preceding-sibling::*[1][${sibPred}]]`;
            }
          }
        }
      }
    }

    if (activeChoice === 'css') {
      selectorPreview.value = 'css:' + joinSegs(segs, segIndices, 'css');
    } else if (activeChoice === 'xpath') {
      selectorPreview.value = 'xpath://' + joinSegs(segs, segIndices, 'xpath');
    } else {
      selectorPreview.value = 'css:' + joinSegs(segs, segIndices, 'css');
    }

    verifyResult.textContent = '点击"校验元素"查看匹配结果';
    verifyResult.className = 'verify-meta';
    broadcastSelectedCandidate();
  }

  // ─── Verify ──────────────────────────────────────────────────────

  function showVerifyResult(result) {
    const visible = result.visible ?? result.count ?? 0;
    const invisible = result.invisible ?? 0;
    const total = result.total ?? (visible + invisible);
    if (total === 0) {
      verifyResult.textContent = '未匹配到元素';
      verifyResult.className = 'verify-meta err';
    } else if (total === 1) {
      verifyResult.textContent = `匹配: 1 个元素 ✓${invisible > 0 ? ` (忽略 ${invisible} 个不可见)` : ''}`;
      verifyResult.className = 'verify-meta ok';
    } else {
      verifyResult.textContent = `匹配: ${visible} 个可见，${invisible} 个不可见（共 ${total} 个）`;
      verifyResult.className = 'verify-meta err';
    }
  }

  // ─── Event handlers ──────────────────────────────────────────────

  // Choice buttons (output format)
  document.querySelectorAll('.choice-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      activeChoice = btn.dataset.choice;
      syncChoiceButtons();
      updateSelector();
      maybeRecomputeRelative();
    });
  });

  // Verify
  $('btnVerify').addEventListener('click', () => {
    if (!currentTabId) {
      verifyResult.textContent = '未关联页面';
      verifyResult.className = 'verify-meta err';
      return;
    }
    verifyResult.textContent = '校验中...';
    verifyResult.className = 'verify-meta';
    send('verifyElement', {
      tabId: currentTabId,
      payload: { selector: selectorPreview.value, type: inferFamilyFromSelector(selectorPreview.value) },
    }).then((res) => {
      if (res && res.error) {
        verifyResult.textContent = '校验失败: ' + res.error;
        verifyResult.className = 'verify-meta err';
      }
    }).catch((err) => {
      verifyResult.textContent = '校验失败: ' + err.message;
      verifyResult.className = 'verify-meta err';
    });
  });

  // Verify relative selector within current anchor
  if ($('btnVerifyRelative')) {
    $('btnVerifyRelative').addEventListener('click', () => {
      if (!currentTabId) {
        verifyResult.textContent = '未关联页面';
        verifyResult.className = 'verify-meta err';
        return;
      }
      verifyResult.textContent = '校验相对选择器中...';
      verifyResult.className = 'verify-meta';
      send('verifyRelative', {
        tabId: currentTabId,
        payload: {
          anchorSelector: anchorSelectorInput.value,
          relativeSelector: relativeSelectorInput.value,
        },
      }).then((res) => {
        if (res && res.error) {
          verifyResult.textContent = '校验相对失败: ' + res.error;
          verifyResult.className = 'verify-meta err';
          return;
        }
        const total = res.total ?? res.count ?? 0;
        const anchorCount = res.anchorCount ?? 0;
        const uniqueItems = res.uniqueItems ?? 0;
        if (anchorCount > 0 && uniqueItems === anchorCount) {
          verifyResult.textContent = `相对选择器在每个锚点内唯一匹配 ✓（共 ${anchorCount} 项）`;
          verifyResult.className = 'verify-meta ok';
        } else if (total === 0) {
          verifyResult.textContent = '相对选择器未匹配到元素';
          verifyResult.className = 'verify-meta err';
        } else {
          verifyResult.textContent = `相对选择器匹配 ${total} 个元素，${uniqueItems}/${anchorCount} 项唯一`;
          verifyResult.className = 'verify-meta err';
        }
      }).catch((err) => {
        verifyResult.textContent = '校验相对失败: ' + err.message;
        verifyResult.className = 'verify-meta err';
      });
    });
  }

  // Toggle relative resolution
  if (useRelativeChk) {
    useRelativeChk.addEventListener('change', () => {
      anchorCard.classList.toggle('disabled', !useRelativeChk.checked);
    });
  }

  function resetSaveButton() {
    const btn = $('btnSave');
    btn.disabled = false;
    btn.textContent = '保存';
  }

  function markSavedButton() {
    const btn = $('btnSave');
    btn.disabled = true;
    btn.textContent = '已保存';
  }

  // Save
  $('btnSave').addEventListener('click', () => {
    const btn = $('btnSave');
    if (btn.disabled) return;
    if (!selectedWorkflowId) {
      verifyResult.textContent = '请先选择流程';
      verifyResult.className = 'verify-meta err';
      $('workflowSelect').focus();
      return;
    }
    const payload = {
      workflowId: parseInt(selectedWorkflowId, 10),
      name: elName.value.trim(),
      selector: selectorPreview.value,
      selectorFamily: choiceFamily(activeChoice),
      tag: elementData?.tag,
      id: elementData?.id || '',
      classes: elementData?.classes || [],
      attrs: elementData?.attrs || {},
      text: elementData?.inner_text?.slice(0, 50) || '',
      pageUrl: elementData?.pageUrl || '',
      path: elementData?.path || [],
      candidates: elementData?.candidates,
      screenshot: elementData?.screenshot,
      listContainer: elementData?.listContainer || '',
      listItem: elementData?.listItem || '',
      listSize: elementData?.listSize || 0,
    };
    // Loop-relative anchoring. When the user unchecks "相对解析" we persist an
    // empty relative selector so the runtime falls back to global resolution.
    const relValue = (relativeSelectorInput.value || '').trim();
    if (useRelativeChk.checked && relValue) {
      payload.relativeSelector = relValue;
      payload.anchorSelector = (anchorSelectorInput.value || '').trim();
      payload.anchorElementName = activeAnchorSelect?.value || '';
      payload.anchorMode = relativeManuallyEdited
        ? 'manual'
        : (elementData?.anchorMode || 'anchor-first');
    } else {
      payload.relativeSelector = '';
      payload.anchorSelector = '';
      payload.anchorElementName = '';
      payload.anchorMode = 'none';
    }
    send('saveElement', payload)
      .then(() => {
        verifyResult.textContent = '已保存';
        verifyResult.className = 'verify-meta ok';
        markSavedButton();
      })
      .catch((err) => {
        verifyResult.textContent = '保存失败: ' + err.message;
        verifyResult.className = 'verify-meta err';
      });
  });

  // Cancel
  $('btnCancel').addEventListener('click', () => {
    // Reset UI to empty state
    elementData = null;
    selectedPathIndex = -1;
    selectedCandidateType = null;
    pathEnabled = [];
    attrEnabled = {};
    elName.value = '';
    selectorPreview.value = '';
    if (anchorCard) anchorCard.style.display = 'none';
    if (relativeSelectorInput) relativeSelectorInput.value = '';
    if (anchorSelectorInput) anchorSelectorInput.value = '';
    relativeManuallyEdited = false;
    verifyResult.textContent = '点击"校验元素"查看匹配结果';
    verifyResult.className = 'verify-meta';
    screenshotPanel.innerHTML = '<div class="screenshot-empty">暂无截图</div>';
    updateScreenshotToggle(null);
    setScreenshotOpen(false);
    domPanel.innerHTML = '';
    $('candidatesList').innerHTML = '';
    propList.innerHTML = '';
    resetSaveButton();
  });

  // Connection status dot
  async function updateConnectionStatus() {
    try {
      const resp = await chrome.runtime.sendMessage({ action: 'getConnectionStatus' });
      const dot = $('connDot');
      if (resp?.connected) {
        dot.classList.add('online');
        dot.title = '已连接';
      } else {
        dot.classList.remove('online');
        dot.title = '未连接';
      }
    } catch (e) {
      const dot = $('connDot');
      dot.classList.remove('online');
      dot.title = '未连接';
    }
  }

  // Environment switch
  async function initEnv() {
    const cfg = await chrome.storage.local.get(['backendPort']);
    const envSelect = $('envSelect');
    envSelect.value = cfg.backendPort || '8811';
    await updateConnectionStatus();
  }

  async function checkConnection() {
    const dot = $('connDot');
    dot.classList.remove('online');
    dot.classList.add('checking');
    dot.title = '检测中...';
    try {
      const cfg = await chrome.storage.local.get(['backendPort']);
      await chrome.runtime.sendMessage({
        action: 'reconnect',
        host: 'localhost',
        port: parseInt(cfg.backendPort || '8811', 10),
      });
      await new Promise((r) => setTimeout(r, 1500));
      await updateConnectionStatus();
    } catch (err) {
      dot.classList.remove('online');
      dot.title = '未连接';
    } finally {
      dot.classList.remove('checking');
    }
  }

  $('envSelect').addEventListener('change', async (e) => {
    const port = e.target.value;
    await chrome.storage.local.set({ backendPort: port });
    await checkConnection();
    // Reload workflows from new backend
    loadWorkflows();
  });

  $('connDot').addEventListener('click', () => {
    checkConnection();
  });

  // Workflow select
  $('workflowSelect').addEventListener('change', (e) => {
    selectedWorkflowId = e.target.value;
    if (selectedWorkflowId) {
      localStorage.setItem('rpa_selected_workflow_id', selectedWorkflowId);
    } else {
      localStorage.removeItem('rpa_selected_workflow_id');
    }
    // Switching flows invalidates any active anchor (different element set).
    clearActiveAnchor();
    loadWorkflowElements(selectedWorkflowId);
  });

  // ─── Init ────────────────────────────────────────────────────────

  // Default to recommend mode; state is kept in sync with HTML active classes.
  setEditMode('recommend');

  // Load workflows and capture payload when panel opens
  initEnv();
  loadWorkflows();
  loadPayloadFromBackground();

  // 通知 background：side panel 已打开/关闭，控制所有标签页的 Alt 捕获开关
  const panelPort = chrome.runtime.connect({ name: 'sidePanel' });
  panelPort.postMessage({ action: 'sidePanelOpened' });
})();
