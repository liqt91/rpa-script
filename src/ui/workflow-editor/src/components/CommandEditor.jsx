import { useState, useEffect } from 'react';
import { api } from '../api';

const RUNTIME_OPTIONS = [
  { value: 'extension', label: '🌐 浏览器扩展' },
  { value: 'backend', label: '⬡ 后端执行' },
  { value: 'emitter', label: '🔀 流程控制' },
];

const PARAM_TYPES = [
  'str-input', 'str-textarea', 'str-var', 'str-dropdown', 'str-element',
  'int-number', 'bool-check', 'list-input', 'dict-input', 'any-expr', 'any-input',
];

const ICONS = [
  'fa-hand-pointer', 'fa-keyboard', 'fa-font', 'fa-eye', 'fa-eye-slash',
  'fa-link', 'fa-spinner', 'fa-arrows-alt-v', 'fa-arrow-up', 'fa-arrow-down',
  'fa-camera', 'fa-code', 'fa-equals', 'fa-clock', 'fa-list', 'fa-circle',
  'fa-heading', 'fa-hashtag', 'fa-table', 'fa-project-diagram',
];

export default function CommandEditor() {
  const [defs, setDefs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [buildResult, setBuildResult] = useState(null);
  const [showJson, setShowJson] = useState(false);

  useEffect(() => { loadDefinitions(); }, []);

  async function loadDefinitions() {
    try {
      const defs = await api.request('/api/commands/definitions');
      setDefs(defs);
    } catch (e) { setError('加载失败: ' + e.message); }
  }

  function selectDef(d) {
    setSelected(d);
    setForm(structuredClone(d));
    setStatus(''); setError(''); setBuildResult(null);
  }

  function createNew() {
    const type = prompt('指令类型名（英文小写，自动做文件名）:');
    if (!type) return;
    const template = {
      type, label: type, category: '其他', runtime: 'extension',
      icon: 'fa-circle', iconColor: 'text-gray-500', bgColor: 'bg-gray-50',
      categoryOrder: 0, commandOrder: 0, description: '', enabled: true,
      params: [],
      handler: { kind: 'delegate', function: 'doClick' },
    };
    setSelected(template);
    setForm(structuredClone(template));
    setStatus(''); setError('');
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
      await api.request(`/api/commands/definitions/${form.type}`, {
        method: 'PUT',
        body: JSON.stringify(form),
      });
      setSelected(form);
      setStatus('已保存');
      setError('');
      loadDefinitions();
    } catch (e) {
      setError('保存失败: ' + (e.message || ''));
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

  // ── common tailwind classes ──
  const labelCls = 'text-[10px] text-gray-400 mb-0.5';
  const inputCls = 'w-full px-2 py-1 bg-[#0f172a] border border-gray-600 rounded text-gray-200 text-xs outline-none focus:border-blue-500';
  const selectCls = 'w-full px-2 py-1 bg-[#0f172a] border border-gray-600 rounded text-gray-200 text-xs outline-none focus:border-blue-500';

  const jsonPreview = showJson && form ? JSON.stringify(form, null, 2) : null;

  return (
    <div className="flex-1 flex min-h-0">
      {/* Left panel — list */}
      <div className="w-56 bg-[#0f172a] border-r border-gray-700 flex flex-col shrink-0">
        <div className="px-3 py-3 border-b border-gray-700 flex items-center justify-between">
          <span className="text-sm font-medium text-gray-200">指令定义</span>
          <button onClick={createNew} className="text-xs text-blue-400 hover:text-blue-300">+ 新建</button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
          {defs.map(d => {
            const isCur = selected && selected.type === d.type;
            const badge = d.runtime === 'backend' ? '⬡' : d.runtime === 'emitter' ? '🔀' : '🌐';
            return (
              <button key={d.type} onClick={() => selectDef(d)}
                className={`w-full text-left px-2 py-1.5 rounded text-xs transition-colors ${
                  isCur ? 'bg-blue-600/30 text-blue-200' : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'}`}>
                <span className="mr-1.5">{badge}</span>{d.label}
                <span className="text-gray-600 ml-1">{d.type}</span>
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

      {/* Right panel — form */}
      <div className="flex-1 flex flex-col min-w-0">
        {!form ? (
          <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
            选择一个指令定义或新建
          </div>
        ) : (
          <>
            {/* Toolbar */}
            <div className="px-4 py-2 border-b border-gray-700 flex items-center justify-between bg-[#0f172a] shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-200">{form.label || form.type}</span>
                <code className="text-[10px] text-gray-500 bg-gray-800 px-1.5 py-0.5 rounded">{form.type}</code>
              </div>
              <div className="flex items-center gap-2">
                {status && <span className={`text-xs ${status.includes('失败') || error ? 'text-red-400' : 'text-green-400'}`}>{status}</span>}
                {error && <span className="text-xs text-red-400">{error}</span>}
                <button onClick={() => setShowJson(!showJson)}
                  className="text-xs px-2 py-1 rounded bg-gray-700 text-gray-300 hover:bg-gray-600">
                  {showJson ? '隐藏 JSON' : '预览 JSON'}
                </button>
                <button onClick={saveDef}
                  className="text-xs px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-500">保存</button>
              </div>
            </div>

            <div className="flex-1 flex min-h-0">
              {/* Form */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {/* Basic info */}
                <fieldset className="border border-gray-700 rounded p-3">
                  <legend className="text-xs font-medium text-gray-400 px-1">基本信息</legend>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <div className={labelCls}>类型名</div>
                      <input value={form.type} onChange={e => updateField('type', e.target.value)} className={inputCls} />
                    </div>
                    <div>
                      <div className={labelCls}>显示名称</div>
                      <input value={form.label} onChange={e => updateField('label', e.target.value)} className={inputCls} />
                    </div>
                    <div>
                      <div className={labelCls}>分类</div>
                      <input value={form.category} onChange={e => updateField('category', e.target.value)} className={inputCls} placeholder="元素操作" />
                    </div>
                    <div>
                      <div className={labelCls}>执行环境</div>
                      <select value={form.runtime} onChange={e => updateField('runtime', e.target.value)} className={selectCls}>
                        {RUNTIME_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                    </div>
                    <div>
                      <div className={labelCls}>图标</div>
                      <select value={form.icon} onChange={e => updateField('icon', e.target.value)} className={selectCls}>
                        {ICONS.map(i => <option key={i} value={i}>{i}</option>)}
                      </select>
                    </div>
                    <div>
                      <div className={labelCls}>图标颜色</div>
                      <input value={form.iconColor || ''} onChange={e => updateField('iconColor', e.target.value)} className={inputCls} placeholder="text-blue-500" />
                    </div>
                  </div>
                  <div className="mt-2">
                    <div className={labelCls}>描述</div>
                    <textarea value={form.description || ''} onChange={e => updateField('description', e.target.value)}
                      className={`${inputCls} h-12 resize-none`} />
                  </div>
                </fieldset>

                {/* Handler */}
                <fieldset className="border border-gray-700 rounded p-3">
                  <legend className="text-xs font-medium text-gray-400 px-1">Handler</legend>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <div className={labelCls}>类型</div>
                      <select value={form.handler?.kind || 'delegate'} onChange={e => updateHandler('kind', e.target.value)} className={selectCls}>
                        <option value="delegate">delegate（简单委托）</option>
                        <option value="custom">custom（自定义 JS）</option>
                        <option value="backend">backend（后端执行）</option>
                      </select>
                    </div>
                    {form.handler?.kind === 'delegate' && (
                      <div>
                        <div className={labelCls}>委托函数</div>
                        <input value={form.handler?.function || ''} onChange={e => updateHandler('function', e.target.value)}
                          className={inputCls} placeholder="doClick" />
                      </div>
                    )}
                    {form.handler?.kind === 'custom' && (
                      <div>
                        <div className={labelCls}>JS 源文件</div>
                        <input value={form.handler?.source || ''} onChange={e => updateHandler('source', e.target.value)}
                          className={inputCls} placeholder="extension/handlers/xxx.js" />
                      </div>
                    )}
                    {form.handler?.kind === 'backend' && (
                      <div>
                        <div className={labelCls}>Python 源文件</div>
                        <input value={form.handler?.source || ''} onChange={e => updateHandler('source', e.target.value)}
                          className={inputCls} placeholder="handlers/backend/xxx.py" />
                      </div>
                    )}
                  </div>
                </fieldset>

                {/* Params */}
                <fieldset className="border border-gray-700 rounded p-3">
                  <legend className="text-xs font-medium text-gray-400 px-1 flex items-center gap-2">
                    参数
                    <button onClick={addParam} className="text-[10px] text-blue-400 hover:text-blue-300">+ 添加</button>
                  </legend>
                  <div className="space-y-2">
                    {(form.params || []).map((p, i) => (
                      <div key={i} className="flex items-center gap-2 bg-[#0a0f1a] rounded p-2">
                        <button onClick={() => removeParam(i)} className="text-red-400 hover:text-red-300 text-xs shrink-0" title="删除">
                          <i className="fas fa-times"></i>
                        </button>
                        <div className="flex-1 grid grid-cols-4 gap-2">
                          <div>
                            <div className={labelCls}>变量名</div>
                            <input value={p.name || ''} onChange={e => updateParam(i, 'name', e.target.value)}
                              className={inputCls} placeholder="element_name" />
                          </div>
                          <div>
                            <div className={labelCls}>显示名</div>
                            <input value={p.label || ''} onChange={e => updateParam(i, 'label', e.target.value)}
                              className={inputCls} placeholder="元素" />
                          </div>
                          <div>
                            <div className={labelCls}>类型</div>
                            <select value={p.type || 'text'} onChange={e => updateParam(i, 'type', e.target.value)} className={selectCls}>
                              {PARAM_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                            </select>
                          </div>
                          <div className="flex items-end gap-1">
                            <label className="flex items-center gap-1 text-[10px] text-gray-400 pb-1">
                              <input type="checkbox" checked={p.required || false} onChange={e => updateParam(i, 'required', e.target.checked)} />
                              必填
                            </label>
                            <div className="flex-1">
                              <div className={labelCls}>分组</div>
                              <input value={p.group || ''} onChange={e => updateParam(i, 'group', e.target.value)}
                                className={inputCls} placeholder="主属性" />
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </fieldset>
              </div>

              {/* JSON preview (right side) */}
              {showJson && (
                <div className="w-80 border-l border-gray-700 flex flex-col shrink-0">
                  <div className="px-3 py-1.5 border-b border-gray-700 text-[10px] text-gray-500 bg-[#0f172a]">
                    实时预览
                  </div>
                  <pre className="flex-1 overflow-auto p-3 text-[10px] text-gray-300 font-mono bg-[#0a0f1a] whitespace-pre-wrap m-0">
                    {jsonPreview}
                  </pre>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
