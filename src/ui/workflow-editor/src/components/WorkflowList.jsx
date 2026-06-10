import { useEffect, useRef, useState } from 'react';
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
  const [browserPaths, setBrowserPaths] = useState({ chrome: null, edge: null });
  const [extStatus, setExtStatus] = useState(null);
  const [runningId, setRunningId] = useState(null);
  const runningRef = useRef(false); // 同步锁，防止 React state 异步更新导致双击穿透
  const [runResult, setRunResult] = useState(null);
  const [showInstallGuide, setShowInstallGuide] = useState(false);
  const sseRef = useRef(null);

  useEffect(() => {
    loadWorkflows();
    loadBrowserPaths();
    loadExtensionStatus();

    // 同步恢复运行状态（避免切换页面后闪烁）
    const savedId = sessionStorage.getItem('wf_running_id');
    const savedRunId = sessionStorage.getItem('wf_run_id');
    const savedResult = sessionStorage.getItem('wf_run_result');
    if (savedId) {
      setRunningId(Number(savedId));
    }
    if (savedResult) {
      try { setRunResult(JSON.parse(savedResult)); } catch {}
    }
    if (savedId && savedRunId) {
      connectRunSSE(Number(savedId), savedRunId);
    }

    return () => {
      if (sseRef.current) { sseRef.current.close(); sseRef.current = null; }
    };
  }, []);

  async function loadBrowserPaths() {
    try {
      const data = await api.getBrowserPaths();
      setBrowserPaths(data);
    } catch (e) {
      console.warn('检测浏览器路径失败:', e.message);
    }
  }

  async function loadExtensionStatus() {
    try {
      const data = await api.getExtensionStatus();
      setExtStatus(data);
    } catch (e) {
      console.warn('检测扩展状态失败:', e.message);
      setExtStatus({ online: false, count: 0, installed: [] });
    }
  }

  function connectRunSSE(wfId, runId) {
    if (sseRef.current) { sseRef.current.close(); }
    const source = new EventSource(`/api/workflows/${wfId}/run/stream?run_id=${encodeURIComponent(runId)}`);
    sseRef.current = source;

    source.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === 'done' || data.type === 'stepError') {
          const success = data.type === 'done' && data.success !== false && !data.stopped;
          const result = {
            wfId,
            success,
            completedSteps: data.completedSteps,
            totalSteps: data.totalSteps,
            error: data.error,
            stopped: data.stopped,
          };
          setRunResult(result);
          sessionStorage.setItem('wf_run_result', JSON.stringify(result));
          setRunningId(null);
          runningRef.current = false;
          sessionStorage.removeItem('wf_running_id');
          sessionStorage.removeItem('wf_run_id');
          source.close();
          sseRef.current = null;
        }
      } catch (err) {
        console.error('[WorkflowList] SSE parse error:', err);
      }
    };

    source.onerror = () => {
      source.close();
      sseRef.current = null;
      // SSE 断开，延迟查询运行记录确认最终状态
      setTimeout(() => {
        api.getWorkflowRuns(wfId)
          .then(runs => {
            const run = runs.find(r => r.runId === runId);
            if (run) {
              const result = { wfId, success: run.success, error: run.error };
              setRunResult(result);
              sessionStorage.setItem('wf_run_result', JSON.stringify(result));
            }
            setRunningId(null);
            runningRef.current = false;
            sessionStorage.removeItem('wf_running_id');
            sessionStorage.removeItem('wf_run_id');
          })
          .catch(() => {});
      }, 1000);
    };
  }

  async function handleRun(wf) {
    if (runningRef.current || runningId) return; // 同步锁 + state 双保险
    runningRef.current = true;
    const runId = `run_${Date.now()}`;
    setRunningId(wf.id);
    sessionStorage.setItem('wf_running_id', String(wf.id));
    sessionStorage.setItem('wf_run_id', runId);
    setRunResult(null);
    sessionStorage.removeItem('wf_run_result');

    // 流程列表执行：清空数据表格，每次执行都是独立任务
    localStorage.removeItem(`workflow_table_${wf.id}`);

    // 启动 SSE 监听进度，fire-and-forget 发请求
    connectRunSSE(wf.id, runId);
    api.runWorkflowExtension(wf.id, runId, null).catch(e => {
      // 切页/刷新导致 fetch 被浏览器取消，不意味着运行失败，让 SSE 判断最终状态
      const msg = e.message || '';
      if (e.name === 'AbortError' || msg.includes('Failed to fetch') || msg.includes('cancel') || msg.includes('aborted')) {
        console.warn('[WorkflowList] run request interrupted, waiting for SSE...');
        return;
      }
      console.error('[WorkflowList] run request failed:', e);
      setRunResult({ wfId: wf.id, success: false, error: e.message });
      sessionStorage.setItem('wf_run_result', JSON.stringify({ wfId: wf.id, success: false, error: e.message }));
      setRunningId(null);
      runningRef.current = false;
      sessionStorage.removeItem('wf_running_id');
      sessionStorage.removeItem('wf_run_id');
      if (sseRef.current) { sseRef.current.close(); sseRef.current = null; }
    });
  }

  async function handleStop(wf) {
    const runId = sessionStorage.getItem('wf_run_id');
    if (!runId) return;
    try {
      await api.stopRun(wf.id, runId);
    } catch (e) {
      console.error('[WorkflowList] stop failed:', e);
    } finally {
      runningRef.current = false;
      setRunningId(null);
      sessionStorage.removeItem('wf_running_id');
      sessionStorage.removeItem('wf_run_id');
      if (sseRef.current) { sseRef.current.close(); sseRef.current = null; }
    }
  }

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
      // 清理 localStorage 中该流程的缓存节点，避免 ID 重用后显示旧数据
      localStorage.removeItem(`workflow_editor_nodes_${id}`);
      localStorage.removeItem(`workflow_table_${id}`);
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

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">流程列表</h1>
          <p className="text-gray-500 text-sm mt-1">管理工作流，配置执行浏览器，手动触发运行</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium flex items-center gap-2 transition-colors"
        >
          <i className="fas fa-plus"></i>
          新建工作流
        </button>
      </div>
        {error && (
          <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
            <i className="fas fa-exclamation-circle mr-2"></i>
            {error}
            <button onClick={() => setError(null)} className="ml-2 text-red-400 hover:text-red-200">×</button>
          </div>
        )}

        {/* 浏览器与扩展状态检测 */}
        <div className="mb-4 p-3 bg-[#1e293b] border border-gray-700 rounded-lg">
          <div className="flex items-center gap-4 text-sm">
            <span className="text-gray-400 font-medium"><i className="fas fa-browser mr-1"></i>浏览器检测:</span>
            <span className="flex items-center gap-1.5">
              <i className="fab fa-chrome text-gray-400"></i>
              <span className={browserPaths.chrome ? 'text-green-400' : 'text-red-400'}>
                {browserPaths.chrome ? 'Chrome 已找到' : 'Chrome 未找到'}
              </span>
            </span>
            <span className="flex items-center gap-1.5">
              <i className="fab fa-edge text-gray-400"></i>
              <span className={browserPaths.edge ? 'text-green-400' : 'text-red-400'}>
                {browserPaths.edge ? 'Edge 已找到' : 'Edge 未找到'}
              </span>
            </span>
            <button
              onClick={() => { loadBrowserPaths(); loadExtensionStatus(); }}
              className="ml-auto text-xs text-blue-400 hover:text-blue-300"
              title="重新检测"
            >
              <i className="fas fa-sync-alt"></i> 重新检测
            </button>
          </div>
          {(browserPaths.chrome || browserPaths.edge) && (
            <div className="mt-2 text-xs text-gray-500 font-mono space-y-0.5">
              {browserPaths.chrome && <div>Chrome: {browserPaths.chrome}</div>}
              {browserPaths.edge && <div>Edge: {browserPaths.edge}</div>}
            </div>
          )}
          {/* 扩展状态 */}
          <div className="mt-2 flex items-center gap-4 text-sm border-t border-gray-700/50 pt-2">
            <span className="text-gray-400 font-medium"><i className="fas fa-puzzle-piece mr-1"></i>扩展状态:</span>
            {(() => {
              if (!extStatus) return <span className="text-gray-500">检测中...</span>;
              const installed = extStatus.installed || [];
              const chromeInstalled = installed.some(i => i.browser === 'chrome');
              const edgeInstalled = installed.some(i => i.browser === 'edge');
              const chromeOnline = extStatus.browsers?.some(b => b.browser === 'chrome');
              const edgeOnline = extStatus.browsers?.some(b => b.browser === 'edge');
              return (
                <>
                  <span className="flex items-center gap-1.5">
                    <i className="fab fa-chrome text-gray-400"></i>
                    {chromeOnline ? (
                      <span className="text-green-400">扩展已安装 · 在线</span>
                    ) : chromeInstalled ? (
                      <span className="text-yellow-400">扩展已安装 · 未连接</span>
                    ) : (
                      <span className="text-red-400">扩展未安装</span>
                    )}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <i className="fab fa-edge text-gray-400"></i>
                    {edgeOnline ? (
                      <span className="text-green-400">扩展已安装 · 在线</span>
                    ) : edgeInstalled ? (
                      <span className="text-yellow-400">扩展已安装 · 未连接</span>
                    ) : (
                      <span className="text-red-400">扩展未安装</span>
                    )}
                  </span>
                </>
              );
            })()}
            <button
              onClick={() => setShowInstallGuide(v => !v)}
              className="ml-auto text-xs text-blue-400 hover:text-blue-300"
            >
              <i className={`fas ${showInstallGuide ? 'fa-chevron-up' : 'fa-chevron-down'} mr-1`}></i>
              {showInstallGuide ? '收起说明' : '安装说明'}
            </button>
          </div>
          {showInstallGuide && (
            <div className="mt-2 text-xs text-gray-400 bg-[#0f172a] border border-gray-700 rounded p-3 space-y-2">
              <p className="font-medium text-gray-300">浏览器扩展安装步骤：</p>
              <ol className="list-decimal list-inside space-y-1">
                <li>打开 Chrome 或 Edge 浏览器，进入扩展管理页面（地址栏输入 <code className="text-blue-300">chrome://extensions</code> 或 <code className="text-blue-300">edge://extensions</code>）</li>
                <li>开启右上角「开发者模式」</li>
                <li>点击「加载已解压的扩展程序」</li>
                <li>选择本项目 <code className="text-yellow-300">extension/</code> 文件夹（或 <code className="text-yellow-300">dist/desktop/extension/</code>）</li>
                <li>安装完成后刷新本页面，扩展状态将显示为「已安装 · 在线」</li>
              </ol>
              <p className="text-gray-500">提示：运行工作流前需确保目标浏览器对应的扩展已安装并在线。</p>
            </div>
          )}
        </div>

        {/* 执行结果 Toast */}
        {runResult && (
          <div className={`mb-4 p-3 rounded-lg text-sm ${
            runResult.success
              ? 'bg-green-900/30 border border-green-700 text-green-300'
              : runResult.stopped
                ? 'bg-yellow-900/30 border border-yellow-700 text-yellow-300'
                : 'bg-red-900/30 border border-red-700 text-red-300'
          }`}>
            <div className="flex items-center justify-between">
              <span>
                <i className={`fas ${runResult.success ? 'fa-check-circle' : runResult.stopped ? 'fa-pause-circle' : 'fa-times-circle'} mr-2`}></i>
                {runResult.success ? '执行成功' : runResult.stopped ? '已停止' : `执行失败: ${runResult.error || '未知错误'}`}
              </span>
              <button onClick={() => setRunResult(null)} className="text-gray-400 hover:text-white">×</button>
            </div>
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
                    <td className="px-4 py-3 text-gray-400">{formatDate(wf.created_at)}</td>
                    <td className="px-4 py-3 text-gray-400">{formatDate(wf.updated_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {runningId === wf.id ? (
                          <button
                            onClick={() => handleStop(wf)}
                            className="px-3 py-1.5 bg-red-600/20 hover:bg-red-600/30 text-red-300 rounded text-xs transition-colors"
                            title="停止"
                          >
                            <i className="fas fa-stop mr-1"></i>停止
                          </button>
                        ) : (
                          <button
                            onClick={() => handleRun(wf)}
                            className="px-3 py-1.5 bg-green-600/20 hover:bg-green-600/30 text-green-300 rounded text-xs transition-colors"
                            title="执行"
                          >
                            <i className="fas fa-play mr-1"></i>执行
                          </button>
                        )}
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
