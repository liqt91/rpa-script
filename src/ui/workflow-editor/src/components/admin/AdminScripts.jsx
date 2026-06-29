import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api';

const PARAM_TYPES = ['string', 'integer', 'float', 'boolean', 'url', 'enum'];

function parseDefault(type, raw) {
  if (raw === '') return undefined;
  if (type === 'integer') return parseInt(raw, 10);
  if (type === 'float') return parseFloat(raw);
  if (type === 'boolean') return raw === 'true' || raw === '1';
  return raw;
}

export default function AdminScripts() {
  const [scripts, setScripts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ name: '', job_yaml: '', main_py: '' });

  const [source, setSource] = useState(null);
  const [edit, setEdit] = useState(null);
  const [test, setTest] = useState(null);
  const [testResult, setTestResult] = useState(null);

  useEffect(() => {
    loadScripts();
  }, []);

  async function loadScripts() {
    setLoading(true);
    try {
      const data = await api.listScripts();
      setScripts(data.scripts || []);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(e) {
    e.preventDefault();
    try {
      await api.createScript(createForm.name, createForm.job_yaml, createForm.main_py);
      setShowCreate(false);
      setCreateForm({ name: '', job_yaml: '', main_py: '' });
      loadScripts();
    } catch (e) {
      setError(e.message);
    }
  }

  async function viewSource(name) {
    try {
      const data = await api.getScriptSource(name);
      setSource(data);
    } catch (e) {
      setError(e.message);
    }
  }

  function editMeta(script) {
    setEdit({
      originalName: script.name,
      name: script.name,
      version: script.version || '',
      description: script.description || '',
      author: script.author || '',
      main: script.main || 'main.py',
      requirements_file: script.requirements_file || 'requirements.txt',
      min_client_version: script.min_client_version || '0.0.0',
      enabled: script.enabled !== false,
      params: Object.entries(script.params || {}).map(([k, v]) => ({
        id: Math.random().toString(36).slice(2),
        name: k,
        type: v.type || 'string',
        description: v.description || '',
        default: v.default !== undefined && v.default !== null ? String(v.default) : '',
        required: !!v.required,
        min: v.constraints?.min !== undefined && v.constraints?.min !== null ? String(v.constraints.min) : '',
        max: v.constraints?.max !== undefined && v.constraints?.max !== null ? String(v.constraints.max) : '',
      })),
    });
  }

  function updateEdit(updater) {
    setEdit(prev => updater(prev));
  }

  function addParam() {
    updateEdit(prev => ({
      ...prev,
      params: [...prev.params, { id: Math.random().toString(36).slice(2), name: '', type: 'string', description: '', default: '', required: false, min: '', max: '' }],
    }));
  }

  function removeParam(id) {
    updateEdit(prev => ({ ...prev, params: prev.params.filter(p => p.id !== id) }));
  }

  function updateParam(id, field, value) {
    updateEdit(prev => ({
      ...prev,
      params: prev.params.map(p => p.id === id ? { ...p, [field]: value } : p),
    }));
  }

  const yamlPreview = useMemo(() => {
    if (!edit) return '';
    const params = {};
    edit.params.forEach(p => {
      if (!p.name.trim()) return;
      const defaultVal = parseDefault(p.type, p.default);
      const constraints = {};
      if (p.min !== '') constraints.min = parseFloat(p.min);
      if (p.max !== '') constraints.max = parseFloat(p.max);
      params[p.name.trim()] = {
        type: p.type,
        description: p.description,
        default: defaultVal,
        required: p.required,
        constraints: Object.keys(constraints).length ? constraints : undefined,
      };
    });
    const data = {
      name: edit.name,
      version: edit.version,
      description: edit.description,
      author: edit.author,
      main: edit.main,
      requirements_file: edit.requirements_file,
      min_client_version: edit.min_client_version,
      enabled: edit.enabled,
      params,
    };
    let yaml = `name: ${data.name}\n`;
    yaml += `version: ${data.version}\n`;
    yaml += `description: ${data.description}\n`;
    yaml += `author: ${data.author}\n`;
    yaml += `main: ${data.main}\n`;
    yaml += `requirements_file: ${data.requirements_file}\n`;
    yaml += `min_client_version: ${data.min_client_version}\n`;
    yaml += `enabled: ${data.enabled}\n`;
    yaml += `params:\n`;
    if (Object.keys(params).length === 0) {
      yaml += `  {}\n`;
    } else {
      Object.entries(params).forEach(([k, v]) => {
        yaml += `  ${k}:\n`;
        yaml += `    type: ${v.type}\n`;
        if (v.description) yaml += `    description: ${v.description}\n`;
        if (v.default !== undefined) yaml += `    default: ${JSON.stringify(v.default)}\n`;
        yaml += `    required: ${v.required}\n`;
        if (v.constraints) {
          yaml += `    constraints:\n`;
          if (v.constraints.min !== undefined) yaml += `      min: ${v.constraints.min}\n`;
          if (v.constraints.max !== undefined) yaml += `      max: ${v.constraints.max}\n`;
        }
      });
    }
    return yaml;
  }, [edit]);

  async function saveMeta() {
    const params = {};
    edit.params.forEach(p => {
      if (!p.name.trim()) return;
      const defaultVal = parseDefault(p.type, p.default);
      const constraints = {};
      if (p.min !== '') constraints.min = parseFloat(p.min);
      if (p.max !== '') constraints.max = parseFloat(p.max);
      params[p.name.trim()] = {
        type: p.type,
        description: p.description,
        default: defaultVal,
        required: p.required,
        constraints: Object.keys(constraints).length ? constraints : undefined,
      };
    });
    const payload = {
      name: edit.name,
      version: edit.version,
      description: edit.description,
      author: edit.author,
      main: edit.main,
      requirements_file: edit.requirements_file,
      min_client_version: edit.min_client_version,
      enabled: edit.enabled,
      params,
    };
    try {
      await api.updateScriptMeta(edit.originalName, payload);
      setEdit(null);
      loadScripts();
    } catch (e) {
      setError(e.message);
    }
  }

  async function toggleEnabled(script) {
    const payload = {
      name: script.name,
      version: script.version,
      description: script.description,
      author: script.author,
      main: script.main,
      requirements_file: script.requirements_file,
      min_client_version: script.min_client_version,
      enabled: !script.enabled,
      params: script.params,
    };
    try {
      await api.updateScriptMeta(script.name, payload);
      loadScripts();
    } catch (e) {
      setError(e.message);
    }
  }

  async function startTest(name, url, paramsJson) {
    try {
      const data = await api.testScript(name, url, paramsJson);
      const taskId = data.task_id;
      setTestResult({ status: 'running', result: null, error: null });
      const interval = setInterval(async () => {
        try {
          const r = await api.getScriptTestResult(taskId);
          if (r.status === 'done') {
            clearInterval(interval);
            setTestResult({ status: 'done', result: r.result, error: null });
          } else if (r.status === 'failed') {
            clearInterval(interval);
            setTestResult({ status: 'failed', result: null, error: r.error });
          }
        } catch (e) {
          clearInterval(interval);
          setTestResult({ status: 'failed', result: null, error: e.message });
        }
      }, 1000);
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">脚本管理</h1>
          <p className="text-gray-500 text-sm mt-1">查看、编辑、测试和创建脚本</p>
        </div>
        <div className="flex gap-2">
          <button onClick={loadScripts} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm transition-colors">
            <i className="fas fa-sync-alt mr-2"></i>刷新
          </button>
          <button onClick={() => setShowCreate(true)} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors">
            <i className="fas fa-plus mr-2"></i>创建脚本
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
          <i className="fas fa-exclamation-circle mr-2"></i>
          {error}
          <button onClick={() => setError(null)} className="ml-2 text-red-400 hover:text-red-200">×</button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <i className="fas fa-circle-notch fa-spin text-blue-400 text-2xl"></i>
          <span className="ml-3 text-gray-400">加载中...</span>
        </div>
      ) : (
        <div className="space-y-3">
          {scripts.length === 0 && <p className="text-gray-500 text-center py-8">暂无脚本</p>}
          {scripts.map(s => (
            <div key={s.name} className="bg-[#1e293b] rounded-xl border border-gray-700 p-5">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <h3 className="text-lg font-medium text-white">{s.name}</h3>
                  <span className="px-2 py-0.5 bg-gray-700 text-gray-300 text-xs rounded">v{s.version}</span>
                  {!s.enabled && <span className="px-2 py-0.5 bg-red-900/30 text-red-400 text-xs rounded">已禁用</span>}
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => viewSource(s.name)} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded-lg transition-colors">查看</button>
                  <button onClick={() => editMeta(s)} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded-lg transition-colors">编辑</button>
                  <button onClick={() => setTest({ name: s.name, url: '', params: '{"scrolls": 1, "delay": 2.0}' })} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg transition-colors">测试</button>
                  <button onClick={() => toggleEnabled(s)} className={`px-3 py-1.5 text-white text-sm rounded-lg transition-colors ${s.enabled ? 'bg-red-600 hover:bg-red-500' : 'bg-green-600 hover:bg-green-500'}`}>
                    {s.enabled ? '禁用' : '启用'}
                  </button>
                </div>
              </div>
              <p className="text-gray-400 text-sm mt-2">{s.description || '无描述'}</p>
              <div className="flex gap-4 mt-3 text-xs text-gray-500">
                <span>作者: {s.author || '-'}</span>
                <span>入口: {s.main}</span>
                <span>参数: {Object.keys(s.params || {}).length} 个</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#1e293b] rounded-xl border border-gray-700 w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h2 className="text-lg font-semibold text-white">创建脚本</h2>
              <button onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-white"><i className="fas fa-times"></i></button>
            </div>
            <form onSubmit={handleCreate} className="p-6 overflow-auto space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1.5">脚本名称 <span className="text-red-400">*</span></label>
                <input value={createForm.name} onChange={e => setCreateForm(f => ({ ...f, name: e.target.value }))} required placeholder="douyin_search" className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" />
                <p className="text-xs text-gray-500 mt-1">只能包含字母、数字、下划线和连字符</p>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1.5">job.yaml <span className="text-red-400">*</span></label>
                <textarea value={createForm.job_yaml} onChange={e => setCreateForm(f => ({ ...f, job_yaml: e.target.value }))} rows={6} required placeholder="name: douyin_search&#10;version: 1.0.0&#10;description: ..." className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white font-mono text-sm"></textarea>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1.5">main.py <span className="text-red-400">*</span></label>
                <textarea value={createForm.main_py} onChange={e => setCreateForm(f => ({ ...f, main_py: e.target.value }))} rows={10} required placeholder="def run(url: str, **params) -> dict:&#10;    return {&quot;total&quot;: 0, &quot;items&quot;: []}" className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white font-mono text-sm"></textarea>
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => setShowCreate(false)} className="px-4 py-2 text-gray-400 hover:text-white text-sm">取消</button>
                <button type="submit" className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium">创建</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {source && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#1e293b] rounded-xl border border-gray-700 w-full max-w-4xl mx-4 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h2 className="text-lg font-semibold text-white">源码查看</h2>
              <button onClick={() => setSource(null)} className="text-gray-400 hover:text-white"><i className="fas fa-times"></i></button>
            </div>
            <div className="p-6 overflow-auto space-y-4">
              <div>
                <h4 className="text-sm font-medium text-gray-300 mb-2">job.yaml</h4>
                <pre className="bg-[#0f172a] rounded-lg p-4 text-sm text-gray-300 font-mono overflow-x-auto">{source.job_yaml || '(无 job.yaml)'}</pre>
              </div>
              <div>
                <h4 className="text-sm font-medium text-gray-300 mb-2">main.py</h4>
                <pre className="bg-[#0f172a] rounded-lg p-4 text-sm text-gray-300 font-mono overflow-x-auto">{source.main_py || '(无 main.py)'}</pre>
              </div>
            </div>
          </div>
        </div>
      )}

      {edit && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#1e293b] rounded-xl border border-gray-700 w-full max-w-5xl mx-4 max-h-[92vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h2 className="text-lg font-semibold text-white">编辑脚本元数据</h2>
              <button onClick={() => setEdit(null)} className="text-gray-400 hover:text-white"><i className="fas fa-times"></i></button>
            </div>
            <div className="p-6 overflow-auto space-y-6">
              <div>
                <h4 className="text-sm font-medium text-gray-300 mb-3">基础信息</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">版本</label>
                    <input value={edit.version} onChange={e => updateEdit(p => ({ ...p, version: e.target.value }))} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">作者</label>
                    <input value={edit.author} onChange={e => updateEdit(p => ({ ...p, author: e.target.value }))} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">入口文件</label>
                    <input value={edit.main} onChange={e => updateEdit(p => ({ ...p, main: e.target.value }))} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">依赖文件</label>
                    <input value={edit.requirements_file} onChange={e => updateEdit(p => ({ ...p, requirements_file: e.target.value }))} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">最低客户端版本</label>
                    <input value={edit.min_client_version} onChange={e => updateEdit(p => ({ ...p, min_client_version: e.target.value }))} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" />
                  </div>
                  <div className="flex items-center gap-3">
                    <input id="editEnabled" type="checkbox" checked={edit.enabled} onChange={e => updateEdit(p => ({ ...p, enabled: e.target.checked }))} className="w-4 h-4 rounded border-gray-600" />
                    <label htmlFor="editEnabled" className="text-sm text-gray-300">启用</label>
                  </div>
                </div>
                <div className="mt-3">
                  <label className="block text-xs text-gray-400 mb-1">描述</label>
                  <input value={edit.description} onChange={e => updateEdit(p => ({ ...p, description: e.target.value }))} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-sm font-medium text-gray-300">参数列表</h4>
                  <button onClick={addParam} className="text-xs px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors">+ 添加参数</button>
                </div>
                <div className="space-y-2">
                  {edit.params.map(p => (
                    <div key={p.id} className="grid grid-cols-12 gap-2 items-center bg-[#0f172a] rounded-lg p-2">
                      <div className="col-span-2">
                        <input value={p.name} onChange={e => updateParam(p.id, 'name', e.target.value)} placeholder="名称" className="w-full px-2 py-1 bg-[#1e293b] border border-gray-600 rounded text-white text-xs" />
                      </div>
                      <div className="col-span-2">
                        <select value={p.type} onChange={e => updateParam(p.id, 'type', e.target.value)} className="w-full px-2 py-1 bg-[#1e293b] border border-gray-600 rounded text-white text-xs">
                          {PARAM_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                        </select>
                      </div>
                      <div className="col-span-3">
                        <input value={p.description} onChange={e => updateParam(p.id, 'description', e.target.value)} placeholder="描述" className="w-full px-2 py-1 bg-[#1e293b] border border-gray-600 rounded text-white text-xs" />
                      </div>
                      <div className="col-span-2">
                        <input value={p.default} onChange={e => updateParam(p.id, 'default', e.target.value)} placeholder="默认值" className="w-full px-2 py-1 bg-[#1e293b] border border-gray-600 rounded text-white text-xs" />
                      </div>
                      <div className="col-span-1 flex items-center justify-center">
                        <input type="checkbox" checked={p.required} onChange={e => updateParam(p.id, 'required', e.target.checked)} className="w-4 h-4" title="必填" />
                      </div>
                      <div className="col-span-1">
                        <input value={p.min} onChange={e => updateParam(p.id, 'min', e.target.value)} placeholder="min" className="w-full px-2 py-1 bg-[#1e293b] border border-gray-600 rounded text-white text-xs" title="最小值" />
                      </div>
                      <div className="col-span-1 flex items-center gap-1">
                        <input value={p.max} onChange={e => updateParam(p.id, 'max', e.target.value)} placeholder="max" className="w-full px-2 py-1 bg-[#1e293b] border border-gray-600 rounded text-white text-xs" title="最大值" />
                        <button onClick={() => removeParam(p.id)} className="text-xs text-red-400 hover:text-red-300">×</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h4 className="text-sm font-medium text-gray-300 mb-2">YAML 预览</h4>
                <pre className="bg-[#0f172a] rounded-lg p-4 text-xs text-gray-300 font-mono overflow-x-auto max-h-48">{yamlPreview}</pre>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button onClick={() => setEdit(null)} className="px-4 py-2 text-gray-400 hover:text-white text-sm">取消</button>
                <button onClick={saveMeta} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium">保存</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {test && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#1e293b] rounded-xl border border-gray-700 w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h2 className="text-lg font-semibold text-white">快速测试: {test.name}</h2>
              <button onClick={() => { setTest(null); setTestResult(null); }} className="text-gray-400 hover:text-white"><i className="fas fa-times"></i></button>
            </div>
            <div className="p-6 overflow-auto">
              <form onSubmit={e => { e.preventDefault(); setTestResult({ status: 'running', result: null, error: null }); startTest(test.name, test.url, test.params); }} className="space-y-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1.5">URL <span className="text-red-400">*</span></label>
                  <input value={test.url} onChange={e => setTest(t => ({ ...t, url: e.target.value }))} required placeholder="https://..." className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1.5">参数（JSON）</label>
                  <textarea value={test.params} onChange={e => setTest(t => ({ ...t, params: e.target.value }))} rows={4} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white font-mono text-sm"></textarea>
                  <p className="text-xs text-gray-500 mt-1">注：scrolls 会被强制限制为 1-3</p>
                </div>
                <div className="flex gap-3">
                  <button type="submit" disabled={testResult?.status === 'running'} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800/50 text-white rounded-lg text-sm font-medium">
                    {testResult?.status === 'running' ? <i className="fas fa-circle-notch fa-spin mr-2"></i> : null}
                    开始测试
                  </button>
                  <button type="button" onClick={() => { setTest(null); setTestResult(null); }} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm">取消</button>
                </div>
              </form>
              {testResult && testResult.status !== 'running' && (
                <div className="mt-4">
                  <p className={`text-sm mb-2 ${testResult.status === 'done' ? 'text-green-400' : 'text-red-400'}`}>
                    {testResult.status === 'done' ? `测试完成，共 ${testResult.result?.total ?? 0} 条` : '测试失败'}
                  </p>
                  <pre className="bg-[#0f172a] rounded-lg p-4 text-xs text-gray-300 font-mono overflow-x-auto max-h-64">
                    {testResult.status === 'done' ? JSON.stringify(testResult.result, null, 2) : testResult.error}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
