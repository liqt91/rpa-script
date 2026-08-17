import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../api';

const statCards = [
  { key: 'workflow_count', label: '流程数', icon: 'fa-project-diagram', color: 'text-accent', bg: 'bg-accent/15' },
  { key: 'run_count', label: '运行次数', icon: 'fa-database', color: 'text-cyan-400', bg: 'bg-cyan-600/10' },
];

const quickLinks = [
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
        <p className="text-muted text-sm mt-1">概览与快捷入口</p>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-danger/25 border border-danger rounded-lg text-danger text-sm">
          <i className="fas fa-exclamation-circle mr-2"></i>
          {error}
          <button onClick={() => setError(null)} className="ml-2 text-danger hover:text-red-200">×</button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <i className="fas fa-circle-notch fa-spin text-accent text-2xl"></i>
          <span className="ml-3 text-faint">加载中...</span>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 mb-6">
            {statCards.map(card => (
              <div key={card.key} className={`${card.bg} border border-gray-700 rounded-xl p-4`}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-faint text-sm">{card.label}</span>
                  <i className={`fas ${card.icon} ${card.color}`}></i>
                </div>
                <div className="text-2xl font-semibold text-white">{stats?.[card.key] ?? 0}</div>
              </div>
            ))}
          </div>

          <div className="bg-surface-2 rounded-xl border border-gray-700 p-5">
            <h2 className="text-white font-medium mb-4">快捷入口</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {quickLinks.map(link => (
                <Link
                  key={link.to}
                  to={link.to}
                  className="flex items-center gap-3 px-4 py-3 bg-bg hover:bg-[#252f47] border border-gray-700 rounded-lg transition-colors"
                >
                  <i className={`fas ${link.icon} text-accent w-5 text-center`}></i>
                  <span className="text-body text-sm">{link.label}</span>
                </Link>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
