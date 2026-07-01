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
  let activeTab = 'xpath-single';

  function tabFamily(tab) {
    if (tab === 'css-single' || tab === 'css-list') return 'css';
    return tab;
  }

  function tabLabel(tab) {
    if (tab === 'css-single') return 'CSS-单个';
    if (tab === 'css-list') return 'CSS-列表';
    if (tab === 'xpath-single') return 'XPath-单个';
    if (tab === 'xpath-list') return 'XPath-列表';
    return 'Drission';
  }
  let selectedCandidateType = null;
  let currentTabId = null;
  let pathEnabled = [];   // bool[]: whether each path level is enabled
  let attrEnabled = {};   // { levelIndex: { attrName: bool } }
  let workflows = [];
  let selectedWorkflowId = localStorage.getItem('rpa_selected_workflow_id') || '';

  // ─── DOM refs ────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const domPanel = $('domPanel');
  const propList = $('propPanel');
  const selectorPreview = $('selectorPreview');
  const verifyResult = $('verifyResult');
  const screenshotBox = $('screenshotBox');
  const elName = $('elName');
  const targetModeSel = $('targetMode');
  const anchorBox = $('anchorBox');
  const useRelativeChk = $('useRelativeChk');
  const anchorSelectorInput = $('anchorSelectorInput');
  const relativeSelectorInput = $('relativeSelectorInput');
  const anchorModeLabel = $('anchorMode');
  // Tracks whether the user manually edited the relative selector this capture.
  let relativeManuallyEdited = false;

  // Populate the loop-relative anchor panel from a capture payload. Hidden when
  // the element was not anchored to a repeating ancestor (legacy / non-list).
  function loadAnchorData(data) {
    relativeManuallyEdited = false;
    const rel = data?.relativeSelector || '';
    if (!rel) {
      anchorBox.style.display = 'none';
      relativeSelectorInput.value = '';
      anchorSelectorInput.value = '';
      return;
    }
    anchorBox.style.display = 'flex';
    relativeSelectorInput.value = rel;
    anchorSelectorInput.value = data.anchorSelector || '';
    useRelativeChk.checked = true;
    const mode = data.anchorMode || 'auto';
    anchorModeLabel.textContent = mode === 'manual' ? '手动' : (mode === 'backfill' ? '回填' : '自动');
  }

  if (relativeSelectorInput) {
    relativeSelectorInput.addEventListener('input', () => {
      relativeManuallyEdited = true;
      anchorModeLabel.textContent = '手动';
    });
  }

  // ─── Runtime Message API ─────────────────────────────────────────

  function send(action, payload) {
    return chrome.runtime.sendMessage({ action, payload });
  }

  function broadcastSelectedCandidate() {
    const selector = selectorPreview.value;
    const type = selectedCandidateType || tabFamily(activeTab);
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
        }
      }
    } catch (e) {
      console.warn('[SidePanel] failed to load workflows:', e);
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
      screenshotBox.innerHTML = `<img src="${data.screenshot}" alt="screenshot">`;
    } else {
      screenshotBox.innerHTML = '<span style="color:#999;font-size:12px;">暂无截图</span>';
    }

    // Initialize path: all enabled by default
    const path = data.path || [];
    pathEnabled = path.map(() => true);
    attrEnabled = {};
    path.forEach((_, i) => { attrEnabled[i] = {}; });

    // Default: select the deepest (target) level
    selectedPathIndex = path.length - 1;

    renderDomTree();
    renderCandidates();
    renderProperties();

    // 默认选中当前 tab 下排名第一的推荐方案
    const tabCands = (data.candidates || []).filter(c => {
      const family = c.family || c.type || 'css';
      if (activeTab === 'css-single') return family === 'css' && !c.isList;
      if (activeTab === 'css-list') return family === 'css' && c.isList;
      if (activeTab === 'xpath-single') return family === 'xpath' && !c.isList;
      if (activeTab === 'xpath-list') return family === 'xpath' && c.isList;
      return family === activeTab;
    });
    const first = tabCands[0] || data.candidates?.[0];
    if (first) {
      selectorPreview.value = first.syntax;
      selectedCandidateType = first.family || first.type || 'css';
      applyCandidateToUI(first);
      const statusText = first.matchCount === 1 ? '唯一匹配' : (first.isList ? `列表 (${first.matchCount}个)` : first.matchCount + ' 匹配');
      verifyResult.textContent = `${statusText} | score:${first.score}`;
      verifyResult.className = 'preview-meta ' + (first.matchCount === 1 ? 'ok' : '');
      broadcastSelectedCandidate();
    } else {
      updateSelector();
    }

    // 初始化 targetMode 下拉框
    targetModeSel.value = data.targetMode || 'single';

    // 循环内相对解析锚点
    loadAnchorData(data);
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
    const family = c.family || c.type || 'css';

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
      } else if (family === 'drission' || syntax.startsWith('text=')) {
        attrEnabled[path.length - 1]['innerText'] = true;
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
    if (family === 'drission') {
      attrEnabled[path.length - 1]['innerText'] = true;
    }
    renderDomTree();
    renderProperties();
  }

  // ─── Candidates rendering ────────────────────────────────────────

  function renderCandidates() {
    const list = $('candidatesList');
    list.innerHTML = '';
    const cands = (elementData?.candidates || []).filter(c => {
      const family = c.family || c.type || 'css';
      if (activeTab === 'css-single') return family === 'css' && !c.isList;
      if (activeTab === 'css-list') return family === 'css' && c.isList;
      if (activeTab === 'xpath-single') return family === 'xpath' && !c.isList;
      if (activeTab === 'xpath-list') return family === 'xpath' && c.isList;
      return family === activeTab;
    });
    if (cands.length === 0) {
      list.innerHTML = `<div style="padding:6px 8px;color:#999;font-size:12px;">暂无${tabLabel(activeTab)}推荐方案</div>`;
      return;
    }
    cands.forEach((c) => {
      const row = document.createElement('div');
      row.className = 'prop-row';
      row.style.cursor = 'pointer';
      row.title = c.syntax;

      const badge = c.matchCount === 1
        ? '<span style="background:#52c41a;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;white-space:nowrap;">唯一</span>'
        : c.isList
        ? `<span style="background:#722ed1;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;white-space:nowrap;">列表 ${c.matchCount}个</span>`
        : `<span style="background:#f0f0f0;color:#666;font-size:10px;padding:1px 5px;border-radius:3px;white-space:nowrap;">${c.matchCount} 匹配</span>`;

      row.innerHTML = `
        <span style="flex:1;min-width:0;font-family:monospace;font-size:11px;color:#333;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(c.syntax)}</span>
        ${badge}
      `;

      row.addEventListener('click', () => {
        selectorPreview.value = c.syntax;
        selectedCandidateType = tabFamily(activeTab);
        targetModeSel.value = c.isList ? 'list' : 'single';
        applyCandidateToUI(c);
        const statusText = c.matchCount === 1 ? '唯一匹配' : (c.isList ? `列表 (${c.matchCount}个)` : c.matchCount + ' 匹配');
        verifyResult.textContent = `${statusText} | score:${c.score}`;
        verifyResult.className = 'preview-meta ' + (c.matchCount === 1 ? 'ok' : '');
        broadcastSelectedCandidate();
      });

      list.appendChild(row);
    });
  }

  function escapeHtml(str) {
    return str.replace(/[<>"&]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '"': '&quot;', '&': '&amp;' }[c]));
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
    if (activeTab === 'css-single' || activeTab === 'css-list') {
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

    if (activeTab === 'xpath-single' || activeTab === 'xpath-list') {
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
    if (activeTab === 'css-single' || activeTab === 'css-list') {
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
    } else if (activeTab === 'xpath-single' || activeTab === 'xpath-list') {
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

    if (activeTab === 'css-single' || activeTab === 'css-list') {
      selectorPreview.value = 'css:' + joinSegs(segs, segIndices, 'css');
    } else if (activeTab === 'xpath-single' || activeTab === 'xpath-list') {
      selectorPreview.value = 'xpath://' + joinSegs(segs, segIndices, 'xpath');
    } else if (activeTab === 'drission') {
      // Drission text selector takes precedence when innerText is checked
      const targetIdx = path.length - 1;
      if (attrEnabled[targetIdx]?.['innerText'] && elementData?.inner_text) {
        selectorPreview.value = `text=${elementData.inner_text.slice(0, 80)}`;
      } else {
        selectorPreview.value = 'css:' + joinSegs(segs, segIndices, 'css');
      }
    } else {
      selectorPreview.value = 'css:' + joinSegs(segs, segIndices, 'css');
    }

    verifyResult.textContent = '点击"校验元素"查看匹配结果';
    verifyResult.className = 'preview-meta';
    broadcastSelectedCandidate();
  }

  // ─── Verify ──────────────────────────────────────────────────────

  function showVerifyResult(result) {
    const visible = result.visible ?? result.count ?? 0;
    const invisible = result.invisible ?? 0;
    const total = result.total ?? (visible + invisible);
    if (total === 0) {
      verifyResult.textContent = '未匹配到元素';
      verifyResult.className = 'preview-meta err';
    } else if (total === 1) {
      verifyResult.textContent = `匹配: 1 个元素 ✓${invisible > 0 ? ` (忽略 ${invisible} 个不可见)` : ''}`;
      verifyResult.className = 'preview-meta ok';
    } else {
      verifyResult.textContent = `匹配: ${visible} 个可见，${invisible} 个不可见（共 ${total} 个）`;
      verifyResult.className = 'preview-meta err';
    }
  }

  // ─── Event handlers ──────────────────────────────────────────────

  // Tabs
  document.querySelectorAll('.tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      activeTab = tab.dataset.tab;
      if (activeTab === 'css-list') targetModeSel.value = 'list';
      else if (activeTab === 'css-single') targetModeSel.value = 'single';
      else if (activeTab === 'xpath-list') targetModeSel.value = 'list';
      else if (activeTab === 'xpath-single') targetModeSel.value = 'single';
      renderCandidates();
      updateSelector();
    });
  });

  // Verify
  $('btnVerify').addEventListener('click', () => {
    if (!currentTabId) {
      verifyResult.textContent = '未关联页面';
      verifyResult.className = 'preview-meta err';
      return;
    }
    verifyResult.textContent = '校验中...';
    verifyResult.className = 'preview-meta';
    send('verifyElement', {
      tabId: currentTabId,
      payload: { selector: selectorPreview.value, type: selectedCandidateType || tabFamily(activeTab) },
    }).then((res) => {
      if (res && res.error) {
        verifyResult.textContent = '校验失败: ' + res.error;
        verifyResult.className = 'preview-meta err';
      }
    }).catch((err) => {
      verifyResult.textContent = '校验失败: ' + err.message;
      verifyResult.className = 'preview-meta err';
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
      verifyResult.className = 'preview-meta err';
      $('workflowSelect').focus();
      return;
    }
    const payload = {
      workflowId: parseInt(selectedWorkflowId, 10),
      name: elName.value.trim(),
      selector: selectorPreview.value,
      selectorFamily: tabFamily(activeTab),
      targetMode: targetModeSel.value || 'single',
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
      payload.anchorMode = relativeManuallyEdited
        ? 'manual'
        : (elementData?.anchorMode || 'auto');
    } else {
      payload.relativeSelector = '';
      payload.anchorSelector = '';
      payload.anchorMode = useRelativeChk.checked ? 'auto' : 'none';
    }
    send('saveElement', payload)
      .then(() => {
        verifyResult.textContent = '已保存';
        verifyResult.className = 'preview-meta ok';
        markSavedButton();
      })
      .catch((err) => {
        verifyResult.textContent = '保存失败: ' + err.message;
        verifyResult.className = 'preview-meta err';
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
    if (anchorBox) anchorBox.style.display = 'none';
    if (relativeSelectorInput) relativeSelectorInput.value = '';
    if (anchorSelectorInput) anchorSelectorInput.value = '';
    relativeManuallyEdited = false;
    verifyResult.textContent = '点击"校验元素"查看匹配结果';
    verifyResult.className = 'preview-meta';
    screenshotBox.innerHTML = '<span style="color:#999;font-size:12px;">暂无截图</span>';
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
  });

  // ─── Init ────────────────────────────────────────────────────────

  // Load workflows and capture payload when panel opens
  initEnv();
  loadWorkflows();
  loadPayloadFromBackground();

  // 通知 background：side panel 已打开/关闭，控制所有标签页的 Alt 捕获开关
  const panelPort = chrome.runtime.connect({ name: 'sidePanel' });
  panelPort.postMessage({ action: 'sidePanelOpened' });
})();
