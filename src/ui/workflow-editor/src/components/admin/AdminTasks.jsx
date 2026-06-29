import { useEffect, useState } from 'react';
import { api } from '../../api';

const statusColors = {
  pending: 'text-yellow-400',
  running: 'text-blue-400',
  done: 'text-green-400',
  failed: 'text-red-400',
};

function parseParamValue(type, value) {
  if (!value) return '';
  if (type === 'integer') return parseInt(value, 10);
  if (type === 'float') return parseFloat(value);
  if (type === 'boolean') return value === 'true' || value === '1';
  return value;
}

export default function AdminTasks() {
  const [tasks, setTasks] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [jobTypeFilter, setJobTypeFilter] = useState('');
  const [scripts, setScripts] = useState([]);

  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ job_type: '', urls: '', params: {} });
  const [selectedMeta, setSelectedMeta] = useState(null);

  useEffect(() => {
    loadScripts();
    loadTasks(1);
  }, []);

  async function loadScripts() {
    try {
      const data = await api.listScripts();
      setScripts(data.scripts || []);
    } catch (e) {
      console.warn('加载脚本类型失败:', e.message);
    }
  }

  async function loadTasks(page) {
    setLoading(true);
    try {
      const params = { page: String(page), per_page: '20' };
      if (statusFilter) params.status = statusFilter;
      if (jobTypeFilter) params.job_type = jobTypeFilter;
      const data = await api.listTasks(params);
      setTasks(data.items || []);
      setPagination({ page: data.page, pages: data.pages, total: data.total });
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function handleJobTypeChange(jobType) {
    const meta = scripts.find(s => s.name === jobType);
    setSelectedMeta(meta || null);
    setForm(f => ({ ...f, job_type: jobType, params: {} }));
  }

  function handleParamChange(key, type, value) {
    setForm(f => ({
      ...f,
      params: { ...f.params, [key]: parseParamValue(type, value) },
    }));
  }

  async function handleCreate(e) {
    e.preventDefault();
    if (!form.job_type || !form.urls.trim()) return;
    setCreating(true);
    try {
      const urls = form.urls.split('\n').map(s => s.trim()).filter(Boolean);
      const payload = { job_type: form.job_type, urls };
      const params = {};
      Object.entries(form.params).forEach(([k, v]) => {
        if (v !== '' && v !== null && v !== undefined) params[k] = v;
      });
      if (Object.keys(params).length) payload.params = params;
      await api.createTask(payload);
      setShowCreate(false);
      setForm({ job_type: '', urls: '', params: {} });
      setSelectedMeta(null);
      loadTasks(1);
    } catch (e) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  }

  function formatTime(iso) {
    if (!iso) return '-';
    return iso.replace('T', ' ').substring(0, 19);
  }

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">任务管理</h1>
          <p className="text-gray-500 text-sm mt-1">创建、查看和筛选任务</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium flex items-center gap-2 transition-colors"
        >
          <i className="fas fa-plus"></i>
          创建任务
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
          <i className="fas fa-exclamation-circle mr-2"></i>
          {error}
          <button onClick={() => setError(null)} className="ml-2 text-red-400 hover:text-red-200">×</button>
        </div>
      )}

      <div className="mb-4 flex gap-3 items-center flex-wrap">
        <select
          value={statusFilter}
          onChange={e => { setStatusFilter(e.target.value); loadTasks(1); }}
          className="px-3 py-2 bg-[#1e293b] border border-gray-700 rounded-lg text-sm text-gray-300"
        >
          <option value="">全部状态</option>
          <option value="pending">待执行</option>
          <option value="running">进行中</option>
          <option value="done">已完成</option>
          <option value="failed">失败</option>
        </select>
        <select
          value={jobTypeFilter}
          onChange={e => { setJobTypeFilter(e.target.value); loadTasks(1); }}
          className="px-3 py-2 bg-[#1e293b] border border-gray-700 rounded-lg text-sm text-gray-300"
        >
          <option value="">全部脚本</option>
          {scripts.map(s => (
            <option key={s.name} value={s.name}>{s.name}</option>
          ))}
        </select>
        <button
          onClick={() => loadTasks(pagination.page)}
          className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm transition-colors"
        >
          <i className="fas fa-sync-alt mr-2"></i>刷新
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <i className="fas fa-circle-notch fa-spin text-blue-400 text-2xl"></i>
          <span className="ml-3 text-gray-400">加载中...</span>
        </div>
      ) : (
        <>
          <div className="bg-[#1e293b] rounded-xl border border-gray-700 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 bg-[#252f47]">
                  <th className="text-left px-4 py-3 font-medium text-gray-400">ID</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-400">脚本</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-400">URL</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-400">状态</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-400">客户端</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-400">创建时间</th>
                </tr>
              </thead>
              <tbody>
                {tasks.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-500">暂无任务</td>
                  </tr>
                )}
                {tasks.map(t => (
                  <tr key={t.id} className="border-b border-gray-700/50 hover:bg-[#252f47] transition-colors">
                    <td className="px-4 py-3 text-white">#{t.id}</td>
                    <td className="px-4 py-3 text-gray-300">{t.job_type}</td>
                    <td className="px-4 py-3 text-gray-400 max-w-xs truncate" title={t.url}>{t.url}</td>
                    <td className={`px-4 py-3 ${statusColors[t.status] || 'text-gray-400'}`}>{t.status}</td>
                    <td className="px-4 py-3 text-gray-400">{t.client_id || '-'}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{formatTime(t.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex items-center justify-between">
            <span className="text-gray-400 text-sm">共 {pagination.total} 条，第 {pagination.page}/{pagination.pages} 页</span>
            <div className="flex gap-2">
              <button
                onClick={() => loadTasks(pagination.page - 1)}
                disabled={pagination.page <= 1}
                className="px-3 py-1.5 bg-[#1e293b] border border-gray-700 rounded text-sm text-gray-300 disabled:opacity-50"
              >
                上一页
              </button>
              <button
                onClick={() => loadTasks(pagination.page + 1)}
                disabled={pagination.page >= pagination.pages}
                className="px-3 py-1.5 bg-[#1e293b] border border-gray-700 rounded text-sm text-gray-300 disabled:opacity-50"
              >
                下一页
              </button>
            </div>
          </div>
        </>
      )}

      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#1e293b] rounded-xl border border-gray-700 w-full max-w-lg mx-4">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h2 className="text-lg font-semibold text-white">创建任务</h2>
              <button
                onClick={() => { setShowCreate(false); setSelectedMeta(null); setForm({ job_type: '', urls: '', params: {} }); }}
                className="text-gray-400 hover:text-white"
              >
                <i className="fas fa-times"></i>
              </button>
            </div>
            <form onSubmit={handleCreate} className="px-6 py-4 space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1.5">脚本类型 <span className="text-red-400">*</span></label>
                <select
                  value={form.job_type}
                  onChange={e => handleJobTypeChange(e.target.value)}
                  required
                  className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm"
                >
                  <option value="">选择脚本...</option>
                  {scripts.map(s => (
                    <option key={s.name} value={s.name}>{s.name} - {s.description}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1.5">URL（每行一个） <span className="text-red-400">*</span></label>
                <textarea
                  value={form.urls}
                  onChange={e => setForm(f => ({ ...f, urls: e.target.value }))}
                  rows={4}
                  required
                  placeholder="https://example.com/page1&#10;https://example.com/page2"
                  className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm"
                ></textarea>
              </div>
              {selectedMeta && Object.entries(selectedMeta.params || {}).map(([key, cfg]) => (
                <div key={key}>
                  <label className="block text-sm text-gray-400 mb-1.5">
                    {key}
                    {cfg.required && <span className="text-red-400">*</span>}
                    {cfg.default !== undefined && <span className="text-gray-500 text-xs ml-1">(默认: {String(cfg.default)})</span>}
                  </label>
                  <input
                    type="text"
                    placeholder={cfg.description || ''}
                    onChange={e => handleParamChange(key, cfg.type, e.target.value)}
                    className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm"
                  />
                  </div>
              ))}
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="px-4 py-2 text-gray-400 hover:text-white text-sm"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800/50 text-white rounded-lg text-sm font-medium"
                >
                  {creating ? <i className="fas fa-circle-notch fa-spin mr-2"></i> : null}
                  提交
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
