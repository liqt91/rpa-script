import { useState, useEffect } from 'react';
import { api } from '../api';

const CMD_TYPES = [
  { value: 'extension', label: '扩展端执行指令', desc: '浏览器扩展中执行，每个指令一个 JS handler 文件' },
  { value: 'backend', label: '本地端操作指令', desc: '后端 Python 执行，每个指令一个 Python handler 文件' },
  { value: 'control', label: '本地端控制指令', desc: '流程控制（if / for / trycatch 等），无需 handler' },
];

const PARAM_TYPES = []; // populated from value_types.json

const PARAM_GROUPS = [
  { v: '默认属性', l: '默认属性' },
  { v: 'advanced', l: '高级' },
  { v: '输出变量', l: '输出变量' },
  { v: '输入变量', l: '输入变量' },
  { v: 'anchor', l: '锚点' },
];

const ICONS = [
  'fa-circle', 'fa-square', 'fa-star', 'fa-heart', 'fa-check', 'fa-times', 'fa-plus', 'fa-minus',
  'fa-arrow-up', 'fa-arrow-down', 'fa-arrow-left', 'fa-arrow-right', 'fa-arrows-up-down', 'fa-arrows-left-right',
  'fa-hand-pointer', 'fa-mouse-pointer', 'fa-cursor', 'fa-i-cursor',
  'fa-globe', 'fa-home', 'fa-cog', 'fa-wrench', 'fa-sliders', 'fa-filter',
  'fa-search', 'fa-magnifying-glass', 'fa-eye', 'fa-eye-slash', 'fa-binoculars',
  'fa-keyboard', 'fa-font', 'fa-bold', 'fa-italic', 'fa-underline', 'fa-heading', 'fa-paragraph', 'fa-list', 'fa-table', 'fa-hashtag',
  'fa-link', 'fa-unlink', 'fa-copy', 'fa-paste', 'fa-clipboard', 'fa-scissors', 'fa-pencil', 'fa-eraser', 'fa-paintbrush',
  'fa-play', 'fa-pause', 'fa-stop', 'fa-forward', 'fa-backward', 'fa-rotate', 'fa-repeat', 'fa-shuffle',
  'fa-camera', 'fa-image', 'fa-video', 'fa-film', 'fa-music', 'fa-volume-high', 'fa-microphone',
  'fa-clock', 'fa-hourglass', 'fa-calendar', 'fa-bell', 'fa-envelope', 'fa-phone', 'fa-comment', 'fa-message',
  'fa-cloud', 'fa-cloud-arrow-up', 'fa-cloud-arrow-down', 'fa-download', 'fa-upload',
  'fa-code', 'fa-terminal', 'fa-bug', 'fa-shield', 'fa-lock', 'fa-unlock', 'fa-key', 'fa-fingerprint',
  'fa-user', 'fa-users', 'fa-user-plus', 'fa-user-gear', 'fa-address-card', 'fa-id-card',
  'fa-file', 'fa-folder', 'fa-folder-open', 'fa-folder-tree', 'fa-book', 'fa-bookmark',
  'fa-database', 'fa-server', 'fa-hard-drive', 'fa-microchip', 'fa-network-wired', 'fa-wifi',
  'fa-cart-shopping', 'fa-credit-card', 'fa-calculator', 'fa-chart-bar', 'fa-chart-line', 'fa-chart-pie',
  'fa-sun', 'fa-moon', 'fa-bolt', 'fa-fire', 'fa-gear', 'fa-power-off', 'fa-toggle-on', 'fa-toggle-off',
  'fa-mobile', 'fa-tablet', 'fa-laptop', 'fa-desktop', 'fa-print',
  'fa-map', 'fa-location-dot', 'fa-location-crosshairs', 'fa-compass', 'fa-flag', 'fa-tag', 'fa-tags',
  'fa-inbox', 'fa-paper-plane', 'fa-share', 'fa-thumbs-up', 'fa-thumbs-down', 'fa-trophy', 'fa-gift', 'fa-rocket',
  'fa-crown', 'fa-certificate', 'fa-medal', 'fa-wand-magic-sparkles', 'fa-droplet', 'fa-brush', 'fa-palette',
  'fa-dice', 'fa-chess', 'fa-puzzle-piece', 'fa-gamepad', 'fa-ghost', 'fa-skull',
  'fa-equals', 'fa-not-equal', 'fa-greater-than', 'fa-less-than', 'fa-percent', 'fa-divide', 'fa-infinity',
  'fa-code-branch', 'fa-code-merge', 'fa-code-pull-request', 'fa-code-fork',
  'fa-spinner', 'fa-circle-notch',
];

