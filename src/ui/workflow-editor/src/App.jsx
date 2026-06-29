import { HashRouter, Routes, Route, useParams, NavLink, useLocation } from 'react-router-dom';
import { WorkflowProvider } from './store/WorkflowContext';
import Layout from './components/Layout';
import WorkflowList from './components/WorkflowList';
import RunLogs from './components/RunLogs';
import Schedules from './components/Schedules';
import AdminDashboard from './components/admin/AdminDashboard';
import AdminTasks from './components/admin/AdminTasks';
import AdminResults from './components/admin/AdminResults';
import AdminClients from './components/admin/AdminClients';
import AdminScripts from './components/admin/AdminScripts';
import AdminAIApps from './components/admin/AdminAIApps';
import AdminPassword from './components/admin/AdminPassword';
import AdminCommands from './components/admin/AdminCommands';

function EditorPage() {
  const { id } = useParams();
  const wfId = parseInt(id, 10);
  if (isNaN(wfId)) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-900 text-white">
        <div className="text-center">
          <p className="text-gray-400 mb-4">无效的工作流 ID</p>
        </div>
      </div>
    );
  }
  return (
    <WorkflowProvider key={wfId} wfId={wfId}>
      <Layout />
    </WorkflowProvider>
  );
}

function SidebarLayout({ children }) {
  const location = useLocation();
  const hideSidebar = location.pathname.startsWith('/editor/');

  if (hideSidebar) {
    return children;
  }

  return (
    <div className="min-h-screen bg-[#0f172a] text-gray-200 flex">
      {/* 侧边栏 */}
      <div className="w-52 bg-[#1e293b] border-r border-gray-700 flex flex-col shrink-0">
        <div className="px-4 py-5 flex items-center gap-2 border-b border-gray-700">
          <i className="fas fa-project-diagram text-blue-400 text-lg"></i>
          <span className="font-semibold text-white">RPA Script</span>
        </div>
        <nav className="flex-1 py-3 space-y-1">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                isActive ? 'bg-blue-600/20 text-blue-300 border-r-2 border-blue-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
              }`
            }
          >
            <i className="fas fa-list w-4 text-center"></i>
            流程列表
          </NavLink>
          <NavLink
            to="/schedules"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                isActive ? 'bg-blue-600/20 text-blue-300 border-r-2 border-blue-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
              }`
            }
          >
            <i className="fas fa-clock w-4 text-center"></i>
            计划任务
          </NavLink>
          <NavLink
            to="/logs"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                isActive ? 'bg-blue-600/20 text-blue-300 border-r-2 border-blue-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
              }`
            }
          >
            <i className="fas fa-file-alt w-4 text-center"></i>
            运行日志
          </NavLink>
          <NavLink
            to="/admin/dashboard"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                isActive ? 'bg-blue-600/20 text-blue-300 border-r-2 border-blue-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
              }`
            }
          >
            <i className="fas fa-cog w-4 text-center"></i>
            管理后台
          </NavLink>
        </nav>
      </div>

      {/* 主内容区 */}
      <div className="flex-1 flex flex-col min-w-0">
        {children}
      </div>
    </div>
  );
}

function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<SidebarLayout><WorkflowList /></SidebarLayout>} />
        <Route path="/logs" element={<SidebarLayout><RunLogs /></SidebarLayout>} />
        <Route path="/schedules" element={<SidebarLayout><Schedules /></SidebarLayout>} />
        <Route path="/admin/dashboard" element={<SidebarLayout><AdminDashboard /></SidebarLayout>} />
        <Route path="/admin/tasks" element={<SidebarLayout><AdminTasks /></SidebarLayout>} />
        <Route path="/admin/results" element={<SidebarLayout><AdminResults /></SidebarLayout>} />
        <Route path="/admin/clients" element={<SidebarLayout><AdminClients /></SidebarLayout>} />
        <Route path="/admin/scripts" element={<SidebarLayout><AdminScripts /></SidebarLayout>} />
        <Route path="/admin/ai-apps" element={<SidebarLayout><AdminAIApps /></SidebarLayout>} />
        <Route path="/admin/password" element={<SidebarLayout><AdminPassword /></SidebarLayout>} />
        <Route path="/admin/commands" element={<SidebarLayout><AdminCommands /></SidebarLayout>} />
        <Route path="/editor/:id" element={<EditorPage />} />
      </Routes>
    </HashRouter>
  );
}

export default App;
