import { useEffect, useState } from 'react';
import { api } from '../api';

export default function RunLogs() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [detailRun, setDetailRun] = useState(null);  // { runId, workflowId, type: 'log'|'table' }
  const [detailData, setDetailData] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    loadRuns();
  }, []);

  async function loadRuns() {
    setLoading(true);
    try {
      const data = await api.listAllRuns();
      console.log('[RunLogs] API response:', data);
      setRuns(Array.isArray(data) ? data : []);
      setError(null);
    } catch (e) {
      console.error('[RunLogs] API error:', e.message);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function viewLog(run) {
    if (!run.workflowId || !run.runId) return;
    setDetailRun({ runId: run.runId, workflowId: run.workflowId, type: 'log' });
    setDetailLoading(true);
    try {
      const data = await api.getRunLog(run.workflowId, run.runId);
      console.log('[RunLogs] getRunLog response:', data);
      setDetailData(data);
    } catch (e) {
      setDetailData({ error: e.message });
    } finally {
      setDetailLoading(false);
    }
  }

  async function viewTable(run) {
    if (!run.workflowId || !run.runId) return;
    setDetailRun({ runId: run.runId, workflowId: run.workflowId, type: 'table' });
    setDetailLoading(true);
    try {
      const data = await api.getRunTable(run.workflowId, run.runId);
      setDetailData(data);
    } catch (e) {
      setDetailData({ error: e.message });
    } finally {
      setDetailLoading(false);
    }
  }

  async function openFolder(run) {
    if (!run.workflowId || !run.runId) return;
    try {
      await api.openRunFolder(run.workflowId, run.runId);
    } catch (e) {
      setError(e.message);
    }
  }

  function formatDate(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
  }

  function formatDuration(start, end) {
    if (!start || !end) return '-';
    const ms = new Date(end) - new Date(start);
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${Math.floor(ms / 1000)}s`;
    return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
  }

  async function exportRunsToCSV() {
    if (runs.length === 0) return;
    const headers = ['流程名称', '开始时间', '触发方式', '耗时', '运行结果', '错误信息'];
    const rows = runs.map(r => [
      r.workflowName || `流程 #${r.workflowId}`,
      formatDate(r.startedAt),
      r.triggerType === 'scheduled' ? '计划执行' : '手动运行',
      formatDuration(r.startedAt, r.completedAt),
      r.success === true ? '成功' : r.success === false ? '失败' : '未知',
      r.error || ''
    ]);
    const csv = [headers, ...rows].map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n');
    await downloadFile(csv, `运行日志_${new Date().toISOString().slice(0, 10)}.csv`, 'text/csv');
  }

  async function exportTableToCSV() {
    const rows = detailData?.rows || [];
    const cols = detailData?.columns || [];
    const inferredCols = cols.length > 0 ? cols
      : rows.length > 0 ? [...new Set(rows.flatMap(Object.keys))].map(k => ({ name: k }))
      : [];
    if (inferredCols.length === 0) return;
    const headers = inferredCols.map(c => c.name);
    const csvRows = rows.map(r => inferredCols.map(c => r[c.name] ?? ''));
    const csv = [headers, ...csvRows].map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n');
    await downloadFile(csv, `数据表格_${detailRun.runId}_${new Date().toISOString().slice(0, 10)}.csv`, 'text/csv');
  }

  async function downloadFile(content, filename, type) {
    if (window.pywebview?.api?.saveFileDialog) {
      try {
        const result = await window.pywebview.api.saveFileDialog(content, filename);
        if (!result.success) {
          if (!result.cancelled) {
            alert('保存失败: ' + (result.error || '未知错误'));
          }
        }
        return;
      } catch (e) {
        console.error('[RunLogs] saveFileDialog failed:', e);
      }
    }
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">运行日志</h1>
          <p className="text-gray-500 text-sm mt-1">查看所有工作流的执行历史和结果</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={exportRunsToCSV}
            disabled={runs.length === 0}
            className="px-3 py-1.5 bg-green-700/60 hover:bg-green-700 disabled:bg-gray-800 disabled:text-gray-500 text-white rounded text-sm flex items-center gap-2 transition-colors"
          >
            <i className="fas fa-file-export"></i>
            导出
          </button>
          <button
            onClick={loadRuns}
            className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded text-sm flex items-center gap-2 transition-colors"
          >
            <i className="fas fa-sync-alt"></i>
            刷新
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
          <i className="fas fa-exclamation-circle mr-2"></i>{error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <i className="fas fa-circle-notch fa-spin text-blue-400 text-2xl"></i>
          <span className="ml-3 text-gray-400">加载中...</span>
        </div>
      ) : runs.length === 0 ? (
        <div className="bg-[#1e293b] rounded-xl border border-gray-700 p-12 text-center">
          <i className="fas fa-file-alt text-gray-600 text-4xl mb-4"></i>
          <p className="text-gray-500">暂无运行记录</p>
        </div>
      ) : (
        <div className="bg-[#1e293b] rounded-xl border border-gray-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 bg-[#252f47]">
                <th className="text-left px-4 py-3 font-medium text-gray-400">流程</th>
                <th className="text-left px-4 py-3 font-medium text-gray-400">开始时间</th>
                <th className="text-left px-4 py-3 font-medium text-gray-400">触发方式</th>
                <th className="text-left px-4 py-3 font-medium text-gray-400">耗时</th>
                <th className="text-left px-4 py-3 font-medium text-gray-400">运行结果</th>
                <th className="text-right px-4 py-3 font-medium text-gray-400">操作</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id} className="border-b border-gray-700/50 hover:bg-[#252f47] transition-colors">
                  <td className="px-4 py-3">
                    <div className="font-medium text-white">{run.workflowName || `流程 #${run.workflowId}`}</div>
                  </td>
                  <td className="px-4 py-3 text-gray-400">{formatDate(run.startedAt)}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      run.triggerType === 'scheduled'
                        ? 'bg-purple-900/40 text-purple-300'
                        : run.triggerType === 'api'
                          ? 'bg-green-900/40 text-green-300'
                          : 'bg-blue-900/40 text-blue-300'
                    }`}>
                      {run.triggerType === 'scheduled' ? '计划执行' : run.triggerType === 'api' ? 'API 调用' : '手动运行'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-400">{formatDuration(run.startedAt, run.completedAt)}</td>
                  <td className="px-4 py-3">
                    <div>
                      {run.success === true ? (
                        <span className="flex items-center gap-1.5 text-green-400">
                          <i className="fas fa-check-circle"></i>
                          运行成功
                        </span>
                      ) : run.success === false ? (
                        <span className="flex items-center gap-1.5 text-red-400">
                          <i className="fas fa-times-circle"></i>
                          运行失败
                          {run.error && <span className="text-red-500 text-xs ml-1">({run.error})</span>}
                        </span>
                      ) : (
                        <span className="text-gray-500">未知</span>
                      )}
                      {run.outputs && Object.keys(run.outputs).length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {Object.entries(run.outputs).map(([key, value]) => (
                            <span key={key} className="px-1.5 py-0.5 bg-gray-800 rounded text-[10px] text-gray-300 font-mono">
                              {key}: {typeof value === 'object' ? JSON.stringify(value).slice(0, 40) : String(value ?? '-')}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => viewLog(run)}
                        className="px-3 py-1.5 bg-gray-700/50 hover:bg-gray-700 text-gray-300 rounded text-xs transition-colors"
                        title="查看日志"
                      >
                        <i className="fas fa-file-alt mr-1"></i>日志
                      </button>
                      <button
                        onClick={() => viewTable(run)}
                        className="px-3 py-1.5 bg-gray-700/50 hover:bg-gray-700 text-gray-300 rounded text-xs transition-colors"
                        title="查看数据表格"
                      >
                        <i className="fas fa-table mr-1"></i>表格
                      </button>
                      <button
                        onClick={() => openFolder(run)}
                        className="px-3 py-1.5 bg-gray-700/50 hover:bg-gray-700 text-gray-300 rounded text-xs transition-colors"
                        title="打开日志文件夹"
                      >
                        <i className="fas fa-folder-open mr-1"></i>文件夹
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 详情弹窗 */}
      {detailRun && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#1e293b] rounded-xl border border-gray-700 w-full max-w-3xl mx-4 max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-lg font-semibold text-white">
                {detailRun.type === 'log' ? '运行日志' : '数据表格'} — {detailRun.runId}
              </h3>
              <button
                onClick={() => { setDetailRun(null); setDetailData(null); }}
                className="text-gray-400 hover:text-white"
              >
                <i className="fas fa-times"></i>
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {detailLoading ? (
                <div className="flex items-center justify-center py-12">
                  <i className="fas fa-circle-notch fa-spin text-blue-400"></i>
                </div>
              ) : detailData?.error ? (
                <div className="text-red-400 text-sm">{detailData.error}</div>
              ) : detailRun.type === 'log' ? (
                <div className="space-y-1 font-mono text-xs">
                  {(detailData?.events || []).map((evt, i) => (
                    <div key={i} className={`px-2 py-1 rounded ${
                      evt.type === 'stepError' ? 'bg-red-900/30 text-red-300' :
                      evt.type === 'done' ? 'bg-green-900/30 text-green-300' :
                      'text-gray-300'
                    }`}>
                      <span className="text-gray-500 mr-2">[{evt.type}]</span>
                      {evt.compound && <span className="text-blue-400 mr-2">{evt.cmdType || 'compound'}</span>}
                      {evt.endOrder && <span className="text-blue-300 mr-2">#{evt.endOrder} 第#{evt.order}步</span>}
                      {evt.error && <span className="text-red-400">{evt.error}</span>}
                      {evt.result?.log !== undefined ? (
                        <span className="text-gray-300">{evt.result.log}</span>
                      ) : evt.result && typeof evt.result === 'object' ? (
                        <span className="text-gray-400">{JSON.stringify(evt.result).slice(0, 200)}</span>
                      ) : evt.result ? (
                        <span className="text-gray-400">{String(evt.result).slice(0, 200)}</span>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : (
                <div>
                  {(() => {
                    const rows = detailData?.rows || [];
                    const cols = detailData?.columns || [];
                    const inferredCols = cols.length > 0 ? cols
                      : rows.length > 0 ? [...new Set(rows.flatMap(Object.keys))].map(k => ({ name: k }))
                      : [];
                    if (inferredCols.length === 0) {
                      return <div className="text-gray-500 text-center py-8">无数据</div>;
                    }
                    return (
                      <>
                        <div className="mb-2 flex justify-end">
                          <button
                            onClick={exportTableToCSV}
                            className="px-3 py-1.5 bg-green-700/60 hover:bg-green-700 text-white rounded text-xs flex items-center gap-1.5 transition-colors"
                          >
                            <i className="fas fa-file-export"></i>
                            导出表格
                          </button>
                        </div>
                        <table className="w-full border-collapse text-xs">
                          <thead>
                            <tr>
                              {inferredCols.map((col, ci) => (
                                <th key={ci} className="border border-gray-600 bg-gray-800 px-2 py-1 text-gray-300">{col.name}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {rows.map((row, ri) => (
                              <tr key={ri}>
                                {inferredCols.map((col, ci) => (
                                  <td key={ci} className="border border-gray-600 px-2 py-1 text-gray-300">{row[col.name] ?? ''}</td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </>
                    );
                  })()}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
