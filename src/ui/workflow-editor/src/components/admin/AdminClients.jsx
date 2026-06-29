import { useEffect, useState } from 'react';
import { api } from '../../api';

export default function AdminClients() {
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadClients();
  }, []);

  async function loadClients() {
    setLoading(true);
    try {
      const data = await api.listClients();
      setClients(data.clients || []);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
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
          <h1 className="text-xl font-semibold text-white">客户端</h1>
          <p className="text-gray-500 text-sm mt-1">查看已注册客户端及其在线状态</p>
        </div>
        <button
          onClick={loadClients}
          className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm transition-colors"
        >
          <i className="fas fa-sync-alt mr-2"></i>刷新
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
                <th className="text-left px-4 py-3 font-medium text-gray-400">ID</th>
                <th className="text-left px-4 py-3 font-medium text-gray-400">主机名</th>
                <th className="text-left px-4 py-3 font-medium text-gray-400">IP</th>
                <th className="text-left px-4 py-3 font-medium text-gray-400">系统</th>
                <th className="text-left px-4 py-3 font-medium text-gray-400">版本</th>
                <th className="text-left px-4 py-3 font-medium text-gray-400">状态</th>
                <th className="text-left px-4 py-3 font-medium text-gray-400">最后心跳</th>
              </tr>
            </thead>
            <tbody>
              {clients.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-500">暂无客户端</td>
                </tr>
              )}
              {clients.map(c => (
                <tr key={c.id} className="border-b border-gray-700/50 hover:bg-[#252f47] transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-white">{c.id}</td>
                  <td className="px-4 py-3 text-gray-300">{c.hostname || '-'}</td>
                  <td className="px-4 py-3 text-gray-400">{c.ip || '-'}</td>
                  <td className="px-4 py-3 text-gray-400">{c.os || '-'}</td>
                  <td className="px-4 py-3 text-gray-400">{c.version || '-'}</td>
                  <td className={`px-4 py-3 ${c.online ? 'text-green-400' : 'text-red-400'}`}>
                    {c.online ? '在线' : '离线'}
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{formatTime(c.last_heartbeat)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
