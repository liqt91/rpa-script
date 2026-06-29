import { useEffect, useState } from 'react';
import { api } from '../../api';

const APP_TYPES = [
  { value: 'chat', label: 'chat（/v1/chat-messages）' },
  { value: 'agent', label: 'agent（/v1/chat-messages）' },
  { value: 'text', label: 'text（/v1/completion-messages）' },
  { value: 'chatflow', label: 'chatflow（/v1/chat-messages）' },
  { value: 'workflow', label: 'workflow（/v1/workflows/run）' },
];

const SCHEMA_TYPES = ['string', 'integer', 'float', 'boolean', 'array', 'object'];

const ENDPOINTS = {
  text: '/v1/completion-messages',
  chat: '/v1/chat-messages',
  agent: '/v1/chat-messages',
  chatflow: '/v1/chat-messages',
  workflow: '/v1/workflows/run',
};

const PAYLOAD_TEMPLATES = {
  text: '{\n  "query": "测试问题",\n  "inputs": {},\n  "response_mode": "blocking",\n  "user": "test-user"\n}',
  chat: '{\n  "query": "测试问题",\n  "inputs": {},\n  "response_mode": "blocking",\n  "user": "test-user"\n}',
  agent: '{\n  "query": "测试问题",\n  "inputs": {},\n  "response_mode": "blocking",\n  "user": "test-user"\n}',
  chatflow: '{\n  "query": "测试问题",\n  "inputs": {},\n  "response_mode": "blocking",\n  "user": "test-user"\n}',
  workflow: '{\n  "inputs": {\n    "key": "value"\n  },\n  "response_mode": "blocking",\n  "user": "test-user"\n}',
};

