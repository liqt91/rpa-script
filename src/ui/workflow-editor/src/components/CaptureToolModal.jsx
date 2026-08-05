import { useState, useEffect } from 'react';
import { api } from '../api';

/**
 * 元素捕获工具 — 原生模态框
 * 支持浏览器捕获(通过WS无超时限制) + 候选选择 + DOM编辑 + 保存到元素库
 */
export default function CaptureToolModal({ wfId, onClose, onSaved }) {
  const [mode, setMode] = useState(0); // 0=推荐方案 1=手动编辑
  const [capturing, setCapturing] = useState(false);
  const [captureError, setCaptureError] = useState('');
  const [elements, setElements] = useState([]);
  const [selectedIdx, setSelectedIdx] = useState(-1);
  const [cur, setCur] = useState(null); // 当前编辑元素
  const [cands, setCands] = useState([]);
  const [selector, setSelector] = useState('');
  const [domPath, setDomPath] = useState([]);
  const [domChecked, setDomChecked] = useState([]);
  const [attrVars, setAttrVars] = useState({});
  const [selLevel, setSelLevel] = useState(-1);
  const [domAttrs, setDomAttrs] = useState({});
  const [sortDir, setSortDir] = useState({ syntax: false, family: false, match: false });

  const strip = (s) => (s || '').replace(/^(css:|xpath:|drission:)/i, '');

  // 加载流程元素
  const loadElements = async (selectLast = false) => {
    try {
      const list = await api.getWorkflowElements(wfId);
      setElements(list || []);
      if (selectLast && list && list.length) {
        showElement(list.length - 1);
      }
    } catch (e) { console.error(e); }
  };

  useEffect(() => { loadElements(); }, [wfId]);

  // 启动浏览器捕获
  const startDesktopCapture = async () => {
    setCapturing(true);
    setCaptureError('');
    try {
      const data = await api.runGuiPicker();
      if (data.cancelled) return;
      const target = data.path?.[data.path.length - 1];
      // 优先用捕获的名称, 否则从 class/tag/type 生成
      let name = String(data.name
        || ((target && target.class_name) || data.tag_name || data.element_type || '元素')
        + ((target && target.title) ? ' "' + target.title + '"' : '')).substring(0, 128) || '捕获元素';
      // 查重: 同名追加 _2 _3 ...
      const existNames = new Set((elements || []).map(e => e.name));
      if (existNames.has(name)) {
        let i = 2;
        while (existNames.has(`${name}_${i}`)) i++;
        name = `${name}_${i}`;
      }
      await api.createWorkflowElement(wfId, {
        name,
        element_kind: data.element_type === 'web' ? 'plain' : 'win32',
        attributes: data,
      });
      await loadElements(true);
      showToast('捕获成功', 'success');
    } catch (e) {
      if (e.message !== 'cancelled') setCaptureError(String(e));
    } finally {
      setCapturing(false);
    }
  };

  // 展示元素
  const showElement = (i) => {
    const el = elements[i];
    if (!el) return;
    setSelectedIdx(i);
    const attrs = el.attributes || el;
    setCur(attrs);
    const cs = attrs.candidates || [];
    setCands(cs.filter(c => ['css', 'xpath'].includes((c.family || c.type || '').toLowerCase())));
    const path = attrs.dom_path || attrs.path || [];
    setDomPath(path);
    setDomChecked(path.map(() => true));
    setAttrVars({});
    setSelLevel(-1);
    setDomAttrs(attrs.attrs || {});
    setSelector(strip(attrs.css_selector || (cs[0] && cs[0].syntax) || ''));
  };

  const sortCands = (col) => {
    const nd = { ...sortDir, [col]: !sortDir[col] };
    setSortDir(nd);
    const idx = { syntax: 0, family: 1, match: 2 }[col];
    const sorted = [...cands].sort((a, b) => {
      let va = idx === 2 ? (a.matchCount || 0) : (a[['syntax', 'family', 'match'][idx]] || '');
      let vb = idx === 2 ? (b.matchCount || 0) : (b[['syntax', 'family', 'match'][idx]] || '');
      if (typeof va === 'string') va = va.toLowerCase();
      if (typeof vb === 'string') vb = vb.toLowerCase();
      return nd[col] ? (va > vb ? -1 : 1) : (va < vb ? -1 : 1);
    });
    setCands(sorted);
  };

  // 勾选/取消勾选层级 (参与选择器生成)
  const toggleDomCheck = (i) => {
    const nd = [...domChecked]; nd[i] = !nd[i];
    setDomChecked(nd);
    updateDomSel(nd, attrVars, selLevel);
  };

  // 选中层级 (显示该层属性)
  const selectDomLevel = (i) => {
    setSelLevel(i);
    const node = domPath[i];
    const nodeAttrs = (node && typeof node === 'object' && node.attrs) || {};
    setDomAttrs(nodeAttrs);
  };

  const toggleAttr = (i, key) => {
    const na = { ...attrVars, [i]: { ...(attrVars[i] || {}), [key]: !(attrVars[i] || {})[key] } };
    setAttrVars(na);
    updateDomSel(domChecked, na, selLevel);
  };

  const updateDomSel = (checked, av, level) => {
    const parts = [];
    for (let i = 0; i < domPath.length; i++) {
      if (!checked[i]) continue;
      const n = domPath[i];
      let p = typeof n === 'object' ? (n.tag || 'div') : String(n);
      if (n && n.id) p += '#' + n.id;
      if (n && n.classes?.length) p += '.' + n.classes.slice(0, 3).join('.');
      if (av[i]) {
        for (const [k, v] of Object.entries(av[i])) {
          if (v) p += `[${k}="${(n && n.attrs && n.attrs[k]) || ''}"]`;
        }
      }
      parts.push(p);
    }
    setSelector(parts.join(' > ') || '');
  };

  const selectAll = () => { const nd = domChecked.map(() => true); setDomChecked(nd); updateDomSel(nd, attrVars, selLevel); };
  const selectNone = () => { const nd = domChecked.map(() => false); setDomChecked(nd); updateDomSel(nd, attrVars, selLevel); };

  const verify = async () => {
    if (!cur) return showToast('请先选择元素');
    try {
      if (cur.element_type === 'web' && (cur.css_selector || selector)) {
        // web 元素: 浏览器验证选择器 (extension querySelectorAll)
        const sel = strip(selector || cur.css_selector);
        const d = await api.verifyWebSelector(sel);
        showToast(d.found ? `✅ 匹配 ${d.count || 1} 个` : `❌ ${d.error || '未找到'}`, d.found ? 'success' : 'error');
      } else {
        // 桌面元素: GUI flash_element 闪烁
        const d = await api.runGuiVerify(cur);
        showToast(d.found ? '✅ 元素存在' : '❌ 元素失效', d.found ? 'success' : 'error');
      }
    } catch (e) { showToast('验证失败: ' + e.message, 'error'); }
  };

  const save = async () => {
    if (selectedIdx < 0 || !cur) return;
    try {
      const payload = { ...cur, css_selector: selector };
      await api.updateWorkflowElement(wfId, elements[selectedIdx].id, { attributes: payload });
      showToast('已保存', 'success');
      onSaved && onSaved();
      loadElements();
    } catch (e) { showToast('保存失败: ' + e, 'error'); }
  };

  const copySel = () => { navigator.clipboard.writeText(selector); showToast('已复制'); };

  // 生成控制台验证 JS 代码 (CSS vs XPath)
  const jsCode = selector
    ? (selector.startsWith('/')
        ? `const r = document.evaluate(\`${selector}\`, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);\nconsole.log('匹配:', r.snapshotLength); r.snapshotItem(0)?.scrollIntoView();`
        : `const el = document.querySelectorAll(\`${selector}\`);\nconsole.log('匹配:', el.length); el[0]?.scrollIntoView();`)
    : '';

  let toastTimer;
  const showToast = (msg, type = 'info') => {
    const el = document.getElementById('capture-toast');
    if (!el) return;
    el.textContent = msg;
    el.style.background = type === 'success' ? '#52c41a' : type === 'error' ? '#ef4444' : '#3b82f6';
    el.classList.add('show');  // 保留定位类, 只追加 show
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show'), 2000);
  };

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" onClick={(e) => e.target === e.currentTarget && onClose()}>
        <div className="bg-gray-50 rounded-lg shadow-2xl w-[95vw] h-[90vh] max-w-6xl flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-2.5 bg-white border-b shrink-0">
            <div className="flex items-center gap-3">
              <h2 className="text-sm font-semibold text-gray-800">元素捕获工具</h2>
              <button
                onClick={startDesktopCapture}
                disabled={capturing}
                className="px-3 py-1.5 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white text-xs rounded transition-colors"
              >
                {capturing ? '捕获中... 左键选取目标' : '🔍 捕获元素'}
              </button>
              {captureError && <span className="text-xs text-red-500">{captureError}</span>}
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none px-2">×</button>
          </div>

          {/* Body */}
          <div className="flex flex-1 overflow-hidden">
            {/* 左侧元素列表 */}
            <div className="w-56 border-r bg-white overflow-y-auto shrink-0">
              <div className="px-3 py-2 text-xs font-semibold text-gray-500 border-b">元素列表</div>
              {elements.map((el, i) => (
                <div
                  key={el.id || i}
                  onClick={() => showElement(i)}
                  className={`px-3 py-2 text-xs cursor-pointer hover:bg-blue-50 border-b border-gray-50 ${i === selectedIdx ? 'bg-blue-100 text-blue-700 font-medium' : 'text-gray-700'}`}
                >
                  <div className="truncate">{el.element_kind === 'plain' ? '🌐' : '🪟'} {el.name}</div>
                  {(el.attributes?.css_selector || '') && <div className="text-[10px] text-gray-400 truncate">{el.attributes.css_selector.slice(0, 40)}</div>}
                </div>
              ))}
              {!elements.length && <div className="px-3 py-4 text-xs text-gray-400">暂无元素</div>}
            </div>

            {/* 右侧编辑器 */}
            <div className="flex-1 flex flex-col gap-3 p-4 overflow-y-auto">
              {/* 名称行 */}
              <div className="flex items-center gap-3">
                <label className="text-xs text-gray-500 w-10 shrink-0">名称</label>
                <input
                  value={(cur && cur.name) || ''}
                  onChange={(e) => setCur({ ...cur, name: e.target.value })}
                  className="flex-1 px-2 py-1.5 border rounded text-sm focus:outline-none focus:border-blue-400"
                />
                {cur && cur.screenshot && (
                  <img src={cur.screenshot} alt="截图" className="w-10 h-8 rounded object-contain border cursor-pointer"
                       onClick={() => window.open(cur.screenshot, '_blank')} />
                )}
              </div>

              {/* Tab */}
              <div className="flex gap-1 shrink-0">
                <button onClick={() => setMode(0)}
                  className={`px-4 py-1.5 text-xs rounded-t border-b-0 border ${mode === 0 ? 'bg-white text-blue-600 border-gray-300 font-medium' : 'bg-gray-100 text-gray-500 border-transparent'}`}>
                  {mode === 0 ? '▶ ' : ''}推荐方案
                </button>
                <button onClick={() => setMode(1)}
                  className={`px-4 py-1.5 text-xs rounded-t border-b-0 border ${mode === 1 ? 'bg-white text-blue-600 border-gray-300 font-medium' : 'bg-gray-100 text-gray-500 border-transparent'}`}>
                  {mode === 1 ? '▶ ' : ''}手动编辑
                </button>
              </div>

              {/* 推荐方案 */}
              {mode === 0 && (
                <div className="flex-1 bg-white rounded border overflow-hidden flex flex-col min-h-0">
                  <div className="flex-1 overflow-y-auto min-h-0">
                    <table className="w-full text-xs">
                    <thead className="bg-gray-50 sticky top-0">
                      <tr>
                        <th className="px-3 py-2 text-left font-medium text-gray-500 cursor-pointer hover:text-blue-500" onClick={() => sortCands('syntax')}>选择器</th>
                        <th className="w-16 px-2 py-2 font-medium text-gray-500 cursor-pointer hover:text-blue-500" onClick={() => sortCands('family')}>类型</th>
                        <th className="w-14 px-2 py-2 font-medium text-gray-500 cursor-pointer hover:text-blue-500" onClick={() => sortCands('match')}>匹配</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cands.map((c, i) => (
                        <tr key={i} onClick={() => setSelector(strip(c.syntax))} className="cursor-pointer hover:bg-blue-50 border-t border-gray-100">
                          <td className="px-3 py-2 font-mono">{strip(c.syntax)}</td>
                          <td className="px-2 py-2">
                            <span className={`px-1.5 py-0.5 rounded text-[10px] ${(c.family||'').toLowerCase()==='css' ? 'bg-orange-50 text-orange-500' : 'bg-green-50 text-green-600'}`}>
                              {(c.family || '?').toUpperCase()}
                            </span>
                          </td>
                          <td className="px-2 py-2">{c.matchCount || ''}</td>
                        </tr>
                      ))}
                      {!cands.length && <tr><td colSpan={3} className="px-3 py-6 text-center text-gray-400">暂无候选方案</td></tr>}
                    </tbody>
                  </table>
                  </div>
                </div>
              )}

              {/* 手动编辑 */}
              {mode === 1 && (
                <div className="flex-1 flex gap-3 min-h-0 overflow-hidden">
                  {/* DOM 层级 */}
                  <div className="flex-1 bg-white rounded border p-3 overflow-y-auto">
                    <div className="flex items-center gap-2 mb-2">
                      <button onClick={selectAll} className="px-2 py-1 text-[10px] bg-blue-50 text-blue-600 rounded border border-blue-200">全选</button>
                      <button onClick={selectNone} className="px-2 py-1 text-[10px] bg-gray-50 text-gray-500 rounded border">全不选</button>
                      <span className="text-[10px] text-gray-400">勾选层级参与选择器生成</span>
                    </div>
                    <div className="text-[10px] font-semibold text-gray-400 mb-1">页面层级</div>
                    {domPath.map((node, i) => {
                      const isLeaf = i === domPath.length - 1;
                      const n = typeof node === 'object' ? node : { tag: String(node) };
                      const isSel = i === selLevel;
                      return (
                        <div
                          key={i}
                          className={`flex items-center gap-1.5 py-1 cursor-pointer rounded ${isSel ? 'bg-blue-50 ring-1 ring-blue-200' : 'hover:bg-gray-50'}`}
                          style={{ paddingLeft: i * 14 }}
                          onClick={() => selectDomLevel(i)}
                        >
                          <input type="checkbox" checked={domChecked[i]} onChange={(e) => { e.stopPropagation(); toggleDomCheck(i); }} />
                          <span className={`font-mono text-xs ${isLeaf ? 'text-red-500 font-semibold' : 'text-gray-600'}`}>
                            {'│  '.repeat(i)}&lt;{n.tag || 'div'}&gt;
                          </span>
                          {n.id && <span className="text-green-600 text-xs">#{n.id}</span>}
                          {n.classes?.length > 0 && <span className="text-purple-600 text-xs">.{n.classes.slice(0, 3).join('.')}</span>}
                        </div>
                      );
                    })}
                  </div>

                  {/* 元素属性 */}
                  <div className="w-52 bg-white rounded border p-3 overflow-y-auto shrink-0">
                    <div className="text-[10px] font-semibold text-gray-400 mb-2">元素属性</div>
                    {selLevel >= 0 && Object.keys(domAttrs || {}).length > 0 ? (
                      Object.entries(domAttrs || {}).filter(([k]) => !['id','class','style'].includes(k)).map(([k, v]) => (
                        <div key={k} className="flex items-center gap-1.5 py-1">
                          <input type="checkbox"
                            checked={(attrVars[selLevel] || {})[k] || false}
                            onChange={() => toggleAttr(selLevel, k)} />
                          <span className="font-mono text-[11px] text-purple-700">{k}="{v}"</span>
                        </div>
                      ))
                    ) : (
                      <div className="text-[11px] text-gray-400">点击左侧层级查看属性</div>
                    )}
                  </div>
                </div>
              )}

              {/* 选择器 */}
              <div className="shrink-0">
                <label className="text-xs text-gray-500 block mb-1">选择器</label>
                <div className="flex gap-2 items-start">
                  <textarea
                    value={selector}
                    onChange={(e) => setSelector(e.target.value)}
                    rows={2}
                    className="flex-1 px-2 py-1.5 border rounded text-sm font-mono focus:outline-none focus:border-blue-400 resize-none"
                  />
                  <button onClick={copySel} className="px-3 py-2 text-xs bg-gray-100 hover:bg-gray-200 rounded border">📋</button>
                </div>

                {/* JS 验证代码 */}
                {selector && (
                  <div className="mt-2 bg-gray-900 rounded border border-gray-700 p-2 font-mono text-[11px] text-green-400 relative">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-gray-500 text-[10px]">控制台手动验证 (F12 → Console)</span>
                      <button
                        onClick={() => { navigator.clipboard.writeText(jsCode); showToast('JS 已复制'); }}
                        className="text-gray-400 hover:text-white text-[10px] px-1.5 border border-gray-700 rounded"
                      >复制</button>
                    </div>
                    <pre className="whitespace-pre-wrap break-all">{jsCode}</pre>
                  </div>
                )}
              </div>

              {/* 操作按钮 */}
              <div className="flex gap-2 shrink-0">
                <button onClick={verify} className="px-4 py-2 text-xs bg-blue-500 hover:bg-blue-600 text-white rounded">🔍 验证</button>
                <button onClick={save} className="px-4 py-2 text-xs bg-green-500 hover:bg-green-600 text-white rounded">💾 保存</button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div id="capture-toast" className="capture-toast fixed top-4 left-1/2 -translate-x-1/2 text-white px-5 py-2.5 rounded-lg text-sm z-[9999] opacity-0 pointer-events-none transition-opacity duration-200" />
      <style>{`
        .capture-toast.show { opacity: 1 !important; }
      `}</style>
    </>
  );
}
