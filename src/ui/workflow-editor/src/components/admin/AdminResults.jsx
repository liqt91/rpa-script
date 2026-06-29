import { useEffect, useState } from 'react';
import { api } from '../../api';

export default function AdminResults() {
  const [results, setResults] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    loadResults(1);
  }, []);

  async function loadResults(page) {
    setLoading(true);
    try {
      const data = await api.listResults({ page: String(page), per_page: '20' });
      setResults(data.items || []);
      setPagination({ page: data.page, pages: data.pages, total: data.total });
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(id) {
    try {
      const data = await api.getResult(id);
      setDetail(data);
    } catch (e) {
      setError(e.message);
    }
  }

  function formatTime(iso) {
    if (!iso) return '-';
    return iso.replace('T', ' ').substring(0, 19);
  }

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-white">结果查看</h1>
        <p className="text-gray-500 text-sm mt-1">查看已上传的采集结果</p>
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
        <>
          <div className="bg-[#1e293b] rounded-xl border border-gray-700 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 bg-[#252f47]">
                  <th className="text-left px-4 py-3 font-medium text-gray-400">ID</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-400">任务ID</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-400">URL</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-400">总数</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-400">脚本</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-400">客户端</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-400">采集时间</th>
                </tr>
              </thead>
              <tbody>
                {results.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-gray-500">暂无结果</td>
                  </tr>
                )}
                {results.map(item => (
                  <tr
                    key={item.id}
                    onClick={() => loadDetail(item.id)}
                    className="border-b border-gray-700/50 hover:bg-[#252f47] transition-colors cursor-pointer"
                  >
                    <td className="px-4 py-3 text-blue-300 hover:underline">#{item.id}</td>
                    <td className="px-4 py-3 text-gray-300">{item.task_id || '-'}</td>
                    <td className="px-4 py-3 text-gray-400 max-w-xs truncate" title={item.url}>{item.url}</td>
                    <td className="px-4 py-3 text-white">{item.total}</td>
                    <td className="px-4 py-3 text-gray-400">{item.job_type || '-'}</td>
                    <td className="px-4 py-3 text-gray-400">{item.client_id || '-'}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{formatTime(item.extract_time)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex items-center justify-between">
            <span className="text-gray-400 text-sm">共 {pagination.total} 条，第 {pagination.page}/{pagination.pages} 页</span>
            <div className="flex gap-2">
              <button
                onClick={() => loadResults(pagination.page - 1)}
                disabled={pagination.page <= 1}
                className="px-3 py-1.5 bg-[#1e293b] border border-gray-700 rounded text-sm text-gray-300 disabled:opacity-50"
              >
                上一页
              </button>
              <button
                onClick={() => loadResults(pagination.page + 1)}
                disabled={pagination.page >= pagination.pages}
                className="px-3 py-1.5 bg-[#1e293b] border border-gray-700 rounded text-sm text-gray-300 disabled:opacity-50"
              >
                下一页
              </button>
            </div>
          </div>
        </>
      )}

      {detail && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#1e293b] rounded-xl border border-gray-700 w-full max-w-2xl mx-4 max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h2 className="text-lg font-semibold text-white">结果详情 #{detail.id}</h2>
              <button onClick={() => setDetail(null)} className="text-gray-400 hover:text-white">
                <i className="fas fa-times"></i>
              </button>
            </div>
            <div className="p-6 overflow-auto">
              <div className="grid grid-cols-2 gap-4 mb-4 text-sm">
                <div className="text-gray-400">任务ID: <span className="text-gray-200">{detail.task_id || '-'}</span></div>
                <div className="text-gray-400">URL: <span className="text-gray-200">{detail.url}</span></div>
                <div className="text-gray-400">总数: <span className="text-gray-200">{detail.total}</span></div>
                <div className="text-gray-400">客户端: <span className="text-gray-200">{detail.client_id || '-'}</span></div>
              </div>
              <pre className="bg-[#0f172a] border border-gray-700 rounded-lg p-4 text-xs text-gray-300 overflow-auto">
                {JSON.stringify(detail.data, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