export default function AdminAIApps() {
  const [apps, setApps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [modal, setModal] = useState(null);
  const [test, setTest] = useState(null);
  const [testResponse, setTestResponse] = useState(null);

  useEffect(() => {
    loadApps();
  }, []);

  async function loadApps() {
    setLoading(true);
    try {
      const data = await api.listAIApps();
      setApps(data.apps || []);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function openCreate() {
    setModal({
      mode: 'create',
      type: '',
      name: '',
      api_key: '',
      app_type: 'chat',
      enabled: true,
      input_schema: [],
    });
  }

  function openEdit(app) {
    setModal({
      mode: 'edit',
      originalType: app.type,
      type: app.type,
      name: app.name,
      api_key: app.api_key || '',
      app_type: app.app_type,
      enabled: app.enabled,
      input_schema: Object.entries(app.input_schema || {}).map(([k, v]) => ({ id: Math.random().toString(36).slice(2), name: k, ...v })),
    });
  }

  function updateModal(updater) {
    setModal(prev => updater(prev));
  }

  function addSchemaRow(initial = {}) {
    updateModal(prev => ({
      ...prev,
      input_schema: [...prev.input_schema, { id: Math.random().toString(36).slice(2), name: '', type: 'string', required: false, description: '', ...initial }],
    }));
  }

  function removeSchemaRow(id) {
    updateModal(prev => ({ ...prev, input_schema: prev.input_schema.filter(r => r.id !== id) }));
  }

  function updateSchemaRow(id, field, value) {
    updateModal(prev => ({
      ...prev,
      input_schema: prev.input_schema.map(r => r.id === id ? { ...r, [field]: value } : r),
    }));
  }

  async function fetchParameters() {
    if (!modal.type.trim()) {
      setError('请先填写类型标识');
      return;
    }
    try {
      const data = await api.getAIAppParameters(modal.type.trim());
      const schema = data.input_schema || {};
      const entries = Object.entries(schema);
      if (entries.length === 0) {
        setError('该应用未配置 user_input_form 参数');
        return;
      }
      updateModal(prev => ({
        ...prev,
        input_schema: entries.map(([k, v]) => ({ id: Math.random().toString(36).slice(2), name: k, type: v.type || 'string', required: !!v.required, description: v.description || '' })),
      }));
    } catch (e) {
      setError(e.message);
    }
  }

  async function saveApp() {
    const schema = {};
    modal.input_schema.forEach(r => {
      if (!r.name.trim()) return;
      schema[r.name.trim()] = {
        type: r.type,
        required: r.required,
        description: r.description,
      };
    });
    const payload = {
      type: modal.type.trim(),
      name: modal.name.trim(),
      api_key: modal.api_key,
      app_type: modal.app_type,
      enabled: modal.enabled,
      input_schema: schema,
    };
    try {
      if (modal.mode === 'create') {
        await api.createAIApp(payload);
      } else {
        await api.updateAIApp(modal.originalType, payload);
      }
      setModal(null);
      loadApps();
    } catch (e) {
      setError(e.message);
    }
  }

  async function deleteApp(type, name) {
    if (!confirm(`确定删除 AI 应用 "${name}" (${type}) 吗？`)) return;
    try {
      await api.deleteAIApp(type);
      loadApps();
    } catch (e) {
      setError(e.message);
    }
  }

  async function submitTest() {
    if (!test) return;
    setTestResponse({ status: 'loading', body: null });
    let payload;
    try {
      payload = JSON.parse(test.payload);
    } catch (e) {
      setTestResponse({ status: 'error', body: `Payload JSON 格式错误: ${e.message}` });
      return;
    }
    try {
      const data = await api.invokeAI(test.app.type, payload);
      setTestResponse({ status: 'ok', body: JSON.stringify(data, null, 2) });
    } catch (e) {
      setTestResponse({ status: 'error', body: e.message });
    }
  }

  function openTest(app) {
    setTest({ app, payload: PAYLOAD_TEMPLATES[app.app_type] || PAYLOAD_TEMPLATES.chat });
    setTestResponse(null);
  }

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">AI 应用管理</h1>
          <p className="text-gray-500 text-sm mt-1">服务端只做校验 + 加 appkey + 转发</p>
        </div>
        <button onClick={openCreate} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors">
          <i className="fas fa-plus mr-2"></i>新增应用
        </button>
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
        <div className="bg-[#1e293b] rounded-xl border border-gray-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 bg-[#252f47]">
                <th className="text-left px-4 py-3 font-medium text-gray-400">名称</th>
                <th className="text-left px-4 py-3 font-medium text-gray-400">类型</th>
                <th className="text-left px-4 py-3 font-medium text-gray-400">API Key</th>
                <th className="text-left px-4 py-3 font-medium text-gray-400">App 类型</th>
                <th className="text-left px-4 py-3 font-medium text-gray-400">Endpoint</th>
                <th className="text-left px-4 py-3 font-medium text-gray-400">启用</th>
                <th className="text-left px-4 py-3 font-medium text-gray-400">操作</th>
              </tr>
            </thead>
            <tbody>
              {apps.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-500">暂无 AI 应用</td>
                </tr>
              )}
              {apps.map(a => {
                const schemaFields = a.input_schema ? Object.keys(a.input_schema).length : 0;
                return (
                  <tr key={a.type} className="border-b border-gray-700/50 hover:bg-[#252f47] transition-colors">
                    <td className="px-4 py-3">
                      <div className="text-white font-medium">{a.name}</div>
                      {schemaFields > 0 && <span className="px-2 py-0.5 bg-blue-900/30 text-blue-400 text-xs rounded">{schemaFields} 个 inputs 字段</span>}
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{a.type}</td>
                    <td className="px-4 py-3 font-mono text-xs">
                      {a.api_key ? (
                        <span className="px-2 py-0.5 bg-green-900/30 text-green-400 text-xs rounded">{a.api_key.substring(0, 8)}****</span>
                      ) : (
                        <span className="px-2 py-0.5 bg-red-900/30 text-red-400 text-xs rounded">未配置</span>
                      )}
                    </td>
                    <td className="px-4 py-3"><span className="px-2 py-0.5 bg-gray-700 text-gray-300 text-xs rounded">{a.app_type}</span></td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{ENDPOINTS[a.app_type] || '/v1/chat-messages'}</td>
                    <td className="px-4 py-3">
                      {a.enabled ? (
                        <span className="px-2 py-0.5 bg-green-900/30 text-green-400 text-xs rounded">是</span>
                      ) : (
                        <span className="px-2 py-0.5 bg-gray-700 text-gray-400 text-xs rounded">否</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <button onClick={() => openTest(a)} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs rounded-lg transition-colors mr-1">测试</button>
                      <button onClick={() => openEdit(a)} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs rounded-lg transition-colors mr-1">编辑</button>
                      <button onClick={() => deleteApp(a.type, a.name)} className="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white text-xs rounded-lg transition-colors">删除</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {modal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#1e293b] rounded-xl border border-gray-700 w-full max-w-lg mx-4 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h2 className="text-lg font-semibold text-white">{modal.mode === 'create' ? '新增 AI 应用' : '编辑 AI 应用'}</h2>
              <button onClick={() => setModal(null)} className="text-gray-400 hover:text-white"><i className="fas fa-times"></i></button>
            </div>
            <div className="p-6 overflow-auto space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">类型标识 *</label>
                  <input value={modal.type} onChange={e => updateModal(p => ({ ...p, type: e.target.value }))} placeholder="sentiment" className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" />
                  <p className="text-xs text-gray-500 mt-1">唯一标识，脚本通过此标识接入</p>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">显示名称 *</label>
                  <input value={modal.name} onChange={e => updateModal(p => ({ ...p, name: e.target.value }))} placeholder="情感分析" className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" />
                </div>
                <div className="col-span-2">
                  <label className="block text-xs text-gray-400 mb-1">API Key</label>
                  <input value={modal.api_key} onChange={e => updateModal(p => ({ ...p, api_key: e.target.value }))} placeholder="sk-xxxxxxxx" className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm font-mono" />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">App 类型</label>
                  <select value={modal.app_type} onChange={e => updateModal(p => ({ ...p, app_type: e.target.value }))} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm">
                    {APP_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </div>
                <div className="flex items-center gap-3">
                  <input id="appEnabled" type="checkbox" checked={modal.enabled} onChange={e => updateModal(p => ({ ...p, enabled: e.target.checked }))} className="w-4 h-4 rounded border-gray-600" />
                  <label htmlFor="appEnabled" className="text-sm text-gray-300">启用</label>
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-gray-300">Inputs 校验规则</label>
                  <div className="flex gap-2">
                    <button onClick={fetchParameters} className="text-xs px-2 py-1 bg-green-700 hover:bg-green-600 text-white rounded">从 Dify 获取</button>
                    <button onClick={() => addSchemaRow()} className="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 text-white rounded">+ 添加字段</button>
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="grid grid-cols-12 gap-2 text-xs text-gray-500 px-2">
                    <div className="col-span-3">字段名</div>
                    <div className="col-span-2">类型</div>
                    <div className="col-span-1 text-center">必填</div>
                    <div className="col-span-5">描述</div>
                    <div className="col-span-1"></div>
                  </div>
                  {modal.input_schema.map(row => (
                    <div key={row.id} className="grid grid-cols-12 gap-2 items-center bg-[#0f172a] rounded-lg p-2">
                      <div className="col-span-3">
                        <input value={row.name} onChange={e => updateSchemaRow(row.id, 'name', e.target.value)} placeholder="comments" className="w-full px-2 py-1 bg-[#1e293b] border border-gray-600 rounded text-white text-xs" />
                      </div>
                      <div className="col-span-2">
                        <select value={row.type} onChange={e => updateSchemaRow(row.id, 'type', e.target.value)} className="w-full px-2 py-1 bg-[#1e293b] border border-gray-600 rounded text-white text-xs">
                          {SCHEMA_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                        </select>
                      </div>
                      <div className="col-span-1 flex justify-center">
                        <input type="checkbox" checked={row.required} onChange={e => updateSchemaRow(row.id, 'required', e.target.checked)} className="w-4 h-4" />
                      </div>
                      <div className="col-span-5">
                        <input value={row.description} onChange={e => updateSchemaRow(row.id, 'description', e.target.value)} placeholder="字段描述" className="w-full px-2 py-1 bg-[#1e293b] border border-gray-600 rounded text-white text-xs" />
                      </div>
                      <div className="col-span-1 flex justify-end">
                        <button onClick={() => removeSchemaRow(row.id)} className="text-xs text-red-400 hover:text-red-300">×</button>
                      </div>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-gray-500 mt-1">声明后，调用 /api/ai/invoke 时会校验 payload.inputs 中的字段。点击“从 Dify 获取”可自动拉取应用配置。</p>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button onClick={() => setModal(null)} className="px-4 py-2 text-gray-400 hover:text-white text-sm">取消</button>
                <button onClick={saveApp} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium">保存</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {test && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#1e293b] rounded-xl border border-gray-700 w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h2 className="text-lg font-semibold text-white">测试 AI 应用（透传）</h2>
              <button onClick={() => { setTest(null); setTestResponse(null); }} className="text-gray-400 hover:text-white"><i className="fas fa-times"></i></button>
            </div>
            <div className="p-6 overflow-auto space-y-4">
              <div className="bg-[#0f172a] rounded-lg p-4">
                <div className="text-sm text-white font-medium mb-1">{test.app.name}</div>
                <div className="text-xs text-gray-500">{test.app.type} | {test.app.app_type}</div>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Dify Payload（JSON）</label>
                <p className="text-xs text-gray-500 mb-2">text/chat/agent/chatflow: 需包含 query / inputs / user；workflow: 需包含 inputs / user（禁止 query）</p>
                <textarea value={test.payload} onChange={e => setTest(t => ({ ...t, payload: e.target.value }))} rows={8} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white font-mono text-xs"></textarea>
              </div>
              <div className="flex gap-3 pt-2">
                <button onClick={submitTest} disabled={testResponse?.status === 'loading'} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800/50 text-white rounded-lg text-sm font-medium">
                  {testResponse?.status === 'loading' ? <i className="fas fa-circle-notch fa-spin mr-2"></i> : null}
                  发送
                </button>
                <button onClick={() => { setTest(null); setTestResponse(null); }} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm">关闭</button>
              </div>
              {testResponse && testResponse.status !== 'loading' && (
                <div className="mt-4">
                  <h4 className="text-sm font-medium text-gray-300 mb-2">响应结果</h4>
                  <pre className={`bg-[#0f172a] rounded-lg p-4 text-xs font-mono overflow-x-auto max-h-64 whitespace-pre ${testResponse.status === 'error' ? 'text-red-400' : 'text-gray-300'}`}>
                    {testResponse.body}
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
