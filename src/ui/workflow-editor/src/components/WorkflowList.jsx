import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { useActiveRun } from '../context/ActiveRunContext';
import RunParametersDialog from './RunParametersDialog';

export default function WorkflowList() {
  const navigate = useNavigate();
  const { activeRun, isBusy, loading: activeRunLoading, notifyRunStarted, notifyRunFinished } = useActiveRun();
  // 项目模式：URL ?project=<目录>（DSH 流程 tab 内嵌时传入）→ 展示该目录的流程文件状态
  const [projectDir] = useState(() => new URLSearchParams(window.location.search).get('project') || '');
  const [projectInfo, setProjectInfo] = useState(null); // {isRpa, meta, workflowExists, workflowMeta}
  const [projectLoading, setProjectLoading] = useState(Boolean(projectDir));
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: '', description: '' });
  const [deleteId, setDeleteId] = useState(null);
  const [browserPaths, setBrowserPaths] = useState({ chrome: null, edge: null });
  const [extStatus, setExtStatus] = useState(null);
  const [runningId, setRunningId] = useState(null);
  const runningRef = useRef(false); // 同步锁，防止 React state 异步更新导致双击穿透
  const recordedRef = useRef(new Set()); // 已记录结果的 wfId:runId，防止 SSE done + onerror 兜底双触发
  const [lastResults, setLastResults] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem('wf_last_results') || '{}'); } catch { return {}; }
  });
  const [runParamsWorkflow, setRunParamsWorkflow] = useState(null);
  const [showInstallGuide, setShowInstallGuide] = useState(false);
  const sseRef = useRef(null);

  useEffect(() => {
    loadWorkflows();
    loadBrowserPaths();
    loadExtensionStatus();
    if (projectDir) loadProjectInfo();

    // 同步恢复运行状态（避免切换页面后闪烁）
    const savedId = sessionStorage.getItem('wf_running_id');
    const savedRunId = sessionStorage.getItem('wf_run_id');
    if (savedId) {
      setRunningId(Number(savedId));
    }
    if (savedId && savedRunId) {
      connectRunSSE(Number(savedId), savedRunId);
    }

    // Poll for workflows created elsewhere (e.g. backend or other clients).
    const poll = setInterval(() => loadWorkflows(true), 5000);

    return () => {
      clearInterval(poll);
      if (sseRef.current) { sseRef.current.close(); sseRef.current = null; }
    };
  }, []);

  useEffect(() => {
    if (activeRun?.workflow_id) {
      setRunningId(activeRun.workflow_id);
      sessionStorage.setItem('wf_running_id', String(activeRun.workflow_id));
      sessionStorage.setItem('wf_run_id', activeRun.run_id);
    } else if (!activeRunLoading && !runningRef.current) {
      setRunningId(null);
      sessionStorage.removeItem('wf_running_id');
      sessionStorage.removeItem('wf_run_id');
    }
  }, [activeRun, activeRunLoading]);

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

  async function handleOpenExtPage(browser) {
    try {
      const data = await api.openExtensionsPage(browser);
      if (!data.success) {
        alert('打开失败: ' + (data.error || '未知错误'));
      }
    } catch (e) {
      alert('打开失败: ' + e.message);
    }
  }

  // 记录一次运行结果：行内徽章常驻 + 侧边栏结果卡（全局，由 ActiveRunContext 展示）
  function recordResult(wfId, result) { // {success, stopped, error, runId}
    const dedupeKey = `${wfId}:${result.runId || ''}`;
    if (result.runId && recordedRef.current.has(dedupeKey)) return;
    if (result.runId) recordedRef.current.add(dedupeKey);
    const entry = { ...result, time: Date.now() };
    setLastResults(prev => {
      const next = { ...prev, [wfId]: entry };
      try { sessionStorage.setItem('wf_last_results', JSON.stringify(next)); } catch {}
      return next;
    });
    const kind = result.success ? 'success' : result.stopped ? 'stopped' : 'error';
    notifyRunFinished({ workflow_id: wfId, run_id: result.runId || null, kind, error: result.error || '' });
  }

  function goRunLogs(wfId, runId) {
    navigate(runId ? `/logs?wf=${wfId}&run=${encodeURIComponent(runId)}` : '/logs');
  }

  function relTime(ts) {
    const s = Math.floor((Date.now() - ts) / 1000);
    if (s < 60) return '刚刚';
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}分钟前`;
    const d = new Date(ts);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
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
          recordResult(wfId, { success, stopped: data.stopped, error: data.error, runId });
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
              recordResult(wfId, { success: run.success, error: run.error, runId });
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
    if (runningRef.current || runningId) return;
    if (isBusy) {
      alert('已有流程运行中，请先停止');
      return;
    }
    const params = wf.parameters;
    if (Array.isArray(params) && params.length > 0) {
      setRunParamsWorkflow(wf);
      return;
    }
    doRun(wf, null);
  }

  async function doRun(wf, parameters = null) {
    runningRef.current = true;
    const runId = `run_${Date.now()}`;
    setRunningId(wf.id);
    notifyRunStarted(wf.id, runId);
    sessionStorage.setItem('wf_running_id', String(wf.id));
    sessionStorage.setItem('wf_run_id', runId);

    // 流程列表执行：清空数据表格，每次执行都是独立任务
    localStorage.removeItem(`workflow_table_${wf.id}`);

    // 启动 SSE 监听进度，fire-and-forget 发请求
    connectRunSSE(wf.id, runId);
    api.runWorkflowExtension(wf.id, runId, null, parameters).catch(e => {
      // 切页/刷新导致 fetch 被浏览器取消，不意味着运行失败，让 SSE 判断最终状态
      const msg = e.message || '';
      if (e.name === 'AbortError' || msg.includes('Failed to fetch') || msg.includes('cancel') || msg.includes('aborted')) {
        console.warn('[WorkflowList] run request interrupted, waiting for SSE...');
        return;
      }
      console.error('[WorkflowList] run request failed:', e);
      recordResult(wf.id, { success: false, error: e.message, runId });
      setRunningId(null);
      runningRef.current = false;
      sessionStorage.removeItem('wf_running_id');
      sessionStorage.removeItem('wf_run_id');
      if (sseRef.current) { sseRef.current.close(); sseRef.current = null; }
    });
  }

  async function handleStop(wf) {
    const runId = sessionStorage.getItem('wf_run_id') || activeRun?.run_id;
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

  async function loadProjectInfo() {
    try {
      const meta = await api.readProjectFile(projectDir, 'rpa.json');
      const wf = await api.readProjectFile(projectDir, 'workflow.json');
      setProjectInfo({
        isRpa: Boolean(meta.isRpa),
        meta: meta.data || null,
        workflowExists: wf.exists,
        workflowMeta: wf.exists && wf.data ? {
          name: wf.data.name || '',
          nodeCount: Array.isArray(wf.data.nodes) ? wf.data.nodes.length : 0,
          elementCount: Array.isArray(wf.data.elements) ? wf.data.elements.length : 0,
          updatedAt: wf.data.updated_at || '',
        } : null,
      });
    } catch (e) {
      console.warn('读取项目信息失败:', e.message);
      setProjectInfo({ isRpa: false, meta: null, workflowExists: false, workflowMeta: null });
    } finally {
      setProjectLoading(false);
    }
  }

  async function loadWorkflows(silent = false) {
    if (!silent) setLoading(true);
    try {
      const data = await api.listWorkflows();
      setWorkflows(data);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      if (!silent) setLoading(false);
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
      });
      setShowCreate(false);
      setForm({ name: '', description: '' });
      loadWorkflows();
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
    <div className="flex-1 min-h-0 overflow-y-auto p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-body">流程列表</h1>
          <p className="text-muted text-sm mt-1">管理工作流，配置执行浏览器，手动触发运行</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 bg-accent hover:bg-accent text-white rounded-lg text-sm font-medium flex items-center gap-2 transition-colors"
        >
          <i className="fas fa-plus"></i>
          新建工作流
        </button>
      </div>

      {/* 项目模式横幅：DSH 流程 tab 内嵌（?project=<目录>）时展示该目录的流程文件状态 */}
      {projectDir && (
        <div className="mb-4 p-4 bg-surface-2 border border-border rounded-lg">
          {projectLoading ? (
            <div className="flex items-center gap-2 text-sm text-faint">
              <i className="fas fa-circle-notch fa-spin"></i> 读取项目信息...
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
              <span className="font-medium text-body">
                <i className="fas fa-folder-open text-accent mr-1.5"></i>
                {projectDir.split(/[\\/]/).filter(Boolean).pop()}
              </span>
              <span className="text-muted font-mono text-xs">{projectDir}</span>
              {projectInfo?.isRpa ? (
                <span className="text-ok text-xs"><i className="fas fa-circle text-[6px] align-middle mr-1"></i>RPA 流程工作区</span>
              ) : (
                <span className="text-warn text-xs"><i className="fas fa-exclamation-triangle mr-1"></i>缺少 rpa.json（可在对话中用 rpa_project_create 初始化）</span>
              )}
              {projectInfo?.workflowMeta ? (
                <span className="text-muted text-xs">
                  流程：{projectInfo.workflowMeta.name || '(未命名)'} · {projectInfo.workflowMeta.nodeCount} 节点 · {projectInfo.workflowMeta.elementCount} 元素
                </span>
              ) : (
                projectInfo && !projectInfo.workflowExists && (
                  <span className="text-muted text-xs">暂无 workflow.json（流程保存在此目录）</span>
                )
              )}
            </div>
          )}
        </div>
      )}
        {error && (
          <div className="mb-4 p-3 bg-danger/25 border border-danger rounded-lg text-danger text-sm">
            <i className="fas fa-exclamation-circle mr-2"></i>
            {error}
            <button onClick={() => setError(null)} className="ml-2 text-danger hover:text-red-200">×</button>
          </div>
        )}

        {/* 浏览器与扩展状态检测 */}
        <div className="mb-4 p-3 bg-surface-2 border border-border rounded-lg">
          <div className="flex items-center gap-4 text-sm">
            <span className="text-faint font-medium"><i className="fas fa-browser mr-1"></i>运行环境:</span>
            {(() => {
              const installed = extStatus ? (extStatus.installed || []) : [];
              const renderStatus = (browser, label, icon) => {
                const found = Boolean(browserPaths[browser]);
                const isInstalled = installed.some(i => i.browser === browser);
                const isOnline = extStatus?.browsers?.some(b => b.browser === browser);
                const colorCls = !found ? 'text-muted' : isOnline ? 'text-ok' : isInstalled ? 'text-warn' : 'text-danger';
                return (
                  <span key={browser} className="flex items-center gap-1.5">
                    <i className={`${icon} ${colorCls}`}></i>
                    <span className={colorCls}>{label}</span>
                    {!found ? (
                      <span className="text-muted">未安装</span>
                    ) : isOnline ? (
                      <span className="text-ok"><i className="fas fa-circle text-[6px] align-middle mr-1"></i>在线</span>
                    ) : isInstalled ? (
                      <span className="text-warn"><i className="fas fa-circle text-[6px] align-middle mr-1"></i>未连接</span>
                    ) : (
                      <>
                        <span className="text-danger">扩展未安装</span>
                        <button
                          onClick={() => handleOpenExtPage(browser)}
                          className="ml-1 px-2 py-0.5 bg-accent/70 hover:bg-blue-700 text-inverse rounded text-[10px] transition-colors"
                          title={`打开 ${label} 并加载扩展`}
                        >
                          打开浏览器
                        </button>
                      </>
                    )}
                  </span>
                );
              };
              return (
                <>
                  {renderStatus('chrome', 'Chrome', 'fab fa-chrome')}
                  {renderStatus('edge', 'Edge', 'fab fa-edge')}
                </>
              );
            })()}
            <button
              onClick={() => { loadBrowserPaths(); loadExtensionStatus(); }}
              className="ml-auto text-xs text-accent hover:text-accent-strong"
              title="重新检测"
            >
              <i className="fas fa-sync-alt"></i> 重新检测
            </button>
            <button
              onClick={() => setShowInstallGuide(v => !v)}
              className="text-xs text-accent hover:text-accent-strong"
            >
              <i className={`fas ${showInstallGuide ? 'fa-chevron-up' : 'fa-chevron-down'} mr-1`}></i>
              {showInstallGuide ? '收起说明' : '安装说明'}
            </button>
          </div>
          {(browserPaths.chrome || browserPaths.edge) && (
            <div className="mt-2 text-xs text-muted font-mono space-y-0.5">
              {browserPaths.chrome && <div>Chrome: {browserPaths.chrome}</div>}
              {browserPaths.edge && <div>Edge: {browserPaths.edge}</div>}
            </div>
          )}
          {showInstallGuide && (
            <div className="mt-2 text-xs text-faint bg-bg border border-border rounded p-3 space-y-2">
              <p className="font-medium text-muted">浏览器扩展安装步骤：</p>
              <ol className="list-decimal list-inside space-y-1">
                <li>打开 Chrome 或 Edge 浏览器，进入扩展管理页面（地址栏输入 <code className="text-accent-strong">chrome://extensions</code> 或 <code className="text-accent-strong">edge://extensions</code>）</li>
                <li>开启右上角「开发者模式」</li>
                <li>点击「加载已解压的扩展程序」</li>
                <li>选择本项目 <code className="text-warn">extension/</code> 文件夹（或 <code className="text-warn">dist/desktop/extension/</code>）</li>
                <li>安装完成后刷新本页面，扩展状态将显示为「已安装 · 在线」</li>
              </ol>
              <p className="text-muted">提示：运行工作流前需确保目标浏览器对应的扩展已安装并在线。若某浏览器显示「未安装」，请先安装对应浏览器（Chrome / Edge）。</p>
            </div>
          )}
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <i className="fas fa-circle-notch fa-spin text-accent text-2xl"></i>
            <span className="ml-3 text-faint">加载中...</span>
          </div>
        ) : workflows.length === 0 ? (
          <div className="text-center py-20">
            <i className="fas fa-folder-open text-muted text-5xl mb-4"></i>
            <p className="text-muted text-lg">暂无工作流</p>
            <p className="text-muted text-sm mt-2">点击右上角"新建工作流"开始</p>
          </div>
        ) : (
          <div className="bg-surface-2 rounded-xl border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-3">
                  <th className="text-left px-4 py-3 font-medium text-faint">名称</th>
                  <th className="text-left px-4 py-3 font-medium text-faint w-40 whitespace-nowrap">更新时间</th>
                  <th className="text-right px-4 py-3 font-medium text-faint w-60 whitespace-nowrap">操作</th>
                </tr>
              </thead>
              <tbody>
                {workflows.map((wf) => (
                  <tr
                    key={wf.id}
                    className="border-b border-border/50 hover:bg-surface-3 transition-colors"
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-body">{wf.name}</div>
                      {wf.description && (
                        <div className="text-muted text-xs mt-0.5">{wf.description}</div>
                      )}
                      {lastResults[wf.id] && (() => {
                        const r = lastResults[wf.id];
                        const cls = r.success ? 'text-ok' : r.stopped ? 'text-warn' : 'text-danger';
                        const icon = r.success ? 'fa-check-circle' : r.stopped ? 'fa-pause-circle' : 'fa-times-circle';
                        const label = r.success ? '执行成功' : r.stopped ? '已停止' : '执行失败';
                        return (
                          <button
                            onClick={() => goRunLogs(wf.id, r.runId)}
                            title="查看运行日志"
                            className={`text-[11px] mt-0.5 inline-flex items-center gap-1 hover:underline ${cls}`}
                          >
                            <i className={`fas ${icon}`}></i>{label} · {relTime(r.time)}
                          </button>
                        );
                      })()}
                    </td>
                    <td className="px-4 py-3 text-faint whitespace-nowrap">{formatDate(wf.updated_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2 whitespace-nowrap">
                        {runningId === wf.id ? (
                          <button
                            onClick={() => handleStop(wf)}
                            className="px-3 py-1.5 bg-danger/20 hover:bg-danger/30 text-danger rounded text-xs transition-colors"
                            title="停止"
                          >
                            <i className="fas fa-stop mr-1"></i>停止
                          </button>
                        ) : (
                          <button
                            onClick={() => handleRun(wf)}
                            disabled={isBusy || runningId !== null}
                            className={`px-3 py-1.5 rounded text-xs transition-colors ${
                              isBusy || runningId !== null
                                ? 'bg-gray-700/50 text-muted cursor-not-allowed'
                                : 'bg-ok/20 hover:bg-ok/30 text-ok'
                            }`}
                            title={isBusy || runningId !== null ? '已有流程运行中，请先停止' : '执行'}
                          >
                            <i className="fas fa-play mr-1"></i>执行
                          </button>
                        )}
                        <button
                          onClick={() => navigate(`/editor/${wf.id}`)}
                          disabled={isBusy || runningId !== null}
                          className={`px-3 py-1.5 rounded text-xs transition-colors ${
                            isBusy || runningId !== null
                              ? 'bg-gray-700/50 text-muted cursor-not-allowed'
                              : 'bg-accent/20 hover:bg-accent-strong/30 text-accent-strong'
                          }`}
                          title={isBusy || runningId !== null ? '流程运行中，不可编辑' : '编辑'}
                        >
                          <i className="fas fa-edit mr-1"></i>编辑
                        </button>
                        <button
                          onClick={() => setDeleteId(wf.id)}
                          className="px-3 py-1.5 bg-danger/20 hover:bg-danger/30 text-danger rounded text-xs transition-colors"
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
          <div className="bg-surface-2 rounded-xl border border-border w-full max-w-md mx-4">
            <div className="flex items-center justify-between px-6 py-4 border-b border-border">
              <h2 className="text-lg font-semibold text-body">新建工作流</h2>
              <button
                onClick={() => { setShowCreate(false); setForm({ name: '', description: '' }); }}
                className="text-faint hover:text-body transition-colors"
              >
                <i className="fas fa-times"></i>
              </button>
            </div>
            <form onSubmit={handleCreate} className="px-6 py-4 space-y-4">
              <div>
                <label className="block text-sm text-faint mb-1.5">名称 <span className="text-danger">*</span></label>
                <input
                  type="text"
                  value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  placeholder="例如：小红书评论采集"
                  className="w-full px-3 py-2 bg-bg border border-border-strong rounded-lg text-body text-sm focus:outline-none focus:border-blue-500"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm text-faint mb-1.5">描述</label>
                <input
                  type="text"
                  value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  placeholder="简短描述这个工作流的用途"
                  className="w-full px-3 py-2 bg-bg border border-border-strong rounded-lg text-body text-sm focus:outline-none focus:border-blue-500"
                />
              </div>
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="px-4 py-2 text-faint hover:text-body text-sm transition-colors"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={creating || !form.name.trim()}
                  className="px-4 py-2 bg-accent hover:bg-accent disabled:bg-blue-800/50 disabled:text-accent-strong/50 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  {creating ? <i className="fas fa-circle-notch fa-spin mr-2"></i> : null}
                  创建并编辑
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Run Parameters Dialog */}
      {runParamsWorkflow && (
        <RunParametersDialog
          parameters={runParamsWorkflow.parameters}
          onConfirm={(values) => {
            const wf = runParamsWorkflow;
            setRunParamsWorkflow(null);
            doRun(wf, values);
          }}
          onCancel={() => setRunParamsWorkflow(null)}
        />
      )}

      {/* Delete Confirm */}
      {deleteId !== null && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-surface-2 rounded-xl border border-border w-full max-w-sm mx-4 px-6 py-5">
            <div className="flex items-center gap-3 mb-3">
              <i className="fas fa-exclamation-triangle text-danger text-lg"></i>
              <h2 className="text-lg font-semibold text-body">确认删除</h2>
            </div>
            <p className="text-faint text-sm mb-5">删除后无法恢复，是否继续？</p>
            <div className="flex items-center justify-end gap-3">
              <button
                onClick={() => setDeleteId(null)}
                className="px-4 py-2 text-faint hover:text-body text-sm transition-colors"
              >
                取消
              </button>
              <button
                onClick={() => handleDelete(deleteId)}
                className="px-4 py-2 bg-danger-solid hover:bg-danger text-white rounded-lg text-sm font-medium transition-colors"
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
