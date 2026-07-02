/**
 * sidepanel.js — Chrome Side Panel UI for element editor.
 *
 * Communicates via chrome.runtime.sendMessage instead of iframe postMessage.
 * Global capture and associated capture each have an independent UI panel
 * (recommend list + manual editor + selector preview) with its own state.
 */
(function () {
  'use strict';

  // ─── Panel layout registry ───────────────────────────────────────

  const PANELS = {
    new: {
      name: 'new',
      panelId: 'globalCapturePanel',
      modeRecommendId: 'globalModeRecommend',
      modeManualId: 'globalModeManual',
      recommendPanelId: 'globalRecommendPanel',
      manualPanelId: 'globalManualPanel',
      candidatesListId: 'globalCandidatesList',
      domPanelId: 'globalDomPanel',
      propPanelId: 'globalPropPanel',
      domCollapseHeaderId: 'globalDomCollapseHeader',
      domCollapseBodyId: 'globalDomCollapseBody',
      propCollapseHeaderId: 'globalPropCollapseHeader',
      propCollapseBodyId: 'globalPropCollapseBody',
      choiceBtnClass: 'global-choice-btn',
      selectorPreviewId: 'globalSelectorPreview',
    },
    child: {
      name: 'child',
      panelId: 'assocCapturePanel',
      modeRecommendId: 'assocModeRecommend',
      modeManualId: 'assocModeManual',
      recommendPanelId: 'assocRecommendPanel',
      manualPanelId: 'assocManualPanel',
      candidatesListId: 'assocCandidatesList',
      domPanelId: 'assocDomPanel',
      propPanelId: 'assocPropPanel',
      domCollapseHeaderId: 'assocDomCollapseHeader',
      domCollapseBodyId: 'assocDomCollapseBody',
      propCollapseHeaderId: 'assocPropCollapseHeader',
      propCollapseBodyId: 'assocPropCollapseBody',
      choiceBtnClass: 'assoc-choice-btn',
      selectorPreviewId: 'assocRelativeSelectorInput',
    },
  };

  function getPanelIds(mode) {
    return PANELS[mode === 'child' ? 'child' : 'new'];
  }

  // ─── State ─────────────────────────────────────────────────────────

  function makeBaseState() {
    return {
      elementData: null,
      selectedPathIndex: -1,
      activeChoice: 'css',
      selectedCandidateType: null,
      pathEnabled: [],
      attrEnabled: {},
      editMode: 'recommend',
      selectorValue: '',
    };
  }

  const globalState = makeBaseState();
  const assocState = Object.assign(makeBaseState(), {
    relativeSelectorValue: '',
    anchorSelector: '',
    anchorElementName: '',
    relativeManuallyEdited: false,
    anchorPathIndex: -1,
  });

  let currentState = globalState;
  let captureMode = 'new';

  let currentTabId = null;
  let workflows = [];
  let selectedWorkflowId = localStorage.getItem('rpa_selected_workflow_id') || '';
  let screenshotOpen = false;

  // Existing elements of the selected workflow, loaded for anchor selection.
  let workflowElements = [];
  let activeAnchorName = '';
  let currentAnchorChain = null;

  // ─── Helpers ───────────────────────────────────────────────────────

  const $ = (id) => document.getElementById(id);

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

  function stripSelectorPrefix(sel) {
    if (!sel) return '';
    const lowered = sel.trim().toLowerCase();
    if (lowered.startsWith('css:')) return sel.slice(4).trim();
    if (lowered.startsWith('xpath:')) return sel.slice(6).trim();
    if (lowered.startsWith('drission:')) return sel.slice(9).trim();
    return sel.trim();
  }

  function buildLocalChain(targetName) {
    const chain = [];
    const seen = new Set();
    let name = targetName;
    while (name) {
      if (seen.has(name)) break;
      seen.add(name);
      const el = workflowElements.find((e) => e.name === name);
      if (!el) break;
      chain.unshift({
        name: el.name,
        elementKind: el.elementKind,
        selector: el.webSelector || el.relativeSelector || '',
      });
      name = el.anchorElementName;
    }
    return chain.filter((node) => node.selector);
  }

  function formatCombinedSelector(chain) {
    if (!chain || !chain.length) return '';
    const css = chain.map((n) => stripSelectorPrefix(n.selector)).filter(Boolean).join(' ');
    return css ? 'css:' + css : '';
  }

  function getSelectorPreview(state) {
    const ids = getPanelIds(state === assocState ? 'child' : 'new');
    return $(ids.selectorPreviewId);
  }

  function getVerifyResult() {
    return $('verifyResult');
  }

  // ─── Screenshot toggle ─────────────────────────────────────────────

  const screenshotPanel = $('screenshotPanel');
  const screenshotToggle = $('screenshotToggle');
  const elName = $('elName');

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

  // ─── Collapsible sections ──────────────────────────────────────────

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

  // ─── Capture mode tabs ─────────────────────────────────────────────

  function refreshAnchorBadge() {
    const badge = $('anchorBadge');
    const name = activeAnchorSelect && activeAnchorSelect.value;
    if (badge) badge.textContent = name ? `基于 ${name}` : '';
  }

  function applyCaptureMode(mode) {
    captureMode = mode === 'child' ? 'child' : 'new';
    const child = captureMode === 'child';
    currentState = child ? assocState : globalState;

    document.querySelectorAll('.capture-tab').forEach((b) => {
      b.classList.toggle('active', b.dataset.capmode === captureMode);
    });

    const anchorRow = $('activeAnchorRow');
    if (anchorRow) anchorRow.style.display = child ? '' : 'none';

    Object.values(PANELS).forEach((p) => {
      const panel = $(p.panelId);
      if (panel) panel.classList.toggle('active', p.name === (child ? 'child' : 'new'));
    });

    const globalSelectorSection = $('globalSelectorSection');
    const assocSelectorSection = $('assocSelectorSection');
    if (globalSelectorSection) globalSelectorSection.style.display = child ? 'none' : 'block';
    if (assocSelectorSection) assocSelectorSection.style.display = child ? 'block' : 'none';

    if (!child && activeAnchorSelect && activeAnchorSelect.value) {
      // Leaving associated mode drops any active anchor + page highlight.
      activeAnchorSelect.value = '';
      updateAnchorSelectLabel('');
      applyActiveAnchor('');
    }

    refreshAnchorBadge();

    // Re-render the active panel from its stored state.
    setEditMode(currentState.editMode, currentState);
    if (currentState.elementData) {
      renderDomTree(currentState);
      renderProperties(currentState);
      renderCandidates(currentState);
      syncChoiceButtons(currentState);
    }
  }

  document.querySelectorAll('.capture-tab').forEach((btn) => {
    btn.addEventListener('click', () => applyCaptureMode(btn.dataset.capmode));
  });

  // ─── Mode toggle (Recommend / Manual) ──────────────────────────────

  function setEditMode(mode, state) {
    state.editMode = mode;
    const ids = getPanelIds(state === assocState ? 'child' : 'new');
    $(ids.modeRecommendId)?.classList.toggle('active', mode === 'recommend');
    $(ids.modeManualId)?.classList.toggle('active', mode === 'manual');
    $(ids.recommendPanelId)?.classList.toggle('active', mode === 'recommend');
    $(ids.manualPanelId)?.classList.toggle('active', mode === 'manual');

    if (mode === 'manual') {
      setCollapsibleOpen(ids.domCollapseHeaderId, ids.domCollapseBodyId, true);
      setCollapsibleOpen(ids.propCollapseHeaderId, ids.propCollapseBodyId, true);
    } else {
      setCollapsibleOpen(ids.domCollapseHeaderId, ids.domCollapseBodyId, false);
      setCollapsibleOpen(ids.propCollapseHeaderId, ids.propCollapseBodyId, false);
      // Switching back to recommend in associated mode restores the captured
      // relative candidates. Manual edits are kept in the relative textarea but
      // recommend mode shows the pre-computed list again.
      if (state === assocState) {
        state.relativeManuallyEdited = false;
        const relInput = $(ids.selectorPreviewId);
        const relFirst = state.elementData?.relativeCandidates?.[0];
        if (relFirst) {
          state.activeChoice = relFirst.family || 'css';
          syncChoiceButtons(state);
          if (relInput) relInput.value = relFirst.syntax;
          state.relativeSelectorValue = relFirst.syntax;
          anchorModeLabel.textContent = '锚定';
          verifyResult.textContent = `${relFirst.matchCount === 1 ? '唯一匹配' : relFirst.matchCount + ' 匹配'} | score:${relFirst.score}`;
          verifyResult.className = 'verify-meta ' + (relFirst.matchCount === 1 ? 'ok' : '');
          broadcastSelectedCandidate();
        } else if (relInput) {
          relInput.value = state.relativeSelectorValue || '';
        }
      }
    }
  }

  $('globalModeRecommend')?.addEventListener('click', () => setEditMode('recommend', globalState));
  $('globalModeManual')?.addEventListener('click', () => setEditMode('manual', globalState));
  $('assocModeRecommend')?.addEventListener('click', () => setEditMode('recommend', assocState));
  $('assocModeManual')?.addEventListener('click', () => setEditMode('manual', assocState));

  // ─── Runtime Message API ───────────────────────────────────────────

  function send(action, payload) {
    return chrome.runtime.sendMessage({ action, payload });
  }

  function broadcastSelectedCandidate() {
    const ids = getPanelIds(captureMode);
    const selector = $(ids.selectorPreviewId)?.value || '';
    const type = currentState.selectedCandidateType || inferFamilyFromSelector(selector) || choiceFamily(currentState.activeChoice);
    if (!selector) return;
    chrome.runtime.sendMessage({ action: 'selectCandidate', payload: { selector, type } }).catch(() => {});
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (!msg) return;
    if (msg.action === 'verifyResultBroadcast' && msg.payload) {
      showVerifyResult(msg.payload);
    }
    if (msg.action === 'newCaptureAvailable') {
      loadPayloadFromBackground();
    }
  });

  // ─── Load workflows and anchor elements ────────────────────────────

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

  // ─── Anchor element control ────────────────────────────────────────

  const activeAnchorSelect = $('activeAnchorSelect');
  const activeAnchorSelectBtn = $('activeAnchorSelectBtn');
  const activeAnchorSelectLabel = $('activeAnchorSelectLabel');
  const activeAnchorTreeDropdown = $('activeAnchorTreeDropdown');
  const btnClearActiveAnchor = $('btnClearActiveAnchor');
  const activeAnchorStatus = $('activeAnchorStatus');
  const anchorSelectorInput = $('anchorSelectorInput');
  const anchorModeLabel = $('anchorMode');

  let anchorExpandedNames = new Set();

  function buildElementTree(elements) {
    const map = new Map();
    elements.forEach((el) => {
      map.set(el.name, { ...el, children: [] });
    });
    const roots = [];
    map.forEach((node) => {
      if (node.anchorElementName && map.has(node.anchorElementName)) {
        map.get(node.anchorElementName).children.push(node);
      } else {
        roots.push(node);
      }
    });
    return roots;
  }

  function renderAnchorTree(nodes, container, selectedName) {
    container.innerHTML = '';
    if (nodes.length === 0) {
      container.innerHTML = '<div class="anchor-tree-row"><span class="spacer"></span><span class="label">暂无元素</span></div>';
      return;
    }
    const chevronRight = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>`;
    const chevronDown = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>`;
    function appendNode(node, depth) {
      const hasChildren = node.children && node.children.length > 0;
      const isExpanded = anchorExpandedNames.has(node.name);
      const paddingLeft = 6 + depth * 16;
      const guideLeft = paddingLeft + 8;

      const wrapper = document.createElement('div');
      wrapper.className = 'anchor-tree-node';

      const row = document.createElement('div');
      row.className = 'anchor-tree-row' + (node.name === selectedName ? ' selected' : '');
      row.style.paddingLeft = paddingLeft + 'px';
      row.dataset.name = node.name;

      const toggle = document.createElement('span');
      toggle.className = hasChildren ? 'toggle' : 'spacer';
      if (hasChildren) {
        toggle.innerHTML = isExpanded ? chevronDown : chevronRight;
        toggle.addEventListener('click', (e) => {
          e.stopPropagation();
          if (anchorExpandedNames.has(node.name)) anchorExpandedNames.delete(node.name);
          else anchorExpandedNames.add(node.name);
          renderAnchorTree(nodes, container, selectedName);
        });
      }
      row.appendChild(toggle);

      const label = document.createElement('span');
      label.className = 'label';
      label.textContent = node.name;
      row.appendChild(label);

      row.addEventListener('click', () => {
        activeAnchorSelect.value = node.name;
        activeAnchorName = node.name;
        updateAnchorSelectLabel(node.name);
        activeAnchorTreeDropdown.style.display = 'none';
        activeAnchorSelect.dispatchEvent(new Event('change'));
      });

      wrapper.appendChild(row);
      container.appendChild(wrapper);

      if (hasChildren && isExpanded) {
        node.children.forEach((child) => appendNode(child, depth + 1));
      }
    }
    nodes.forEach((node) => appendNode(node, 0));
  }

  function updateAnchorSelectLabel(name) {
    if (activeAnchorSelectLabel) activeAnchorSelectLabel.textContent = name || '请选择锚点元素';
  }

  function renderActiveAnchorOptions() {
    if (!activeAnchorSelect) return;
    const current = activeAnchorName;
    const excludeName = (elName?.value || currentState.elementData?.name || '').trim();
    const anchorEls = workflowElements.filter((el) => el?.name && el.name !== excludeName);
    const placeholderText = workflowElements.length === 0 ? '先捕获全局元素' : '请选择锚点元素';
    activeAnchorSelect.innerHTML = `<option value="">${placeholderText}</option>`;
    anchorEls.forEach((el) => {
      const opt = document.createElement('option');
      opt.value = el.name;
      opt.textContent = el.name;
      activeAnchorSelect.appendChild(opt);
    });
    anchorExpandedNames = new Set(anchorEls.map((el) => el.name));
    const tree = buildElementTree(anchorEls);
    renderAnchorTree(tree, activeAnchorTreeDropdown, current);
    if (current && current !== excludeName && anchorEls.some((el) => el.name === current)) {
      activeAnchorSelect.value = current;
    } else {
      activeAnchorSelect.value = '';
      activeAnchorName = '';
    }
    updateAnchorSelectLabel(activeAnchorName);
  }

  async function applyActiveAnchor(name) {
    activeAnchorName = name || '';
    currentAnchorChain = null;
    if (!activeAnchorName) {
      if (activeAnchorStatus) activeAnchorStatus.textContent = '';
      try { await send('setActiveAnchor', { anchorSelector: '', anchorElementName: '' }); } catch (_e) {}
      return;
    }
    const el = workflowElements.find((e) => e.name === activeAnchorName);
    let anchorSelector = el?.webSelector || '';
    let anchorChain = null;
    const needsChain = !anchorSelector || el?.elementKind === 'child';
    if (needsChain) {
      if (activeAnchorStatus) activeAnchorStatus.textContent = '计算链...';
      try {
        const chainResp = await send('getElementChain', { workflowId: selectedWorkflowId, name: activeAnchorName });
        if (chainResp && !chainResp.error && chainResp.chain && chainResp.chain.length) {
          anchorChain = chainResp.chain;
          anchorSelector = chainResp.combined_css ? 'css:' + chainResp.combined_css
            : (chainResp.combined_xpath ? 'xpath:' + chainResp.combined_xpath : '');
        }
      } catch (_e) {}
      if (!anchorChain) {
        anchorChain = buildLocalChain(activeAnchorName);
        if (anchorChain && anchorChain.length) {
          anchorSelector = formatCombinedSelector(anchorChain);
        }
      }
    }
    if (!anchorSelector && (!anchorChain || !anchorChain.length)) {
      if (activeAnchorStatus) activeAnchorStatus.textContent = '无选择器';
      return;
    }
    currentAnchorChain = anchorChain;
    anchorSelectorInput.value = anchorSelector || '';
    if (activeAnchorStatus) activeAnchorStatus.textContent = '定位中...';
    try {
      const res = await send('setActiveAnchor', {
        anchorSelector,
        anchorElementName: activeAnchorName,
        anchorChain,
      });
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
    updateAnchorSelectLabel('');
    currentAnchorChain = null;
    _clearAssocElementData();
    applyActiveAnchor('');
    refreshAnchorBadge();
  }

  function _clearAssocElementData() {
    assocState.elementData = null;
    assocState.relativeSelectorValue = '';
    assocState.selectedPathIndex = -1;
    assocState.pathEnabled = [];
    assocState.attrEnabled = {};
    const ids = getPanelIds('child');
    const relInput = $(ids.selectorPreviewId);
    if (relInput) relInput.value = '';
    anchorSelectorInput.value = '';
    if (captureMode === 'child') {
      renderDomTree(assocState);
      renderProperties(assocState);
      renderCandidates(assocState);
    }
  }

  if (activeAnchorSelect) {
    activeAnchorSelect.addEventListener('change', () => {
      const name = activeAnchorSelect.value;
      // 重选锚点元素后清空此前捕获的子元素
      _clearAssocElementData();
      applyActiveAnchor(name);
      if (name) {
        computeRelativeForSelectedAnchor();
      }
      refreshAnchorBadge();
    });
  }

  if (btnClearActiveAnchor) {
    btnClearActiveAnchor.addEventListener('click', () => {
      clearActiveAnchor();
    });
  }

  if (activeAnchorSelectBtn && activeAnchorTreeDropdown) {
    activeAnchorSelectBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = activeAnchorTreeDropdown.style.display === 'block';
      activeAnchorTreeDropdown.style.display = isOpen ? 'none' : 'block';
      if (!isOpen) {
        renderActiveAnchorOptions();
      }
    });

    document.addEventListener('click', (e) => {
      if (activeAnchorTreeDropdown.style.display === 'none') return;
      const wrap = activeAnchorSelectBtn.closest('.anchor-select-wrap');
      if (wrap && !wrap.contains(e.target)) {
        activeAnchorTreeDropdown.style.display = 'none';
      }
    });
  }

  if (elName) {
    elName.addEventListener('input', () => {
      renderActiveAnchorOptions();
    });
  }

  async function computeRelativeForSelectedAnchor(silent) {
    const anchorEl = getCurrentAnchorElement();
    if (!anchorEl) {
      anchorSelectorInput.value = '';
      const ids = getPanelIds('child');
      const relInput = $(ids.selectorPreviewId);
      if (relInput) relInput.value = '';
      assocState.relativeSelectorValue = '';
      currentAnchorChain = null;
      return;
    }
    let anchorChain = currentAnchorChain;
    let anchorSelector = anchorSelectorInput.value || anchorEl.webSelector || '';
    const needsChain = !anchorSelector || anchorEl.elementKind === 'child';
    if (needsChain && (!anchorChain || !anchorChain.length)) {
      try {
        const chainResp = await send('getElementChain', { workflowId: selectedWorkflowId, name: anchorEl.name });
        if (chainResp && !chainResp.error && chainResp.chain && chainResp.chain.length) {
          anchorChain = chainResp.chain;
          anchorSelector = chainResp.combined_css ? 'css:' + chainResp.combined_css
            : (chainResp.combined_xpath ? 'xpath:' + chainResp.combined_xpath : '');
        }
      } catch (_e) {}
      if (!anchorChain || !anchorChain.length) {
        anchorChain = buildLocalChain(anchorEl.name);
        anchorSelector = formatCombinedSelector(anchorChain);
      }
      currentAnchorChain = anchorChain;
      anchorSelectorInput.value = anchorSelector || '';
    }

    const targetSelector = assocState.selectorValue;
    if (!targetSelector || (!anchorSelector && (!anchorChain || !anchorChain.length)) || !currentTabId) {
      if (!silent) {
        verifyResult.textContent = '请确认目标元素和锚点元素';
        verifyResult.className = 'verify-meta err';
      }
      return;
    }
    if (!silent) {
      verifyResult.textContent = '计算相对选择器中...';
      verifyResult.className = 'verify-meta';
    }
    try {
      const res = await send('computeRelativeFromAnchor', {
        tabId: currentTabId,
        payload: { targetSelector, anchorSelector, anchorChain },
      });
      if (res && res.error) {
        if (!silent) {
          verifyResult.textContent = '相对选择器计算失败: ' + res.error;
          verifyResult.className = 'verify-meta err';
        }
        return;
      }
      const ids = getPanelIds('child');
      const relInput = $(ids.selectorPreviewId);
      if (relInput) relInput.value = res.relativeSelector || '';
      assocState.relativeSelectorValue = res.relativeSelector || '';
      const family = inferFamilyFromSelector(res.relativeSelector) || 'css';
      if (family !== assocState.activeChoice) {
        assocState.activeChoice = family;
        syncChoiceButtons(assocState);
      }
      assocState.relativeManuallyEdited = false;
      if (!silent) {
        anchorModeLabel.textContent = '锚定';
        verifyResult.textContent = '相对选择器已生成: ' + (res.relativeSelector || '');
        verifyResult.className = 'verify-meta ok';
      }
      broadcastSelectedCandidate();
    } catch (err) {
      if (!silent) {
        verifyResult.textContent = '计算失败: ' + err.message;
        verifyResult.className = 'verify-meta err';
      }
    }
  }

  // ─── Load capture payload ──────────────────────────────────────────

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
    resetSaveButton();
    if (!data) return;

    const anchored = (data?.elementKind === 'child') || !!(data?.relativeSelector || data?.anchorElementName);
    applyCaptureMode(anchored ? 'child' : 'new');

    const state = currentState;
    state.elementData = data;

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
    state.pathEnabled = path.map(() => true);
    state.attrEnabled = {};
    path.forEach((_, i) => { state.attrEnabled[i] = {}; });

    // Default: select the deepest (target) level
    state.selectedPathIndex = path.length - 1;

    // Restore active choice from selector prefix or payload family.
    state.activeChoice = inferFamilyFromSelector(data.selector) || data.selectorFamily || 'css';
    syncChoiceButtons(state);

    renderDomTree(state);
    renderProperties(state);

    if (state === globalState) {
      // Global mode: select best global candidate and update global selector preview.
      const first = (data.candidates || []).find((c) => {
        const f = c.family || c.type || 'css';
        return f === 'css' || f === 'xpath';
      });
      if (first) {
        state.activeChoice = first.family || first.type || 'css';
        syncChoiceButtons(state);
        state.selectorValue = first.syntax;
        const preview = $(getPanelIds('new').selectorPreviewId);
        if (preview) preview.value = first.syntax;
        state.selectedCandidateType = first.family || first.type || choiceFamily(state.activeChoice);
        applyCandidateToUI(first, state);
        const statusText = first.matchCount === 1 ? '唯一匹配' : (first.isList ? `列表 (${first.matchCount}个)` : first.matchCount + ' 匹配');
        verifyResult.textContent = `${statusText} | score:${first.score}`;
        verifyResult.className = 'verify-meta ' + (first.matchCount === 1 ? 'ok' : '');
        broadcastSelectedCandidate();
      } else {
        updateSelector(state);
      }
      renderCandidates(state);
    } else {
      // Associated mode: load anchor info and relative selector.
      assocState.relativeManuallyEdited = false;
      assocState.selectorValue = data.selector || '';
      assocState.anchorPathIndex = data?.anchorPathIndex ?? -1;
      const rel = data?.relativeSelector || '';
      const anchorElName = data?.anchorElementName || '';
      assocState.relativeSelectorValue = rel;

      // Keep a global target selector for backend reference even though the UI
      // now builds the relative selector directly from the sub-path.
      if (!assocState.selectorValue) {
        const bestGlobal = (data.candidates || []).find((c) => {
          const f = c.family || c.type || 'css';
          return f === 'css' || f === 'xpath';
        });
        if (bestGlobal) assocState.selectorValue = bestGlobal.syntax;
      }
      const relInput = $(getPanelIds('child').selectorPreviewId);
      if (relInput) relInput.value = rel;
      const family = inferFamilyFromSelector(rel) || 'css';
      if (family !== assocState.activeChoice) {
        assocState.activeChoice = family;
        syncChoiceButtons(assocState);
      }
      anchorSelectorInput.value = data?.anchorSelector || '';
      if (activeAnchorSelect && anchorElName) {
        activeAnchorName = anchorElName;
        renderActiveAnchorOptions();
        activeAnchorSelect.value = anchorElName;
      }
      const mode = data?.anchorMode || '';
      anchorModeLabel.textContent = mode === 'manual' ? '手动' : (mode === 'anchor-first' ? '锚定' : '无');

      // Pre-select best relative candidate and apply it to the manual editor.
      // The manual editor now shows only the sub-path below the anchor.
      if (data.relativeCandidates?.length) {
        const relFirst = data.relativeCandidates[0];
        if (relFirst) {
          assocState.activeChoice = relFirst.family || 'css';
          syncChoiceButtons(assocState);
          if (relInput) relInput.value = relFirst.syntax;
          assocState.relativeSelectorValue = relFirst.syntax;
          assocState.relativeManuallyEdited = false;
          anchorModeLabel.textContent = '锚定';
          verifyResult.textContent = `${relFirst.matchCount === 1 ? '唯一匹配' : relFirst.matchCount + ' 匹配'} | score:${relFirst.score}`;
          verifyResult.className = 'verify-meta ' + (relFirst.matchCount === 1 ? 'ok' : '');
          applyCandidateToUI(relFirst, assocState);
          broadcastSelectedCandidate();
        }
      } else {
        updateSelector(assocState);
      }
      renderCandidates(assocState);
    }

    refreshAnchorBadge();
  }

  // ─── DOM Tree rendering ────────────────────────────────────────────

  function renderDomTree(state) {
    const ids = getPanelIds(state === assocState ? 'child' : 'new');
    const domPanel = $(ids.domPanelId);
    if (!domPanel) return;
    domPanel.innerHTML = '';
    const path = state.elementData?.path || [];

    // In associated mode only the sub-path below the anchor is editable.
    const isAssoc = state === assocState;
    const startIdx = isAssoc ? Math.max(0, state.anchorPathIndex + 1) : 0;
    if (isAssoc && state.anchorPathIndex >= 0 && state.anchorPathIndex < path.length) {
      const anchorNode = path[state.anchorPathIndex];
      const header = document.createElement('div');
      header.className = 'dom-item';
      header.style.color = '#1677ff';
      header.style.fontWeight = '500';
      header.style.cursor = 'default';
      const anchorPreview = [anchorNode.tag, anchorNode.id ? '#' + anchorNode.id : '', (anchorNode.classes || []).slice(0, 2).map(c => '.' + c).join('')].filter(Boolean).join('');
      header.textContent = `↳ 锚点: ${anchorPreview}`;
      domPanel.appendChild(header);
    }

    for (let i = startIdx; i < path.length; i++) {
      const node = path[i];
      const row = document.createElement('div');
      row.className = 'dom-item' + (i === state.selectedPathIndex ? ' active' : '');

      const hasAttr = Object.keys(state.attrEnabled[i] || {}).some((k) => state.attrEnabled[i][k]);
      if (hasAttr) {
        row.style.borderLeft = '3px solid #fa8c16';
        row.style.paddingLeft = '7px';
      }

      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = state.pathEnabled[i];
      cb.addEventListener('change', () => {
        state.pathEnabled[i] = cb.checked;
        updateSelector(state);
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
        state.selectedPathIndex = i;
        renderDomTree(state);
        renderProperties(state);
      });

      domPanel.appendChild(row);
    }
  }

  // ─── Apply candidate selection to DOM tree / properties ────────────

  function applyCandidateToUI(c, state) {
    if (!state.elementData?.path?.length) return;
    const path = state.elementData.path;

    // Reset
    state.pathEnabled = path.map(() => false);
    state.attrEnabled = {};
    path.forEach((_, i) => { state.attrEnabled[i] = {}; });

    // Associated mode: map a relative candidate to the sub-path below the anchor.
    if (state === assocState && state.anchorPathIndex >= 0) {
      let syntax = c.syntax;
      const family = c.family || c.type || choiceFamily(state.activeChoice);
      if (syntax.startsWith('css:')) syntax = syntax.slice(4);
      else if (syntax.startsWith('xpath:')) syntax = syntax.slice(6);
      else if (syntax.startsWith('verse:')) {
        state.pathEnabled[path.length - 1] = false;
        state.selectedPathIndex = path.length - 1;
        state.attrEnabled[path.length - 1]['verse_fp'] = true;
        renderDomTree(state);
        renderProperties(state);
        return;
      }

      const isXPath = family === 'xpath';
      const segDelimiter = isXPath ? /\// : /\s*>\s*|\s+/;
      const segs = syntax.split(segDelimiter).filter(Boolean);
      const parseFn = isXPath ? parseXPathSeg : parseSeg;

      let pathIdx = state.anchorPathIndex + 1;
      for (const segStr of segs) {
        if (pathIdx >= path.length) break;
        const seg = parseFn(segStr);
        let matched = false;
        for (let i = pathIdx; i < path.length; i++) {
          if (segMatchesNode(seg, path[i])) {
            applySegToNode(seg, i, state);
            pathIdx = i + 1;
            matched = true;
            break;
          }
        }
        if (!matched) break;
      }
      state.selectedPathIndex = state.pathEnabled.lastIndexOf(true);
      renderDomTree(state);
      renderProperties(state);
      return;
    }

    let syntax = c.syntax;
    const family = c.family || c.type || choiceFamily(state.activeChoice);

    if (syntax.startsWith('css:')) syntax = syntax.slice(4);
    else if (syntax.startsWith('xpath:')) syntax = syntax.slice(6);
    else if (syntax.startsWith('verse:')) {
      state.pathEnabled[path.length - 1] = false;
      state.selectedPathIndex = path.length - 1;
      state.attrEnabled[path.length - 1]['verse_fp'] = true;
      renderDomTree(state);
      renderProperties(state);
      return;
    }

    if (c.pathMapping && c.pathMapping.length > 0) {
      const segs = family === 'xpath'
        ? syntax.split('/').filter(Boolean)
        : syntax.split(/\s*>\s*|\s+/).filter(Boolean);
      segs.forEach((segStr, idx) => {
        const pathIdx = c.pathMapping[idx];
        if (pathIdx === undefined) return;
        const seg = family === 'xpath' ? parseXPathSeg(segStr) : parseSeg(segStr);
        applySegToNode(seg, pathIdx, state);
      });
      state.selectedPathIndex = state.pathEnabled.lastIndexOf(true);
      renderDomTree(state);
      renderProperties(state);
      return;
    }

    if (syntax.startsWith('tag:')) {
      syntax = syntax.slice(4);
      syntax = syntax.replace(/@class=([a-zA-Z0-9_-]+)/g, '.$1');
      syntax = syntax.replace(/@([a-zA-Z0-9_-]+)=([^@]+)$/g, '[$1="$2"]');
    }

    if (/[+~]/.test(syntax) || syntax.startsWith('text=') || syntax.startsWith('@')) {
      state.pathEnabled[path.length - 1] = /[+~]/.test(syntax);
      state.selectedPathIndex = path.length - 1;

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
              state.attrEnabled[path.length - 1]['sib:' + idx] = true;
            });
          }
        }
      }

      renderDomTree(state);
      renderProperties(state);
      return;
    }

    function parseSeg(seg) {
      let tag = seg.match(/^([a-zA-Z0-9_*-]+)/)?.[1] || '';
      let id = seg.match(/#([a-zA-Z0-9_-]+)/)?.[1] || '';
      const classes = [...seg.matchAll(/\.([a-zA-Z0-9_-]+)/g)].map(m => m[1]);
      let attrs = [...seg.matchAll(/\[([a-zA-Z0-9_-]+)(?:=["']([^"']*)["'])?\]/g)];
      const nth = seg.match(/:nth-of-type\((\d+)\)/)?.[1] || '';
      const nthChild = seg.match(/:nth-child\((\d+)\)/)?.[1] || '';

      const idAttr = attrs.find(a => a[1] === 'id');
      if (idAttr && idAttr[2]) {
        id = idAttr[2];
        attrs = attrs.filter(a => a[1] !== 'id');
      }
      const classAttr = attrs.find(a => a[1] === 'class');
      if (classAttr && classAttr[2]) {
        classAttr[2].split(/\s+/).filter(Boolean).forEach(c => {
          if (!classes.includes(c)) classes.push(c);
        });
        attrs = attrs.filter(a => a[1] !== 'class');
      }

      return { tag, id, classes, attrs, nth, nthChild };
    }

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
          const unescaped = val.replace(/\\(.)/g, '$1');
          const actual = (node.attrs?.[name] || '').toString().trim();
          if (actual !== unescaped.trim()) return false;
        } else {
          if (!node.attrs?.hasOwnProperty(name)) return false;
        }
      }
      return true;
    }

    function applySegToNode(seg, i, state) {
      const node = path[i];
      state.pathEnabled[i] = !!(seg.tag && seg.tag !== '*');
      if (seg.id) state.attrEnabled[i]['id'] = true;
      seg.classes.forEach(c => { if (node.classes?.includes(c)) state.attrEnabled[i]['class:' + c] = true; });
      seg.attrs.forEach(([_, name]) => {
        if (node.attrs?.[name] !== undefined) state.attrEnabled[i][name] = true;
      });
      if (seg.nth) state.attrEnabled[i]['index-of-type'] = true;
      if (seg.nthChild) state.attrEnabled[i]['nth-child'] = true;
      if (seg.text) state.attrEnabled[i]['innerText'] = true;
    }

    function applySegToNodeLoose(seg, i, state) {
      const node = path[i];
      state.pathEnabled[i] = !!(seg.tag && seg.tag !== '*');
      if (seg.id && node.id) state.attrEnabled[i]['id'] = true;
      seg.classes.forEach(c => { if (node.classes?.includes(c)) state.attrEnabled[i]['class:' + c] = true; });
      seg.attrs.forEach(([_, name]) => {
        if (node.attrs?.[name] !== undefined) state.attrEnabled[i][name] = true;
      });
      if (seg.nth && node.index !== undefined) state.attrEnabled[i]['index-of-type'] = true;
      if (seg.nthChild && node.realIndex !== undefined) state.attrEnabled[i]['nth-child'] = true;
      if (seg.text) state.attrEnabled[i]['innerText'] = true;
    }

    const isXPath = family === 'xpath';
    const segDelimiter = isXPath ? /\// : /\s*>\s*|\s+/;

    const segs = syntax.split(segDelimiter).filter(Boolean);
    const parseFn = isXPath ? parseXPathSeg : parseSeg;

    if (segs.length >= 1) {
      let segIdx = segs.length - 1;
      for (let i = path.length - 1; i >= 0 && segIdx >= 0; i--) {
        const seg = parseFn(segs[segIdx]);
        if (!segMatchesNode(seg, path[i])) continue;
        applySegToNode(seg, i, state);
        segIdx--;
      }
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
            applySegToNodeLoose(seg, k, state);
            break;
          }
        }
      }
      state.selectedPathIndex = state.pathEnabled.lastIndexOf(true);
      renderDomTree(state);
      renderProperties(state);
      return;
    }

    state.pathEnabled[path.length - 1] = true;
    state.selectedPathIndex = path.length - 1;
    renderDomTree(state);
    renderProperties(state);
  }

  // ─── Candidates rendering ──────────────────────────────────────────

  function renderCandidates(state) {
    const ids = getPanelIds(state === assocState ? 'child' : 'new');
    const list = $(ids.candidatesListId);
    if (!list) return;
    list.innerHTML = '';

    if (state === assocState && state.elementData?.relativeCandidates?.length) {
      renderRelativeCandidates(state.elementData.relativeCandidates, list, state);
      return;
    }

    const cands = (state.elementData?.candidates || []).filter((c) => {
      const f = c.family || c.type || 'css';
      return f === 'css' || f === 'xpath';
    });
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
        state.activeChoice = family;
        syncChoiceButtons(state);
        const preview = $(ids.selectorPreviewId);
        if (preview) preview.value = c.syntax;
        if (state === assocState) {
          state.relativeSelectorValue = c.syntax;
          state.relativeManuallyEdited = false;
        } else {
          state.selectorValue = c.syntax;
        }
        state.selectedCandidateType = family;
        applyCandidateToUI(c, state);
        const statusText = c.matchCount === 1 ? '唯一匹配' : (c.isList ? `列表 (${c.matchCount}个)` : c.matchCount + ' 匹配');
        verifyResult.textContent = `${statusText} | score:${c.score}`;
        verifyResult.className = 'verify-meta ' + (c.matchCount === 1 ? 'ok' : '');
        broadcastSelectedCandidate();
      });

      list.appendChild(row);
    });
  }

  function renderRelativeCandidates(cands, list, state) {
    const ids = getPanelIds('child');
    const uniqueCands = [];
    const seen = new Set();
    for (const c of cands) {
      if (seen.has(c.syntax)) continue;
      seen.add(c.syntax);
      uniqueCands.push(c);
    }
    if (uniqueCands.length === 0) {
      list.innerHTML = '<div class="candidates-empty">暂无相对推荐方案</div>';
      return;
    }
    uniqueCands.forEach((c) => {
      const row = document.createElement('div');
      row.className = 'prop-row';
      row.style.cursor = 'pointer';
      row.title = c.syntax;

      const family = c.family || 'css';
      const familyPill = `<span style="background:${family === 'css' ? '#fff2e8' : '#f6ffed'};color:${family === 'css' ? '#fa8c16' : '#52c41a'};font-size:10px;padding:1px 5px;border-radius:3px;white-space:nowrap;border:1px solid ${family === 'css' ? '#ffbb96' : '#b7eb8f'};">${family.toUpperCase()}</span>`;
      const matchPill = c.matchCount === 1
        ? '<span style="background:#52c41a;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;white-space:nowrap;">唯一</span>'
        : `<span style="background:#f0f0f0;color:#666;font-size:10px;padding:1px 5px;border-radius:3px;white-space:nowrap;">${c.matchCount} 匹配</span>`;

      row.innerHTML = `
        <span style="flex:1;min-width:0;font-family:monospace;font-size:11px;color:#333;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(c.syntax)}</span>
        <span style="display:flex;gap:4px;flex-shrink:0;">${familyPill}${matchPill}</span>
      `;

      row.addEventListener('click', () => {
        state.activeChoice = family;
        syncChoiceButtons(state);
        const relInput = $(ids.selectorPreviewId);
        if (relInput) relInput.value = c.syntax;
        state.relativeSelectorValue = c.syntax;
        state.relativeManuallyEdited = false;
        anchorModeLabel.textContent = '锚定';
        verifyResult.textContent = `${c.matchCount === 1 ? '唯一匹配' : c.matchCount + ' 匹配'} | score:${c.score}`;
        verifyResult.className = 'verify-meta ' + (c.matchCount === 1 ? 'ok' : '');
        applyCandidateToUI(c, state);
        broadcastSelectedCandidate();
      });

      list.appendChild(row);
    });
  }

  function escapeHtml(str) {
    return str.replace(/[<>"&]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '"': '&quot;', '&': '&amp;' }[c]));
  }

  function syncChoiceButtons(state) {
    const ids = getPanelIds(state === assocState ? 'child' : 'new');
    document.querySelectorAll('.' + ids.choiceBtnClass).forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.choice === state.activeChoice);
    });
  }

  // ─── Properties rendering ──────────────────────────────────────────

  function renderProperties(state) {
    const ids = getPanelIds(state === assocState ? 'child' : 'new');
    const propList = $(ids.propPanelId);
    if (!propList) return;
    propList.innerHTML = '';
    const path = state.elementData?.path || [];
    if (state.selectedPathIndex < 0 || state.selectedPathIndex >= path.length) return;

    const node = path[state.selectedPathIndex];
    const enabledMap = state.attrEnabled[state.selectedPathIndex] || {};

    const section = document.createElement('div');
    section.className = 'prop-section';

    const title = document.createElement('div');
    title.className = 'prop-section-title';
    title.textContent = '属性';
    section.appendChild(title);

    if (node.id) addPropRow(section, 'id', node.id, enabledMap, state);

    (node.classes || []).forEach((cls) => addPropRow(section, 'class:' + cls, cls, enabledMap, state, false, 'class'));

    const attrs = node.attrs || {};
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === 'id' || k === 'class') return;
      addPropRow(section, k, v, enabledMap, state);
    });

    const parent = state.selectedPathIndex > 0 ? path[state.selectedPathIndex - 1] : null;
    if (parent) {
      const sameTagSiblings = parent.childrenTags?.filter((t) => t === node.tag).length || 1;
      if (sameTagSiblings > 1 || enabledMap['index-of-type']) {
        addPropRow(section, 'index-of-type', String((node.index || 0) + 1), enabledMap, state, false, 'index-of-type');
      }
      const allSiblings = parent.childrenTags?.length || 1;
      if (allSiblings > 1 || enabledMap['nth-child']) {
        addPropRow(section, 'nth-child', String((node.realIndex ?? node.index ?? 0) + 1), enabledMap, state, false, 'nth-child');
      }
    }

    propList.appendChild(section);

    const isTarget = state.selectedPathIndex === path.length - 1;
    if (isTarget) {
      const contentSection = document.createElement('div');
      contentSection.className = 'prop-section';

      const contentTitle = document.createElement('div');
      contentTitle.className = 'prop-section-title';
      contentTitle.textContent = '内容';
      contentSection.appendChild(contentTitle);

      if (state.elementData?.inner_text) {
        addPropRow(contentSection, 'innerText', state.elementData.inner_text, state.attrEnabled[state.selectedPathIndex] || {}, state, false, 'innerText');
      }
      if (state.elementData?.verse_fp) {
        addPropRow(contentSection, 'verse_fp', state.elementData.verse_fp, state.attrEnabled[state.selectedPathIndex] || {}, state, false, 'verse');
      }

      propList.appendChild(contentSection);

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
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = !!enabledMap['sib:' + idx];
            cb.addEventListener('change', () => {
              Object.keys(enabledMap).forEach((k) => {
                if (k.startsWith('sib:')) enabledMap[k] = false;
              });
              enabledMap['sib:' + idx] = cb.checked;
              updateSelector(state);
            });

            const nameEl = document.createElement('span');
            nameEl.style.flex = '1';
            nameEl.style.color = '#666';
            nameEl.textContent = `<${sib.tag}> ${label}`;

            row.appendChild(cb);
            row.appendChild(nameEl);
          } else {
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

  function addPropRow(container, name, value, enabledMap, state, disabled, displayName) {
    const row = document.createElement('div');
    row.className = 'prop-row';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = !!enabledMap[name];
    cb.disabled = !!disabled;
    cb.addEventListener('change', () => {
      enabledMap[name] = cb.checked;
      updateSelector(state);
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
    const defaultOp = name === 'innerText' || name.startsWith('class:') ? 'contains' : 'equals';
    matchEl.value = enabledMap[name + ':operator'] || defaultOp;
    matchEl.disabled = !!disabled;
    matchEl.addEventListener('change', () => {
      enabledMap[name + ':operator'] = matchEl.value;
      updateSelector(state);
    });

    const valEl = document.createElement('input');
    valEl.className = 'prop-value';
    valEl.value = value;
    valEl.disabled = !!disabled;
    valEl.addEventListener('input', () => {
      const node = state.elementData.path[state.selectedPathIndex];
      if (name.startsWith('class:')) {
        const oldCls = name.slice(6);
        const idx = node.classes.indexOf(oldCls);
        if (idx >= 0) node.classes[idx] = valEl.value;
      } else if (name === 'innerText' || name === 'verse_fp') {
        // Non-DOM attributes, do not write into node.attrs
      } else if (node.attrs) {
        node.attrs[name] = valEl.value;
      }
      updateSelector(state);
    });

    row.appendChild(cb);
    row.appendChild(nameEl);
    row.appendChild(matchEl);
    row.appendChild(valEl);
    container.appendChild(row);
    return row;
  }

  // ─── Selector assembly ─────────────────────────────────────────────

  function cssEsc(v) { return v.replace(/(["\\])/g, '\\$1').replace(/\n/g, ' '); }
  function xpathLiteral(v) {
    if (typeof v !== 'string') v = String(v);
    if (!v.includes("'")) return `'${v}'`;
    if (!v.includes('"')) return `"${v}"`;
    return `concat('${v.split("'").join(`', "'", '`)}')`;
  }

  function buildAttrPredicate(key, value, operator, choice) {
    if (choice === 'css') {
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

  function buildTextPredicate(value, operator) {
    switch (operator) {
      case 'contains': return `[contains(text(),${xpathLiteral(value)})]`;
      case 'not_contains': return `[not(contains(text(),${xpathLiteral(value)}))]`;
      case 'starts_with': return `[starts-with(text(),${xpathLiteral(value)})]`;
      case 'not_starts_with': return `[not(starts-with(text(),${xpathLiteral(value)}))]`;
      case 'ends_with': return `[substring(text(), string-length(text()) - string-length(${xpathLiteral(value)}) + 1) = ${xpathLiteral(value)}]`;
      case 'not_ends_with': return `[not(substring(text(), string-length(text()) - string-length(${xpathLiteral(value)}) + 1) = ${xpathLiteral(value)})]`;
      case 'not_equals': return `[text()!=${xpathLiteral(value)}]`;
      case 'gt': return `[text()>${value}]`;
      case 'gte': return `[text()>=${value}]`;
      case 'lt': return `[text()<${value}]`;
      case 'lte': return `[text()<=${value}]`;
      default: return `[text()=${xpathLiteral(value)}]`;
    }
  }

  function buildXPathSeg(node, attrMap, includeTag, innerTextValue, state) {
    let seg = includeTag ? (node.tag || '*') : '*';
    const predicates = [];

    if (attrMap.id && node.id) {
      predicates.push(`@id=${xpathLiteral(node.id)}`);
    }

    (node.classes || []).forEach((cls) => {
      if (attrMap['class:' + cls]) {
        const op = attrMap['class:' + cls + ':operator'] || 'contains';
        predicates.push(buildAttrPredicate('class', cls, op, 'xpath').slice(1, -1));
      }
    });

    Object.entries(node.attrs || {}).forEach(([k, v]) => {
      if (k === 'verse_fp') return;
      if (!attrMap[k]) return;
      const op = attrMap[k + ':operator'] || 'equals';
      predicates.push(buildAttrPredicate(k, v, op, 'xpath').slice(1, -1));
    });

    if (attrMap['index-of-type']) {
      predicates.push(String((node.index || 0) + 1));
    }
    if (attrMap['nth-child']) {
      predicates.push(`position()=${(node.realIndex ?? node.index ?? 0) + 1}`);
    }
    if (innerTextValue) {
      const op = attrMap['innerText:operator'] || 'contains';
      predicates.push(buildTextPredicate(innerTextValue, op).slice(1, -1));
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

  function updateSelector(state) {
    if (!state.elementData) return;
    const ids = getPanelIds(state === assocState ? 'child' : 'new');
    const path = state.elementData.path || [];
    const isAssoc = state === assocState;
    const startIdx = isAssoc ? Math.max(0, state.anchorPathIndex + 1) : 0;

    // Backward compatibility: captures without anchorPathIndex fall back to the
    // previous recompute-from-target behavior.
    if (isAssoc && state.anchorPathIndex < 0 && getCurrentAnchorElement()) {
      computeRelativeForSelectedAnchor(true);
      return;
    }

    const segs = [];
    const segIndices = [];

    if (state.activeChoice === 'xpath') {
      for (let i = startIdx; i < path.length; i++) {
        const node = path[i];
        const attrMap = state.attrEnabled[i] || {};
        const hasId = attrMap.id && node.id;
        const hasClass = (node.classes || []).some((cls) => attrMap['class:' + cls]);
        const hasAttr = Object.keys(node.attrs || {}).some((k) => attrMap[k]);
        const hasNth = attrMap['index-of-type'];
        const hasNthChild = attrMap['nth-child'];
        const hasText = attrMap['innerText'] && state.elementData?.inner_text && i === path.length - 1;
        const hasSib = Object.keys(attrMap).some((k) => k.startsWith('sib:') && attrMap[k]);
        const hasAny = state.pathEnabled[i] || hasId || hasClass || hasAttr || hasNth || hasNthChild || hasText || hasSib;
        if (!hasAny) continue;
        const innerTextValue = hasText ? state.elementData.inner_text.slice(0, 80) : null;
        segs.push(buildXPathSeg(node, attrMap, state.pathEnabled[i], innerTextValue, state));
        segIndices.push(i);
      }
    } else {
      for (let i = startIdx; i < path.length; i++) {
        const node = path[i];
        const attrMap = state.attrEnabled[i] || {};
        const hasId = attrMap.id && node.id;
        const hasClass = (node.classes || []).some((cls) => attrMap['class:' + cls]);
        const hasAttr = Object.keys(node.attrs || {}).some((k) => attrMap[k]);
        const hasNth = attrMap['index-of-type'];
        const hasNthChild = attrMap['nth-child'];
        const hasSib = Object.keys(attrMap).some((k) => k.startsWith('sib:') && attrMap[k]);

        const hasAny = state.pathEnabled[i] || hasId || hasClass || hasAttr || hasNth || hasNthChild || hasSib;
        if (!hasAny) continue;

        const parts = [];

        if (state.pathEnabled[i]) {
          parts.push(node.tag || 'div');
        }

        if (hasId) {
          if (!state.pathEnabled[i]) parts.length = 0;
          parts.push('#' + CSS.escape(node.id));
        } else if (hasClass) {
          if (!state.pathEnabled[i]) parts.length = 0;
          (node.classes || []).forEach((cls) => {
            if (attrMap['class:' + cls]) {
              const op = attrMap['class:' + cls + ':operator'] || 'contains';
              const negative = op.startsWith('not_');
              parts.push(negative ? `:not(.${CSS.escape(cls)})` : `.${CSS.escape(cls)}`);
            }
          });
        } else if (hasAttr && !state.pathEnabled[i]) {
          parts.length = 0;
        }

        const attrs = node.attrs || {};
        Object.entries(attrs).forEach(([k, v]) => {
          if (k === 'verse_fp') return;
          if (!attrMap[k]) return;
          const op = attrMap[k + ':operator'] || 'equals';
          parts.push(buildAttrPredicate(k, v, op, 'css'));
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

    if (state.activeChoice === 'css') {
      const targetIdx = path.length - 1;
      const targetAttrMap = state.attrEnabled[targetIdx] || {};
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
    } else if (state.activeChoice === 'xpath') {
      const targetIdx = path.length - 1;
      const targetAttrMap = state.attrEnabled[targetIdx] || {};
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

    let selector = '';
    if (state.activeChoice === 'css') {
      selector = 'css:' + joinSegs(segs, segIndices, 'css');
    } else if (state.activeChoice === 'xpath') {
      if (isAssoc) {
        // In assoc mode the first enabled level may be deeper than the anchor's
        // direct child (intermediate levels disabled). Use .// to match CSS
        // descendant semantics; use ./ only when the first enabled level is the
        // direct child of the anchor.
        const firstGap = segIndices.length ? segIndices[0] - state.anchorPathIndex - 1 : 0;
        selector = 'xpath:.' + (firstGap > 0 ? '//' : '/') + joinSegs(segs, segIndices, 'xpath');
      } else {
        selector = 'xpath://' + joinSegs(segs, segIndices, 'xpath');
      }
    } else {
      selector = 'css:' + joinSegs(segs, segIndices, 'css');
    }

    if (isAssoc) {
      // In associated mode we assemble the relative selector directly from the
      // sub-path below the anchor. The captured global target selector stays in
      // assocState.selectorValue for save/reference; the visible textarea shows
      // the relative selector.
      if (!assocState.relativeManuallyEdited) {
        const relInput = $(ids.selectorPreviewId);
        if (relInput) relInput.value = selector;
        assocState.relativeSelectorValue = selector;
      }
    } else {
      state.selectorValue = selector;
      const preview = $(ids.selectorPreviewId);
      if (preview) preview.value = selector;
    }

    verifyResult.textContent = '点击"校验元素"查看匹配结果';
    verifyResult.className = 'verify-meta';
    broadcastSelectedCandidate();
  }

  // ─── Verify ─────────────────────────────────────────────────────────

  const verifyResult = $('verifyResult');

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

  // ─── Event handlers ────────────────────────────────────────────────

  // Choice buttons for each panel
  function onChoiceClick(btn, state) {
    state.activeChoice = btn.dataset.choice;
    syncChoiceButtons(state);
    updateSelector(state);
    // updateSelector already builds the correct prefixed selector for assoc mode
    // and respects relativeManuallyEdited; do not mirror prefixes here.
  }

  document.querySelectorAll('.global-choice-btn').forEach((btn) => {
    btn.addEventListener('click', () => onChoiceClick(btn, globalState));
  });
  document.querySelectorAll('.assoc-choice-btn').forEach((btn) => {
    btn.addEventListener('click', () => onChoiceClick(btn, assocState));
  });

  // Relative selector manual edit
  const assocRelativeSelectorInput = $('assocRelativeSelectorInput');
  if (assocRelativeSelectorInput) {
    assocRelativeSelectorInput.addEventListener('input', () => {
      assocState.relativeSelectorValue = assocRelativeSelectorInput.value;
      assocState.relativeManuallyEdited = true;
      anchorModeLabel.textContent = '手动';
      const family = inferFamilyFromSelector(assocRelativeSelectorInput.value) || assocState.activeChoice;
      if (family !== assocState.activeChoice) {
        assocState.activeChoice = family;
        syncChoiceButtons(assocState);
      }
      broadcastSelectedCandidate();
    });
  }

  // Verify
  $('btnVerify').addEventListener('click', () => {
    if (!currentTabId) {
      verifyResult.textContent = '未关联页面';
      verifyResult.className = 'verify-meta err';
      return;
    }
    if (captureMode === 'child') {
      const relValue = (assocRelativeSelectorInput?.value || '').trim();
      if (!relValue) {
        verifyResult.textContent = '请填写相对选择器';
        verifyResult.className = 'verify-meta err';
        return;
      }
      verifyResult.textContent = '校验相对选择器中...';
      verifyResult.className = 'verify-meta';
      broadcastSelectedCandidate();
      send('verifyRelative', {
        tabId: currentTabId,
        payload: {
          anchorSelector: anchorSelectorInput.value,
          relativeSelector: assocRelativeSelectorInput.value,
          anchorChain: currentAnchorChain,
        },
      }).then((res) => {
        if (res && res.error) {
          verifyResult.textContent = '校验相对失败: ' + res.error;
          verifyResult.className = 'verify-meta err';
          return;
        }
        const total = res.total ?? res.count ?? 0;
        const anchorCount = res.anchorCount ?? 0;
        const invisible = res.invisible ?? 0;
        if (total === 0) {
          verifyResult.textContent = '未匹配到元素';
          verifyResult.className = 'verify-meta err';
        } else if (total === 1) {
          verifyResult.textContent = `匹配: 1 个元素 ✓${invisible > 0 ? ` (忽略 ${invisible} 个不可见)` : ''}`;
          verifyResult.className = 'verify-meta ok';
        } else {
          verifyResult.textContent = `匹配: ${total} 个元素（基于 ${anchorCount} 个锚点实例）`;
          verifyResult.className = total > 0 ? 'verify-meta ok' : 'verify-meta err';
        }
      }).catch((err) => {
        verifyResult.textContent = '校验相对失败: ' + err.message;
        verifyResult.className = 'verify-meta err';
      });
      return;
    }
    const preview = $(getPanelIds('new').selectorPreviewId);
    verifyResult.textContent = '校验中...';
    verifyResult.className = 'verify-meta';
    broadcastSelectedCandidate();
    send('verifyElement', {
      tabId: currentTabId,
      payload: { selector: preview.value, type: inferFamilyFromSelector(preview.value) },
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
    if (captureMode === 'child' && !activeAnchorSelect?.value) {
      verifyResult.textContent = '捕获关联元素需要先选择锚点元素';
      verifyResult.className = 'verify-meta err';
      if (activeAnchorSelect) activeAnchorSelect.focus();
      return;
    }

    const state = currentState;
    const elementKind = captureMode === 'child' ? 'child' : 'plain';
    const globalPreview = $(getPanelIds('new').selectorPreviewId);
    // Child elements resolve relative to their anchor at runtime; the global
    // target selector captured from the full path is not verified and should
    // not be persisted as web_selector.
    const selector = elementKind === 'child'
      ? ''
      : (state === assocState ? (state.selectorValue || globalPreview?.value || '') : (globalPreview?.value || ''));

    const payload = {
      workflowId: parseInt(selectedWorkflowId, 10),
      name: elName.value.trim(),
      elementKind,
      selector,
      selectorFamily: choiceFamily(state.activeChoice),
      tag: state.elementData?.tag,
      id: state.elementData?.id || '',
      classes: state.elementData?.classes || [],
      attrs: state.elementData?.attrs || {},
      text: state.elementData?.inner_text?.slice(0, 50) || '',
      pageUrl: state.elementData?.pageUrl || '',
      path: state.elementData?.path || [],
      candidates: state.elementData?.candidates,
      screenshot: state.elementData?.screenshot,
      listContainer: state.elementData?.listContainer || '',
      listItem: state.elementData?.listItem || '',
      listSize: state.elementData?.listSize || 0,
    };

    const relValue = (assocRelativeSelectorInput?.value || '').trim();
    if (captureMode === 'child' && relValue) {
      payload.relativeSelector = relValue;
      payload.anchorSelector = (anchorSelectorInput.value || '').trim();
      payload.anchorElementName = activeAnchorSelect?.value || '';
      payload.anchorMode = assocState.relativeManuallyEdited ? 'manual' : 'anchor-first';
      payload.relativeManuallyEdited = assocState.relativeManuallyEdited;
    } else {
      payload.relativeSelector = '';
      payload.anchorSelector = '';
      payload.anchorElementName = '';
      payload.anchorMode = 'none';
      payload.relativeManuallyEdited = false;
    }

    send('saveElement', payload)
      .then(() => {
        verifyResult.textContent = '已保存';
        verifyResult.className = 'verify-meta ok';
        markSavedButton();
        if (selectedWorkflowId) loadWorkflowElements(selectedWorkflowId);
        // 保存完成后清空当前编辑状态，否则 renderActiveAnchorOptions 会把刚保存的元素排除掉
        globalState.elementData = null;
        assocState.elementData = null;
        elName.value = '';
      })
      .catch((err) => {
        verifyResult.textContent = '保存失败: ' + err.message;
        verifyResult.className = 'verify-meta err';
      });
  });

  // Cancel
  $('btnCancel').addEventListener('click', () => {
    [globalState, assocState].forEach((state) => {
      state.elementData = null;
      state.selectedPathIndex = -1;
      state.selectedCandidateType = null;
      state.pathEnabled = [];
      state.attrEnabled = {};
      state.selectorValue = '';
    });
    assocState.relativeSelectorValue = '';
    assocState.relativeManuallyEdited = false;
    assocState.anchorPathIndex = -1;

    elName.value = '';
    const globalPreview = $(getPanelIds('new').selectorPreviewId);
    if (globalPreview) globalPreview.value = '';
    if (assocRelativeSelectorInput) assocRelativeSelectorInput.value = '';
    anchorSelectorInput.value = '';
    verifyResult.textContent = '点击"校验元素"查看匹配结果';
    verifyResult.className = 'verify-meta';
    screenshotPanel.innerHTML = '<div class="screenshot-empty">暂无截图</div>';
    updateScreenshotToggle(null);
    setScreenshotOpen(false);

    Object.values(PANELS).forEach((p) => {
      $(p.domPanelId).innerHTML = '';
      $(p.candidatesListId).innerHTML = '';
      $(p.propPanelId).innerHTML = '';
    });

    resetSaveButton();
  });

  // ─── Connection / workflow init ────────────────────────────────────

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
    loadWorkflows();
  });

  $('connDot').addEventListener('click', () => {
    checkConnection();
  });

  $('workflowSelect').addEventListener('change', (e) => {
    selectedWorkflowId = e.target.value;
    if (selectedWorkflowId) {
      localStorage.setItem('rpa_selected_workflow_id', selectedWorkflowId);
    } else {
      localStorage.removeItem('rpa_selected_workflow_id');
    }
    clearActiveAnchor();
    loadWorkflowElements(selectedWorkflowId);
  });

  // ─── Init ──────────────────────────────────────────────────────────

  // Initialize collapsibles for both panels.
  initCollapsible('globalDomCollapseHeader', 'globalDomCollapseBody', false);
  initCollapsible('globalPropCollapseHeader', 'globalPropCollapseBody', false);
  initCollapsible('assocDomCollapseHeader', 'assocDomCollapseBody', false);
  initCollapsible('assocPropCollapseHeader', 'assocPropCollapseBody', false);

  // Default to global mode.
  applyCaptureMode('new');

  initEnv();
  loadWorkflows();
  loadPayloadFromBackground();

  const panelPort = chrome.runtime.connect({ name: 'sidePanel' });
  panelPort.postMessage({ action: 'sidePanelOpened' });
})();