export default function CommandEditor() {
  const [defs, setDefs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [buildResult, setBuildResult] = useState(null);
  const [pythonCode, setPythonCode] = useState('');
  const [jsCode, setJsCode] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [reviewFindings, setReviewFindings] = useState(null);
  const [showTypeRegistry, setShowTypeRegistry] = useState(false);
  const [typeRegistryJson, setTypeRegistryJson] = useState('');
  const [categories, setCategories] = useState([]);
  const [valueTypes, setValueTypes] = useState({});
  const [paramTypes, setParamTypes] = useState([]);

  useEffect(() => { loadDefinitions(); loadCategories(); loadValueTypes(); }, []);

  async function loadValueTypes() {
    try {
      const data = await api.request('/api/commands/value-types');
      const pt = data.paramTypes || {};
      setParamTypes(Object.keys(pt));
      setValueTypes(data.valueTypes || {});
      setTypeRegistryJson(JSON.stringify(data, null, 2));
    } catch (e) { /* ignore */ }
  }

  async function saveTypeRegistry() {
    try {
      await api.request('/api/commands/value-types', {
        method: 'PUT',
        body: typeRegistryJson,
      });
      await loadValueTypes();
      setStatus('类型注册表已保存');
    } catch (e) { setError('保存类型注册表失败: ' + e.message); }
  }

  async function loadCategories() {
    try {
      const cats = await api.getCategories();
      setCategories(cats);
    } catch (e) { /* ignore */ }
  }

  async function loadDefinitions() {
    try {
      const defs = await api.request('/api/commands/definitions');
      setDefs(defs);
    } catch (e) { setError('加载失败: ' + e.message); }
  }

  async function loadPythonSource(typeName) {
    if (!typeName) {
      setPythonCode('');
      return;
    }
    try {
      const data = await api.getHandlerSource(typeName);
      setPythonCode(data.code || '');
    } catch (e) {
      setPythonCode('');
    }
  }

  async function loadJsSource(typeName) {
    if (!typeName) { setJsCode(''); return; }
    try {
      const data = await api.getJsHandlerSource(typeName);
      setJsCode(data.code || '');
    } catch (e) { setJsCode(''); }
  }

  function selectDef(d) {
    setSelected(d);
    setForm(structuredClone(d));
    setStatus('');
    setError('');
    setBuildResult(null);
    setPythonCode('');
    setJsCode('');
    loadPythonSource(d.cmd);
    loadJsSource(d.cmd);
  }

  function createNew() {
    const type = prompt('指令类型名（英文小写，自动做文件名）:');
    if (!type) return;
    const template = {
      type, label: type, categories: [], runtime: 'extension',
      icon: 'fa-circle', iconColor: 'text-gray-500', bgColor: 'bg-gray-50',
      commandOrder: 0, description: '', enabled: true,
      params: [],
    };
    setSelected(template);
    setForm(structuredClone(template));
    setStatus('');
    setError('');
    setPythonCode('');
    setJsCode('');
  }

  function updateField(field, value) {
    setForm(prev => ({ ...prev, [field]: value }));
    setStatus('');
  }

  function updateHandler(field, value) {
    setForm(prev => ({ ...prev, handler: { ...prev.handler, [field]: value } }));
    setStatus('');
  }

  function updateParam(idx, field, value) {
    setForm(prev => {
      const params = [...prev.params];
      params[idx] = { ...params[idx], [field]: value };
      return { ...prev, params };
    });
    setStatus('');
  }

  function addParam() {
    setForm(prev => ({ ...prev, params: [...prev.params, { name: '', label: '', type: 'text' }] }));
  }

  function removeParam(idx) {
    setForm(prev => ({ ...prev, params: prev.params.filter((_, i) => i !== idx) }));
  }

  async function saveDef() {
    if (!form) return;
    try {
      // Strip internal UI fields before saving
      const clean = {};
      for (const [k, v] of Object.entries(form)) {
        if (k.startsWith('_') || k === '_file' || k === 'handler') continue;
        clean[k] = v;
      }
      await api.request(`/api/commands/definitions/${form.cmd}`, {
        method: 'PUT',
        body: JSON.stringify(clean),
      });
      setSelected(form);
      setStatus('已保存');
      setError('');
      loadDefinitions();
      loadPythonSource(form.cmd);
      loadJsSource(form.cmd);
    } catch (e) {
      setError('保存失败: ' + (e.message || ''));
    }
  }

  async function deleteDef() {
    if (!form) return;
    if (!confirm(`确认删除指令 "${form.cmd}"？也会删除对应的 handler 文件。`)) return;
    try {
      await api.deleteDefinition(form.cmd);
      setForm(null);
      setSelected(null);
      setStatus('');
      setError('');
      loadDefinitions();
    } catch (e) {
      setError('删除失败: ' + (e.message || ''));
    }
  }

  async function runBuild() {
    try {
      setStatus('构建中...');
      const res = await api.request('/api/commands/definitions/build', { method: 'POST' });
      setBuildResult(res);
      setStatus('构建完成');
      setError('');
    } catch (e) { setError('构建失败: ' + e.message); }
  }

  async function generateHandlerWithAI() {
    if (!form) return;
    setAiLoading(true); setError('');
    try {
      const definition = {
        cmd: form.cmd, label: form.label, category: form.category,
        runtime: form.runtime, description: form.description,
        params: form.params || [],
      };
      const res = await api.generateWithScenario('command_backend', { definition });
      setPythonCode(res.code || '');
      setStatus('AI 生成完成');
    } catch (e) { setError('AI 生成失败: ' + e.message); }
    finally { setAiLoading(false); }
  }

  async function reviewHandler() {
    if (!form || !pythonCode) return;
    setAiLoading(true); setError(''); setReviewFindings(null);
    try {
      const definition = {
        cmd: form.cmd, label: form.label, category: form.category,
        runtime: form.runtime, description: form.description,
        params: form.params || [],
      };
      const res = await api.generateWithScenario('command_review', { definition, source: pythonCode });
      setReviewFindings(res.findings || []);
      setStatus(res.findings?.length ? `发现 ${res.findings.length} 个问题` : '未发现问题');
    } catch (e) { setError('Review 失败: ' + e.message); }
    finally { setAiLoading(false); }
  }

  async function savePythonCode() {
    if (!form || !pythonCode) return;
    try {
      await api.saveHandlerCode(form.cmd, pythonCode);
      setStatus('Python 代码已保存');
    } catch (e) {
      setError('保存失败: ' + e.message);
    }
  }

  // ── common tailwind classes ──
  const labelCls = 'text-[10px] text-gray-400 mb-0.5';
  const inputCls = 'w-full px-2 py-1 bg-[#0f172a] border border-gray-600 rounded text-gray-200 text-xs outline-none focus:border-blue-500';
  const selectCls = 'w-full px-2 py-1 bg-[#0f172a] border border-gray-600 rounded text-gray-200 text-xs outline-none focus:border-blue-500';

  const isBackend = form && form.runtime === 'backend';
  const isExtension = form && form.runtime === 'extension';
  const isControl = form && form.runtime === 'control';

  // ── color palette ──
  // Each entry: name, hex (500 shade for icons), hex50 (50 shade for bg)
  const PALETTE = [
    { name: 'slate',   hex:'#64748b', hex50:'#f8fafc' }, { name: 'gray',   hex:'#6b7280', hex50:'#f9fafb' },
    { name: 'zinc',    hex:'#71717a', hex50:'#fafafa' }, { name: 'neutral',hex:'#737373', hex50:'#fafafa' },
    { name: 'stone',   hex:'#78716c', hex50:'#fafaf9' }, { name: 'red',    hex:'#ef4444', hex50:'#fef2f2' },
    { name: 'orange',  hex:'#f97316', hex50:'#fff7ed' }, { name: 'amber',  hex:'#f59e0b', hex50:'#fffbeb' },
    { name: 'yellow',  hex:'#eab308', hex50:'#fefce8' }, { name: 'lime',   hex:'#84cc16', hex50:'#f7fee7' },
    { name: 'green',   hex:'#22c55e', hex50:'#f0fdf4' }, { name: 'emerald',hex:'#10b981', hex50:'#ecfdf5' },
    { name: 'teal',    hex:'#14b8a6', hex50:'#f0fdfa' }, { name: 'cyan',   hex:'#06b6d4', hex50:'#ecfeff' },
    { name: 'sky',     hex:'#0ea5e9', hex50:'#f0f9ff' }, { name: 'blue',   hex:'#3b82f6', hex50:'#eff6ff' },
    { name: 'indigo',  hex:'#6366f1', hex50:'#eef2ff' }, { name: 'violet', hex:'#8b5cf6', hex50:'#f5f3ff' },
    { name: 'purple',  hex:'#a855f7', hex50:'#faf5ff' }, { name: 'fuchsia',hex:'#d946ef', hex50:'#fdf4ff' },
    { name: 'pink',    hex:'#ec4899', hex50:'#fdf2f8' }, { name: 'rose',   hex:'#f43f5e', hex50:'#fff1f2' },
  ];
  function _iconHex(cls) {
    if (!cls) return PALETTE[15].hex;
    const m = cls.match(/text-(\w+)-/);
    const c = PALETTE.find(p => p.name === (m ? m[1] : ''));
    return c ? c.hex : PALETTE[15].hex;
  }
  function _bgHex(cls) {
    if (!cls) return PALETTE[15].hex50;
    const m = cls.match(/bg-(\w+)-/);
    const c = PALETTE.find(p => p.name === (m ? m[1] : ''));
    return c ? c.hex50 : PALETTE[15].hex50;
  }

  return (
    <div className="flex-1 flex min-h-0">
      {/* Left panel — list */}
      <div className="w-56 bg-[#0f172a] border-r border-gray-700 flex flex-col shrink-0">
        <div className="px-3 py-3 border-b border-gray-700 flex items-center justify-between">
          <span className="text-sm font-medium text-gray-200">指令定义</span>
          <button onClick={createNew} className="text-xs text-blue-400 hover:text-blue-300">+ 新建</button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
          {/* 类型注册表入口 */}
          <button
            onClick={() => { setSelected({ _type: '__type_registry__' }); setForm(null); }}
            className={`w-full text-left px-2 py-1.5 rounded text-xs transition-colors flex items-center gap-2 ${
              selected && selected._type === '__type_registry__' ? 'bg-amber-600/30 text-amber-200' : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
            }`}>
            <i className="fas fa-database text-[10px] w-4 text-center"></i>
            类型注册表
          </button>
          {defs.map((d, i) => {
            const isCur = selected && selected.cmd === d.cmd;
            return (
              <button key={d.cmd || d.label || i} onClick={() => selectDef(d)}
                className={`w-full text-left px-2 py-1.5 rounded text-xs transition-colors ${
                  isCur ? 'bg-blue-600/30 text-blue-200' : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'}`}>
                {d.label}
                <span className="text-gray-600 ml-1">{d.cmd}</span>
              </button>
            );
          })}
        </div>
        <div className="px-2 py-2 border-t border-gray-700">
          <button onClick={runBuild}
            className="w-full text-xs px-2 py-1.5 rounded bg-green-700/40 text-green-300 hover:bg-green-700/60 transition-colors">
            <i className="fas fa-hammer mr-1"></i>构建生成
          </button>
          {buildResult && (
            <div className="mt-1 text-[10px] text-gray-500">
              {buildResult.results?.map((r, i) => (
                <div key={i} className={r.returncode === 0 ? 'text-green-400' : 'text-red-400'}>
                  {r.script.split('/').pop()}: {r.returncode === 0 ? '✓' : '✗'}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex flex-col min-w-0">
        {selected && selected._type === '__type_registry__' ? (
          <div className="flex-1 flex flex-col min-h-0">
            <div className="px-4 py-2 border-b border-gray-700 flex items-center justify-between bg-[#0f172a] shrink-0">
              <div className="flex items-center gap-2">
                <i className="fas fa-database text-amber-400 text-sm"></i>
                <span className="text-sm font-medium text-gray-200">类型注册表</span>
                <code className="text-[10px] text-gray-500 bg-gray-800 px-1.5 py-0.5 rounded">src/runtime/commands/types/value_types.json</code>
              </div>
              <div className="flex items-center gap-2">
                {status && <span className={`text-xs ${status.includes('失败') || error ? 'text-red-400' : 'text-green-400'}`}>{status}</span>}
                {error && <span className="text-xs text-red-400">{error}</span>}
                <button onClick={saveTypeRegistry}
                  className="text-xs px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-500">
                  <i className="fas fa-save mr-1"></i>保存
                </button>
              </div>
            </div>
            <div className="flex-1 p-4">
              <textarea
                value={typeRegistryJson}
                onChange={e => setTypeRegistryJson(e.target.value)}
                className="w-full h-full p-3 text-[11px] font-mono bg-[#0a0f1a] border border-gray-600 rounded text-gray-300 outline-none resize-none focus:border-blue-500"
                spellCheck={false}
              />
            </div>
            <div className="px-4 py-2 border-t border-gray-700 bg-[#0f172a] text-[10px] text-gray-500">
              编辑 src/runtime/commands/types/value_types.json。此文件是参数类型和值类型的唯一真相源。
            </div>
          </div>
        ) : !form ? (
          <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
            选择一个指令定义或新建
          </div>
        ) : (
          <>
            {/* Toolbar */}
            <div className="px-4 py-2 border-b border-gray-700 flex items-center justify-between bg-[#0f172a] shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-200">{form.label || form.cmd}</span>
                <code className="text-[10px] text-gray-500 bg-gray-800 px-1.5 py-0.5 rounded">{form.cmd}</code>
              </div>
              <div className="flex items-center gap-2">
                {status && <span className={`text-xs ${status.includes('失败') || error ? 'text-red-400' : 'text-green-400'}`}>{status}</span>}
                {error && <span className="text-xs text-red-400">{error}</span>}
                <button onClick={saveDef}
                  className="text-xs px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-500">保存</button>
                <button onClick={deleteDef}
                  className="text-xs px-3 py-1 rounded bg-red-700/60 text-red-200 hover:bg-red-700">删除</button>
              </div>
            </div>

            {/* 4-column layout */}
            <div className="flex-1 flex min-h-0">
              {/* Col 1: 指令配置 */}
              <div className="flex-1 flex flex-col min-w-0 border-r border-gray-700">
                <div className="px-3 py-1.5 border-b border-gray-700 text-[10px] font-medium text-gray-400 bg-[#0f172a] shrink-0">
                  指令配置
                </div>
                <div className="flex-1 overflow-y-auto p-3 space-y-3">
                  {/* Basic info */}
                  <fieldset className="border border-gray-700 rounded p-2.5">
                    <legend className="text-[10px] font-medium text-gray-400 px-1">基本信息</legend>
                    <div className="space-y-2">
                      <div>
                        <div className={labelCls}>类型名</div>
                        <input value={form.cmd} onChange={e => updateField('type', e.target.value)} className={inputCls} />
                      </div>
                      <div>
                        <div className={labelCls}>显示名称</div>
                        <input value={form.label} onChange={e => updateField('label', e.target.value)} className={inputCls} />
                      </div>
                      <div>
                        <div className={labelCls}>分类</div>
                        <div className="relative">
                          <button
                            onClick={() => setForm(prev => ({ ...prev, _catOpen: !prev._catOpen }))}
                            className={`w-full px-2 py-1 bg-[#0f172a] border border-gray-600 rounded text-xs text-left outline-none focus:border-blue-500 flex items-center justify-between`}
                          >
                            <span className="text-gray-200">
                              {(() => {
                                const cats = form.categories || (form.category ? [form.category] : []);
                                if (cats.length === 0) return <span className="text-gray-500">选择分类…</span>;
                                return cats.map(s => categories.find(c => c.slug === s)?.name || s).join(', ');
                              })()}
                            </span>
                            <i className="fas fa-chevron-down text-gray-500 text-[9px]"></i>
                          </button>
                          {form._catOpen && (
                            <div className="absolute z-20 mt-1 w-full bg-[#1a2236] border border-gray-600 rounded shadow-lg max-h-40 overflow-y-auto">
                              {categories.map(cat => {
                                const cats = form.categories || (form.category ? [form.category] : []);
                                const checked = cats.includes(cat.slug);
                                return (
                                  <label key={cat.slug} onClick={() => { const next = checked ? cats.filter(s => s !== cat.slug) : [...cats, cat.slug]; updateField('categories', next); }}
                                    className={`flex items-center gap-2 px-2.5 py-1.5 cursor-pointer text-[10px] hover:bg-gray-700/50 ${checked ? 'text-blue-300' : 'text-gray-300'}`}>
                                    <i className={`fas fa-check text-[9px] ${checked ? 'text-blue-400' : 'text-transparent'}`}></i>
                                    <i className={`fas ${cat.icon || 'fa-folder'} text-[9px] w-3 text-center`}></i>
                                    {cat.name}
                                  </label>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      </div>
                      <div>
                        <div className={labelCls}>指令类型</div>
                        <select value={form.runtime} onChange={e => updateField('runtime', e.target.value)} className={selectCls}>
                          {CMD_TYPES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                        <div className="text-[9px] text-gray-500 mt-0.5 leading-tight">
                          {CMD_TYPES.find(t => t.value === form.runtime)?.desc}
                        </div>
                      </div>
                      {/* Icon preview + picker */}
                      <div>
                        <div className={labelCls}>图标</div>
                        <button
                          onClick={() => setForm(prev => ({ ...prev, _iconOpen: !prev._iconOpen }))}
                          className="w-full px-2 py-1.5 bg-[#0f172a] border border-gray-600 rounded text-xs outline-none focus:border-blue-500 flex items-center gap-2 hover:border-gray-500"
                        >
                          <span
                            className="w-7 h-7 rounded flex items-center justify-center text-sm shrink-0"
                            style={{
                              color: _iconHex(form.iconColor),
                              backgroundColor: _bgHex(form.bgColor),
                            }}
                          >
                            <i className={`fas ${form.icon || 'fa-circle'}`}></i>
                          </span>
                          <span className="text-gray-400 flex-1 text-left truncate">{form.icon || 'fa-circle'}</span>
                          <i className="fas fa-chevron-down text-gray-500 text-[9px]"></i>
                        </button>
                        {form._iconOpen && (
                          <div className="mt-1 p-2 bg-[#1a2236] border border-gray-600 rounded grid grid-cols-6 gap-1 max-h-36 overflow-y-auto">
                            {ICONS.map(i => (
                              <button
                                key={i}
                                onClick={() => { updateField('icon', i); }}
                                className={`w-7 h-7 rounded flex items-center justify-center text-xs ${
                                  form.icon === i ? 'ring-2 ring-blue-400' : ''
                                }`}
                                style={{
                                  color: _iconHex(form.iconColor),
                                  backgroundColor: _bgHex(form.bgColor),
                                }}
                                title={i}
                              >
                                <i className={`fas ${i}`}></i>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                      <div>
                        <div className={labelCls}>图标颜色</div>
                        <button
                          onClick={() => setForm(prev => ({ ...prev, _icolorOpen: !prev._icolorOpen }))}
                          className="w-full px-2 py-1 bg-[#0f172a] border border-gray-600 rounded text-xs outline-none focus:border-blue-500 flex items-center gap-2 hover:border-gray-500"
                        >
                          <span className="w-4 h-4 rounded-sm shrink-0" style={{ backgroundColor: _iconHex(form.iconColor) }}></span>
                          <span className="text-gray-300 flex-1 text-left">{form.iconColor || 'text-blue-500'}</span>
                          <i className="fas fa-chevron-down text-gray-500 text-[9px]"></i>
                        </button>
                        {form._icolorOpen && (
                          <div className="mt-1 p-2 bg-[#1a2236] border border-gray-600 rounded grid grid-cols-8 gap-1">
                            {PALETTE.map(c => (
                              <button
                                key={'icon-' + c.name}
                                onClick={() => updateField('iconColor', `text-${c.name}-500`)}
                                className={`w-5 h-5 rounded-sm border cursor-pointer transition ${
                                  (form.iconColor || '').includes(c.name) ? 'ring-1 ring-white' : 'border-gray-600'
                                }`}
                                style={{ backgroundColor: c.hex }}
                                title={c.name}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                      <div>
                        <div className={labelCls}>背景颜色</div>
                        <button
                          onClick={() => setForm(prev => ({ ...prev, _bgcolorOpen: !prev._bgcolorOpen }))}
                          className="w-full px-2 py-1 bg-[#0f172a] border border-gray-600 rounded text-xs outline-none focus:border-blue-500 flex items-center gap-2 hover:border-gray-500"
                        >
                          <span className="w-4 h-4 rounded-sm shrink-0 border border-gray-500" style={{ backgroundColor: _bgHex(form.bgColor) }}></span>
                          <span className="text-gray-300 flex-1 text-left">{form.bgColor || 'bg-blue-50'}</span>
                          <i className="fas fa-chevron-down text-gray-500 text-[9px]"></i>
                        </button>
                        {form._bgcolorOpen && (
                          <div className="mt-1 p-2 bg-[#1a2236] border border-gray-600 rounded grid grid-cols-8 gap-1">
                            {PALETTE.map(c => (
                              <button
                                key={'bg-' + c.name}
                                onClick={() => updateField('bgColor', `bg-${c.name}-50`)}
                                className={`w-5 h-5 rounded-sm border cursor-pointer transition ${
                                  (form.bgColor || '').includes(c.name) ? 'ring-1 ring-white' : 'border-gray-600'
                                }`}
                                style={{ backgroundColor: c.hex50 }}
                                title={c.name}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                      <div>
                        <div className={labelCls}>指令排序</div>
                        <input type="number" value={form.commandOrder ?? 0} onChange={e => updateField('commandOrder', parseInt(e.target.value) || 0)}
                          className={inputCls} />
                      </div>
                      <div className="flex items-center gap-3 flex-wrap">
                        <label className="flex items-center gap-1.5 text-[10px] text-gray-400 cursor-pointer">
                          <input type="checkbox" checked={form.enabled !== false} onChange={e => updateField('enabled', e.target.checked)}
                            className="accent-blue-500" />
                          启用
                        </label>
                        {!isControl && (
                          <label className="flex items-center gap-1.5 text-[10px] text-gray-400 cursor-pointer">
                            <input type="checkbox" checked={form.isContainer || false} onChange={e => updateField('isContainer', e.target.checked)}
                              className="accent-green-500" />
                            容器指令
                          </label>
                        )}
                        {form.isContainer && (
                          <input value={form.closesWith || ''} onChange={e => updateField('closesWith', e.target.value)}
                            className={`${inputCls} w-28 text-[10px]`} placeholder="闭合标记如 endFor" />
                        )}
                      </div>
                      <div>
                        <div className={labelCls}>描述</div>
                        <textarea value={form.description || ''} onChange={e => updateField('description', e.target.value)}
                          className={`${inputCls} h-12 resize-none`} />
                      </div>
                    </div>
                  </fieldset>

                  {/* Handler info (derived from instruction type) */}
                  <div className="border border-gray-700 rounded p-2.5 bg-[#0a0f1a]/50">
                    <div className="text-[10px] font-medium text-gray-400 mb-1.5">Handler 文件</div>
                    {isControl ? (
                      <div className="text-[10px] text-gray-500">无需 handler，由流程引擎直接解释执行</div>
                    ) : isBackend ? (
                      <div className="text-[10px] text-gray-300 font-mono">commands/backend_commands/{form.cmd}.py</div>
                    ) : (
                      <div className="text-[10px] text-gray-300 font-mono">commands/extension_commands/{form.cmd}.py</div>
                    )}
                  </div>

                  {/* Params */}
                  <fieldset className="border border-gray-700 rounded p-2.5">
                    <legend className="text-[10px] font-medium text-gray-400 px-1 flex items-center gap-2">
                      参数
                      <button onClick={addParam} className="text-[10px] text-blue-400 hover:text-blue-300">+ 添加</button>
                    </legend>
                    <div className="space-y-2">
                      {(form.params || []).map((p, i) => (
                        <div key={i} className="bg-[#0a0f1a] rounded p-2">
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="text-[10px] text-gray-500">#{i + 1}</span>
                            <button onClick={() => removeParam(i)} className="text-red-400 hover:text-red-300 text-[10px]" title="删除">
                              <i className="fas fa-trash-alt"></i>
                            </button>
                          </div>
                          <div className="grid grid-cols-2 gap-1.5 mb-1.5">
                            <div>
                              <div className="text-[9px] text-gray-500 mb-0.5">变量名</div>
                              <input value={p.name || ''} onChange={e => updateParam(i, 'name', e.target.value)}
                                className={`${inputCls} text-[10px]`} placeholder="url" />
                            </div>
                            <div>
                              <div className="text-[9px] text-gray-500 mb-0.5">显示名</div>
                              <input value={p.label || ''} onChange={e => updateParam(i, 'label', e.target.value)}
                                className={`${inputCls} text-[10px]`} placeholder="目标地址" />
                            </div>
                          </div>
                          <div className="grid grid-cols-3 gap-1.5 mb-1.5">
                            <div>
                              <div className="text-[9px] text-gray-500 mb-0.5">类型</div>
                              <select value={p.type || 'str-input'} onChange={e => updateParam(i, 'type', e.target.value)} className={`${selectCls} text-[10px]`}>
                                {PARAM_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                              </select>
                            </div>
                            <div>
                              <div className="text-[9px] text-gray-500 mb-0.5">分组</div>
                              <select value={p.group || '主属性'} onChange={e => updateParam(i, 'group', e.target.value)}
                                className={`${selectCls} text-[10px]`}>
                                {PARAM_GROUPS.map(g => <option key={g.v} value={g.v}>{g.l}</option>)}
                              </select>
                            </div>
                            <div className="flex items-end pb-1 gap-2">
                              <label className="flex items-center gap-1 text-[10px] text-gray-400">
                                <input type="checkbox" checked={p.required || false} onChange={e => updateParam(i, 'required', e.target.checked)} />
                                必填
                              </label>
                            </div>
                          </div>
                          {Object.keys(valueTypes).length > 0 && (
                            <div className="mb-1.5">
                              <div className="text-[9px] text-gray-500 mb-0.5">期望值类型</div>
                              <select
                                value={p.valueType || ''}
                                onChange={e => updateParam(i, 'valueType', e.target.value || undefined)}
                                className={`${selectCls} text-[10px]`}
                              >
                                <option value="">— 不指定 —</option>
                                {Object.entries(valueTypes).map(([k, v]) => (
                                  <option key={k} value={k}>{v.label || k}</option>
                                ))}
                              </select>
                            </div>
                          )}
                          <div className="grid grid-cols-2 gap-1.5 mb-1.5">
                            <div>
                              <div className="text-[9px] text-gray-500 mb-0.5">默认值</div>
                              <input value={p.default !== undefined ? String(p.default) : ''} onChange={e => updateParam(i, 'default', e.target.value)}
                                className={`${inputCls} text-[10px]`} placeholder="默认值" />
                            </div>
                            <div>
                              <div className="text-[9px] text-gray-500 mb-0.5">占位提示</div>
                              <input value={p.placeholder || ''} onChange={e => updateParam(i, 'placeholder', e.target.value)}
                                className={`${inputCls} text-[10px]`} placeholder="输入提示..." />
                            </div>
                          </div>
                          <div className="mb-1.5">
                            <div className="text-[9px] text-gray-500 mb-0.5">参数说明</div>
                            <input value={p.description || ''} onChange={e => updateParam(i, 'description', e.target.value)}
                              className={`${inputCls} text-[10px]`} placeholder="向用户说明该参数的用途" />
                          </div>
                          {(p.type === 'str-dropdown') && (
                            <div>
                              <div className="text-[9px] text-gray-500 mb-0.5 flex items-center justify-between">
                                <span>下拉选项</span>
                                <button onClick={() => {
                                  const opts = [...(p.options || []), { label: '', value: '' }];
                                  updateParam(i, 'options', opts);
                                }} className="text-[10px] text-blue-400 hover:text-blue-300">+ 添加</button>
                              </div>
                              {(p.options || []).map((opt, oi) => (
                                <div key={oi} className="flex items-center gap-1 mb-1">
                                  <input value={opt.label || ''} onChange={e => {
                                    const opts = [...(p.options || [])];
                                    opts[oi] = { ...opts[oi], label: e.target.value };
                                    updateParam(i, 'options', opts);
                                  }} className={`${inputCls} text-[10px] flex-1`} placeholder="显示名" />
                                  <input value={opt.value || ''} onChange={e => {
                                    const opts = [...(p.options || [])];
                                    opts[oi] = { ...opts[oi], value: e.target.value };
                                    updateParam(i, 'options', opts);
                                  }} className={`${inputCls} text-[10px] flex-1`} placeholder="值" />
                                  <button onClick={() => {
                                    updateParam(i, 'options', (p.options || []).filter((_, j) => j !== oi));
                                  }} className="text-red-400 hover:text-red-300 text-[10px] shrink-0"><i className="fas fa-times"></i></button>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </fieldset>
                </div>
              </div>

              {/* Col 2: JSON 预览 / 类型注册表 */}
              <div className="flex-1 flex flex-col min-w-0 border-r border-gray-700">
                <div className="px-3 py-1.5 border-b border-gray-700 text-[10px] font-medium text-gray-400 bg-[#0f172a] shrink-0 flex items-center justify-between">
                  <span>{showTypeRegistry ? '类型注册表' : 'JSON 预览'}</span>
                  <button
                    onClick={() => setShowTypeRegistry(v => !v)}
                    className="text-[10px] px-1.5 py-0.5 rounded bg-gray-700/50 text-gray-300 hover:bg-gray-600"
                  >{showTypeRegistry ? 'JSON' : '类型'}</button>
                </div>
                {showTypeRegistry ? (
                  <div className="flex-1 flex flex-col min-h-0">
                    <textarea
                      value={typeRegistryJson}
                      onChange={e => setTypeRegistryJson(e.target.value)}
                      className="flex-1 p-3 text-[10px] font-mono bg-[#0a0f1a] text-gray-300 outline-none resize-none"
                      spellCheck={false}
                    />
                    <div className="px-2 py-1.5 border-t border-gray-700 bg-[#0a0f1a] shrink-0">
                      <button onClick={saveTypeRegistry}
                        className="text-[10px] px-2 py-1 rounded bg-green-700/60 text-green-300 hover:bg-green-700 w-full">
                        保存类型注册表
                      </button>
                    </div>
                  </div>
                ) : (
                  <pre className="flex-1 overflow-auto p-3 text-[10px] text-gray-300 font-mono bg-[#0a0f1a] whitespace-pre-wrap m-0 leading-relaxed">
                    {JSON.stringify(form, null, 2)}
                  </pre>
                )}
              </div>

              {/* Col 3: Python Handler 预览 */}
              <div className="flex-1 flex flex-col min-w-0 border-r border-gray-700">
                <div className="px-3 py-1.5 border-b border-gray-700 text-[10px] font-medium text-gray-400 bg-[#0f172a] shrink-0">
                  Python Handler 预览
                </div>
                {!isControl && (
                  <div className="px-3 py-1.5 border-b border-gray-700/50 bg-[#0a0f1a] shrink-0">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] text-gray-400">操作</span>
                      <div className="flex items-center gap-1.5">
                        <button onClick={generateHandlerWithAI} disabled={aiLoading}
                          className="text-[10px] px-2 py-1 rounded bg-purple-600/80 text-white hover:bg-purple-500 disabled:opacity-50 disabled:cursor-not-allowed">
                          {aiLoading ? '生成中…' : 'AI 生成'}
                        </button>
                        <button onClick={reviewHandler} disabled={aiLoading || !pythonCode}
                          className="text-[10px] px-2 py-1 rounded bg-emerald-600/80 text-white hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed">
                          Review
                        </button>
                        <button onClick={savePythonCode} disabled={!pythonCode}
                          className="text-[10px] px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed">
                          保存
                        </button>
                      </div>
                    </div>
                    <span className="text-[10px] text-gray-500 font-mono">commands/{isBackend ? 'backend' : 'extension'}_commands/{form.cmd}.py</span>
                    {/* Review findings */}
                    {reviewFindings && reviewFindings.length > 0 && (
                      <div className="mt-2 max-h-32 overflow-y-auto space-y-1">
                        {reviewFindings.map((f, i) => (
                          <div key={i} className={`text-[10px] px-2 py-1 rounded ${
                            f.level === 'error' ? 'bg-red-900/30 text-red-300 border border-red-800' :
                            f.level === 'warning' ? 'bg-yellow-900/30 text-yellow-300 border border-yellow-800' :
                            'bg-blue-900/30 text-blue-300 border border-blue-800'
                          }`}>
                            <span className="font-medium">{f.check}</span>
                            {f.line && <span className="text-gray-500 ml-1">L{f.line}</span>}
                            <span className="mx-1">—</span>
                            {f.message}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                <textarea
                  value={pythonCode}
                  onChange={e => setPythonCode(e.target.value)}
                  disabled={isControl}
                  className="flex-1 p-3 text-[11px] font-mono bg-[#0a0f1a] text-gray-300 outline-none resize-none disabled:opacity-50"
                  spellCheck={false}
                  placeholder={isControl ? '控制指令无需 Python handler' : '# Python handler 代码 — 点击「AI 生成」或手动编写'}
                />
              </div>

              {/* Col 4: JS Handler 预览 */}
              <div className="flex-1 flex flex-col min-w-0">
                <div className="px-3 py-1.5 border-b border-gray-700 text-[10px] font-medium text-gray-400 bg-[#0f172a] shrink-0">
                  JS Handler 预览
                </div>
                {isExtension && (
                  <div className="px-3 py-1 border-b border-gray-700/50 bg-[#0a0f1a] shrink-0">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] text-gray-400">操作</span>
                      <div className="flex items-center gap-1.5">
                        <button onClick={async () => {
                          setAiLoading(true); setError('');
                          try {
                            const definition = { cmd: form.cmd, label: form.label, category: form.category, runtime: form.runtime, description: form.description, params: form.params || [] };
                            const res = await api.generateWithScenario('command_extension_js', { definition });
                            setJsCode(res.code || '');
                            setStatus('AI 生成完成');
                          } catch (e) { setError('AI 生成失败: ' + e.message); }
                          finally { setAiLoading(false); }
                        }} disabled={aiLoading}
                          className="text-[10px] px-2 py-1 rounded bg-purple-600/80 text-white hover:bg-purple-500 disabled:opacity-50 disabled:cursor-not-allowed">
                          {aiLoading ? '生成中…' : 'AI 生成'}
                        </button>
                        <button onClick={async () => { try { await api.saveJsHandlerCode(form.cmd, jsCode); setStatus('JS 代码已保存'); } catch(e) { setError('保存失败: ' + e.message); } }} disabled={!jsCode}
                          className="text-[10px] px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed">
                          保存
                        </button>
                      </div>
                    </div>
                    <span className="text-[10px] text-gray-500 font-mono">{(form.handler && form.handler.source) || `extension/dom_handlers_new/${form.cmd}.js`}</span>
                  </div>
                )}
                <textarea
                  value={jsCode}
                  onChange={e => setJsCode(e.target.value)}
                  disabled={!isExtension}
                  className="flex-1 p-3 text-[11px] font-mono bg-[#0a0f1a] text-gray-300 outline-none resize-none disabled:opacity-50"
                  spellCheck={false}
                  placeholder={isControl ? '控制指令无需 JS handler' : isExtension ? '// JS handler 代码' : '仅扩展端执行指令支持 JS handler'}
                />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
