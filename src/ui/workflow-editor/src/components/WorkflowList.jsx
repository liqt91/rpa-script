import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';

export default function WorkflowList() {
  const navigate = useNavigate();
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', url: '' });
  const [deleteId, setDeleteId] = useState(null);

  useEffect(() => {
    loadWorkflows();
  }, []);

  async function loadWorkflows() {
    setLoading(true);
    try {
      const data = await api.listWorkflows();
      setWorkflows(data);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(e) {
    e.preventDefault();
    if (!form.name.trim()) return;
    setCreating(true);
    try {
      const wf = await api.createWorkflow({
        name: form.name.trim(),
        description: form.description.trim(),
        url: form.url.trim(),
      });
      setShowCreate(false);
      setForm({ name: '', description: '', url: '' });
      navigate(`/editor/${wf.id}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(id) {
    try {
      await api.deleteWorkflow(id);
      setDeleteId(null);
      loadWorkflows();
    } catch (e) {
      setError(e.message);
    }
  }

  function formatDate(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }

  const currentUser = typeof window !== 'undefined' ? window.__USER__ : null;

  return (
    <div className="min-h-screen bg-[#0f172a] text-gray-200">
      {/* Header */}
      <div className="border-b border-gray-700 bg-[#1e293b]">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <i className="fas fa-project-diagram text-blue-400 text-xl"></i>
            <h1 className="text-xl font-semibold text-white">工作流管理</h1>
          </div>
          <div className="flex items-center gap-3">
            {currentUser ? (
              <div className="flex items-center gap-2 text-sm text-gray-300">
                <i className="fas fa-user-circle text-gray-500"></i>
                <span>{currentUser.username}</span>
                <a
                  href="/admin/logout"
                  className="text-gray-500 hover:text-red-400 text-xs ml-1 transition-colors"
                  title="退出登录"
                >
                  <i className="fas fa-sign-out-alt"></i>
                </a>
              </div>
            ) : null}
            <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium flex items-center gap-2 transition-colors"
          >
            <i className="fas fa-plus"></i>
            新建工作流
          </button>
        </div>
      </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-6 py-6">
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
        ) : workflows.length === 0 ? (
          <div className="text-center py-20">
            <i className="fas fa-folder-open text-gray-600 text-5xl mb-4"></i>
            <p className="text-gray-500 text-lg">暂无工作流</p>
            <p className="text-gray-600 text-sm mt-2">点击右上角"新建工作流"开始</p>
          </div>
        ) : (
          <div className="bg-[#1e293b] rounded-xl border border-gray-700 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 bg-[#252f47]">
                  <th className="text-left px-4 py-3 font-medium text-gray-400">名称</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-400">目标页面</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-400">框架</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-400">创建时间</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-400">更新时间</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-400">操作</th>
                </tr>
              </thead>
              <tbody>
                {workflows.map((wf) => (
                  <tr
                    key={wf.id}
                    className="border-b border-gray-700/50 hover:bg-[#252f47] transition-colors"
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-white">{wf.name}</div>
                      {wf.description && (
                        <div className="text-gray-500 text-xs mt-0.5">{wf.description}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-400 max-w-xs truncate">
                      {wf.url || '-'}
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 bg-blue-900/40 text-blue-300 rounded text-xs">
                        {wf.framework || 'DrissionPage'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-400">{formatDate(wf.created_at)}</td>
                    <td className="px-4 py-3 text-gray-400">{formatDate(wf.updated_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => navigate(`/editor/${wf.id}`)}
                          className="px-3 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 rounded text-xs transition-colors"
                          title="编辑"
                        >
                          <i className="fas fa-edit mr-1"></i>编辑
                        </button>
                        <button
                          onClick={() => setDeleteId(wf.id)}
                          className="px-3 py-1.5 bg-red-600/20 hover:bg-red-600/30 text-red-300 rounded text-xs transition-colors"
                          title="删除"
                        >
                          <i className="fas fa-trash mr-1"></i>删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#1e293b] rounded-xl border border-gray-700 w-full max-w-md mx-4">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h2 className="text-lg font-semibold text-white">新建工作流</h2>
              <button
                onClick={() => { setShowCreate(false); setForm({ name: '', description: '', url: '' }); }}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <i className="fas fa-times"></i>
              </button>
            </div>
            <form onSubmit={handleCreate} className="px-6 py-4 space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1.5">名称 <span className="text-red-400">*</span></label>
                <input
                  type="text"
                  value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  placeholder="例如：小红书评论采集"
                  className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1.5">描述</label>
                <input
                  type="text"
                  value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  placeholder="简短描述这个工作流的用途"
                  className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1.5">目标页面 URL</label>
                <input
                  type="text"
                  value={form.url}
                  onChange={e => setForm({ ...form, url: e.target.value })}
                  placeholder="https://..."
                  className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
                />
              </div>
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="px-4 py-2 text-gray-400 hover:text-white text-sm transition-colors"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={creating || !form.name.trim()}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800/50 disabled:text-blue-300/50 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  {creating ? <i className="fas fa-circle-notch fa-spin mr-2"></i> : null}
                  创建并编辑
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirm */}
      {deleteId !== null && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#1e293b] rounded-xl border border-gray-700 w-full max-w-sm mx-4 px-6 py-5">
            <div className="flex items-center gap-3 mb-3">
              <i className="fas fa-exclamation-triangle text-red-400 text-lg"></i>
              <h2 className="text-lg font-semibold text-white">确认删除</h2>
            </div>
            <p className="text-gray-400 text-sm mb-5">删除后无法恢复，是否继续？</p>
            <div className="flex items-center justify-end gap-3">
              <button
                onClick={() => setDeleteId(null)}
                className="px-4 py-2 text-gray-400 hover:text-white text-sm transition-colors"
              >
                取消
              </button>
              <button
                onClick={() => handleDelete(deleteId)}
                className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm font-medium transition-colors"
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
