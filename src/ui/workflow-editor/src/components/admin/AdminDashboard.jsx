import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../api';

const statCards = [
  { key: 'tasks_total', label: '任务总数', icon: 'fa-tasks', color: 'text-blue-400', bg: 'bg-blue-600/10' },
  { key: 'tasks_pending', label: '待执行', icon: 'fa-clock', color: 'text-yellow-400', bg: 'bg-yellow-600/10' },
  { key: 'tasks_running', label: '进行中', icon: 'fa-spinner', color: 'text-blue-300', bg: 'bg-blue-500/10' },
  { key: 'tasks_done', label: '已完成', icon: 'fa-check-circle', color: 'text-green-400', bg: 'bg-green-600/10' },
  { key: 'tasks_failed', label: '失败', icon: 'fa-times-circle', color: 'text-red-400', bg: 'bg-red-600/10' },
  { key: 'clients_total', label: '客户端总数', icon: 'fa-desktop', color: 'text-purple-400', bg: 'bg-purple-600/10' },
  { key: 'clients_online', label: '在线客户端', icon: 'fa-signal', color: 'text-green-300', bg: 'bg-green-500/10' },
  { key: 'results_total', label: '结果总数', icon: 'fa-database', color: 'text-cyan-400', bg: 'bg-cyan-600/10' },
];

const quickLinks = [
  { to: '/admin/tasks', label: '任务管理', icon: 'fa-tasks' },
  { to: '/admin/results', label: '结果查看', icon: 'fa-database' },
  { to: '/admin/clients', label: '客户端', icon: 'fa-desktop' },
  { to: '/admin/scripts', label: '脚本管理', icon: 'fa-file-code' },
  { to: '/admin/commands', label: '指令管理', icon: 'fa-terminal' },
  { to: '/admin/ai-apps', label: 'AI 应用', icon: 'fa-robot' },
  { to: '/admin/password', label: '修改密码', icon: 'fa-key' },
];

export default function AdminDashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;
    api.getAdminDashboard()
      .then(data => { if (mounted) { setStats(data); setError(null); } })
      .catch(e => { if (mounted) setError(e.message); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, []);

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-white">管理后台</h1>
        <p className="text-gray-500 text-sm mt-1">概览与快捷入口</p>
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
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            {statCards.map(card => (
              <div key={card.key} className={`${card.bg} border border-gray-700 rounded-xl p-4`}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-gray-400 text-sm">{card.label}</span>
                  <i className={`fas ${card.icon} ${card.color}`}></i>
                </div>
                <div className="text-2xl font-semibold text-white">{stats?.[card.key] ?? 0}</div>
              </div>
            ))}
          </div>

          <div className="bg-[#1e293b] rounded-xl border border-gray-700 p-5">
            <h2 className="text-white font-medium mb-4">快捷入口</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {quickLinks.map(link => (
                <Link
                  key={link.to}
                  to={link.to}
                  className="flex items-center gap-3 px-4 py-3 bg-[#0f172a] hover:bg-[#252f47] border border-gray-700 rounded-lg transition-colors"
                >
                  <i className={`fas ${link.icon} text-blue-400 w-5 text-center`}></i>
                  <span className="text-gray-200 text-sm">{link.label}</span>
                </Link>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
