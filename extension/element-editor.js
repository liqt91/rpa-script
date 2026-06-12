/**
 * element-editor.js — Element editor UI logic (extracted from inline script
 * to satisfy Chrome Extension CSP: no inline scripts allowed in MV3).
 */
(function () {
  'use strict';

  // ─── State ───────────────────────────────────────────────────────
  let elementData = null;
  let selectedPathIndex = -1;
  let activeTab = 'css';
  let selectedCandidateType = null;
  let pathEnabled = [];   // bool[]: whether each path level is enabled
  let attrEnabled = {};   // { levelIndex: { attrName: bool } }

  // ─── DOM refs ────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const domPanel = $('domPanel');
  const propList = $('propList');
  const selectorPreview = $('selectorPreview');
  const verifyResult = $('verifyResult');
  const screenshotBox = $('screenshotBox');
  const elName = $('elName');
  const targetModeSel = $('targetMode');

  // ─── PostMessage API ─────────────────────────────────────────────

  function send(action, payload) {
    window.parent.postMessage({ source: 'rpa-element-editor', action, payload }, '*');
  }

  // Notify parent we are ready
  send('ready');

  window.addEventListener('message', (e) => {
    const msg = e.data;
    if (!msg || msg.source !== 'rpa-content-script') return;
    if (msg.action === 'init') {
      loadElementData(msg.payload);
    }
    if (msg.action === 'verifyResult') {
      showVerifyResult(msg.payload);
    }
  });

  // ─── Load data ───────────────────────────────────────────────────

  function loadElementData(data) {
    const loading = $('loadingOverlay');
    if (loading) loading.classList.add('hidden');
    elementData = data;
    if (!data) return;

    elName.value = data.name || '';

    // 初始化 targetMode
    if (targetModeSel) targetModeSel.value = data.targetMode || 'single';

    // Screenshot
    if (data.screenshot) {
      screenshotBox.innerHTML = `<img src="${data.screenshot}" alt="screenshot">`;
    }

    // Initialize path: all enabled by default
    const path = data.path || [];
    pathEnabled = path.map(() => true);
    attrEnabled = {};
    path.forEach((_, i) => { attrEnabled[i] = {}; });

    // Default: select the deepest (target) level
    selectedPathIndex = path.length - 1;

    // Auto-select best candidate into preview
    const candidates = data.candidates || [];
    const best = candidates[0];
    if (best) {
      activeTab = best.family || best.type || 'css';
      selectorPreview.value = best.syntax;
      selectedCandidateType = activeTab;
      if (targetModeSel) targetModeSel.value = best.isList ? 'list' : 'single';
      verifyResult.textContent = `${best.matchCount === 1 ? '唯一匹配' : best.matchCount + ' 匹配'} | score:${best.score}`;
      verifyResult.className = 'preview-meta ' + (best.matchCount === 1 ? 'ok' : '');
      // sync tab UI
      document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === activeTab));
    }

    renderDomTree();
    renderCandidates();
    renderProperties();
    if (!best) updateSelector();
  }

  // ─── DOM Tree rendering ──────────────────────────────────────────

  function renderDomTree() {
    domPanel.innerHTML = '';
    const path = elementData?.path || [];
    path.forEach((node, i) => {
      const row = document.createElement('div');
      row.className = 'dom-item' + (i === selectedPathIndex ? ' active' : '');

      const indent = document.createElement('span');
      indent.className = 'dom-indent';
      indent.style.width = (i * 12) + 'px';

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

      row.appendChild(indent);
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

  // ─── Candidates rendering ────────────────────────────────────────

  function renderCandidates() {
    const list = $('candidatesList');
    list.innerHTML = '';
    const cands = (elementData?.candidates || []).filter(c => {
      const family = c.family || c.type || 'css';
      return family === activeTab;
    });
    if (cands.length === 0) {
      list.innerHTML = `<div style="padding:6px 8px;color:#999;font-size:12px;">暂无${activeTab === 'css' ? 'CSS' : activeTab === 'xpath' ? 'XPath' : 'Drission'}推荐方案</div>`;
      return;
    }
    cands.forEach((c) => {
      const row = document.createElement('div');
      row.className = 'prop-row';
      row.style.cursor = 'pointer';
      row.title = c.syntax;

      const badge = c.matchCount === 1
        ? '<span style="background:#52c41a;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;white-space:nowrap;">唯一</span>'
        : `<span style="background:#f0f0f0;color:#666;font-size:10px;padding:1px 5px;border-radius:3px;white-space:nowrap;">${c.matchCount} 匹配</span>`;

      row.innerHTML = `
        <span style="flex:1;min-width:0;font-family:monospace;font-size:11px;color:#333;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(c.syntax)}</span>
        ${badge}
      `;

      row.addEventListener('click', () => {
        selectorPreview.value = c.syntax;
        selectedCandidateType = activeTab;
        if (targetModeSel) targetModeSel.value = c.isList ? 'list' : 'single';
        verifyResult.textContent = `${c.matchCount === 1 ? '唯一匹配' : c.matchCount + ' 匹配'} | score:${c.score}`;
        verifyResult.className = 'preview-meta ' + (c.matchCount === 1 ? 'ok' : '');
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

    // classes — each gets a unique key so users can pick specific ones
    (node.classes || []).forEach((cls) => addPropRow(section, 'class:' + cls, cls, enabledMap, false, 'class'));

    // other attributes
    const attrs = node.attrs || {};
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === 'id' || k === 'class') return;
      addPropRow(section, k, v, enabledMap);
    });

    // structural: index-of-type
    const parent = selectedPathIndex > 0 ? path[selectedPathIndex - 1] : null;
    if (parent) {
      const sameTagSiblings = parent.childrenTags?.filter((t) => t === node.tag).length || 1;
      if (sameTagSiblings > 1) {
        addPropRow(section, 'index-of-type', String((node.index || 0) + 1), enabledMap, false, 'index-of-type');
      }
    }

    propList.appendChild(section);
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
  }

  // ─── Selector assembly ───────────────────────────────────────────

  function cssEsc(v) { return v.replace(/(["\\])/g, '\\$1').replace(/\n/g, ' '); }
  function xpathEsc(v) { return v.replace(/'/g, "'"); }

  function buildAttrPredicate(key, value, operator) {
    if (activeTab === 'css') {
      switch (operator) {
        case 'contains': return `[${key}*="${cssEsc(value)}"]`;
        case 'starts_with': return `[${key}^="${cssEsc(value)}"]`;
        case 'ends_with': return `[${key}$="${cssEsc(value)}"]`;
        case 'not_equals': return `:not([${key}="${cssEsc(value)}"])`;
        default: return `[${key}="${cssEsc(value)}"]`;
      }
    }
    // XPath
    switch (operator) {
      case 'contains': return `[contains(@${key},'${xpathEsc(value)}')]`;
      case 'not_contains': return `[not(contains(@${key},'${xpathEsc(value)}'))]`;
      case 'starts_with': return `[starts-with(@${key},'${xpathEsc(value)}')]`;
      case 'not_starts_with': return `[not(starts-with(@${key},'${xpathEsc(value)}'))]`;
      case 'ends_with': return `[substring(@${key}, string-length(@${key}) - string-length('${xpathEsc(value)}') + 1) = '${xpathEsc(value)}']`;
      case 'not_ends_with': return `[not(substring(@${key}, string-length(@${key}) - string-length('${xpathEsc(value)}') + 1) = '${xpathEsc(value)}')]`;
      case 'not_equals': return `[@${key}!='${xpathEsc(value)}']`;
      case 'gt': return `[@${key}>${value}]`;
      case 'gte': return `[@${key}>=${value}]`;
      case 'lt': return `[@${key}<${value}]`;
      case 'lte': return `[@${key}<=${value}]`;
      default: return `[@${key}='${xpathEsc(value)}']`;
    }
  }

  function updateSelector() {
    if (!elementData) return;
    const path = elementData.path || [];
    const enabledIndices = [];
    for (let i = 0; i < path.length; i++) {
      if (pathEnabled[i]) enabledIndices.push(i);
    }
    if (enabledIndices.length === 0) {
      selectorPreview.value = '';
      verifyResult.textContent = '未选择任何层级';
      verifyResult.className = 'preview-meta';
      return;
    }

    const segs = [];
    for (let j = 0; j < enabledIndices.length; j++) {
      const i = enabledIndices[j];
      const node = path[i];
      const attrMap = attrEnabled[i] || {};
      const parts = [node.tag || 'div'];

      if (attrMap.id && node.id) {
        parts.push('#' + CSS.escape(node.id));
      }
      (node.classes || []).forEach((cls) => {
        if (attrMap['class:' + cls]) {
          parts.push('.' + CSS.escape(cls));
        }
      });
      const attrs = node.attrs || {};
      Object.entries(attrs).forEach(([k, v]) => {
        if (attrMap[k]) {
          const op = attrMap[k + ':operator'] || 'equals';
          parts.push(buildAttrPredicate(k, v, op));
        }
      });
      if (attrMap['index-of-type']) {
        const idx = (node.index || 0) + 1;
        parts.push(`:nth-of-type(${idx})`);
      }

      const seg = parts.join('');
      if (j === 0) {
        segs.push(seg);
      } else {
        const prevI = enabledIndices[j - 1];
        const hasSkipped = i > prevI + 1;
        if (activeTab === 'css') {
          segs.push((hasSkipped ? ' ' : ' > ') + seg);
        } else {
          segs.push((hasSkipped ? '//' : '/') + seg);
        }
      }
    }

    if (activeTab === 'css') {
      selectorPreview.value = segs.join('');
    } else {
      selectorPreview.value = '//' + segs.join('');
    }

    verifyResult.textContent = '点击"校验元素"查看匹配结果';
    verifyResult.className = 'preview-meta';
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
      renderCandidates();
      updateSelector();
    });
  });

  // Verify
  $('btnVerify').addEventListener('click', () => {
    send('verify', { selector: selectorPreview.value, type: selectedCandidateType || activeTab });
  });

  // Save
  $('btnSave').addEventListener('click', () => {
    send('save', {
      name: elName.value.trim(),
      selector: selectorPreview.value,
      selectorFamily: activeTab,
      targetMode: targetModeSel ? targetModeSel.value : 'single',
    });
  });

  // Cancel / Close
  $('btnCancel').addEventListener('click', () => send('cancel'));
  $('btnClose').addEventListener('click', () => send('cancel'));
})();
