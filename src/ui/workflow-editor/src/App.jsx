import { HashRouter, Routes, Route, useParams, NavLink, useLocation } from 'react-router-dom';
import { WorkflowProvider } from './store/WorkflowContext';
import { ActiveRunProvider, useActiveRun } from './context/ActiveRunContext';
import Layout from './components/Layout';
import WorkflowList from './components/WorkflowList';
import RunLogs from './components/RunLogs';
import Schedules from './components/Schedules';
import AdminPassword from './components/admin/AdminPassword';
import CommandEditor from './components/CommandEditor';
import AIConfigPage from './components/AIConfigPage';

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
  const { activeRun, stopActiveRun } = useActiveRun();
  const hideSidebar = location.pathname.startsWith('/editor/');

  if (hideSidebar) {
    return children;
  }

  return (
    <div className="h-screen bg-[#0f172a] text-gray-200 flex overflow-hidden">
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
            to="/admin/password"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                isActive ? 'bg-blue-600/20 text-blue-300 border-r-2 border-blue-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
              }`
            }
          >
            <i className="fas fa-lock w-4 text-center"></i>
            修改密码
          </NavLink>
          <NavLink
            to="/commands/definitions"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                isActive ? 'bg-blue-600/20 text-blue-300 border-r-2 border-blue-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
              }`
            }
          >
            <i className="fas fa-file-code w-4 text-center"></i>
            指令定义
          </NavLink>
          <NavLink
            to="/ai-config"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                isActive ? 'bg-blue-600/20 text-blue-300 border-r-2 border-blue-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
              }`
            }
          >
            <i className="fas fa-brain w-4 text-center"></i>
            AI 配置
          </NavLink>
        </nav>

        {activeRun && (
          <div className="px-3 py-3 border-t border-gray-700">
            <div className="bg-blue-600/10 border border-blue-600/30 rounded-lg p-2.5">
              <div className="flex items-center gap-2 text-xs text-blue-300 mb-1.5">
                <i className="fas fa-circle-notch fa-spin"></i>
                <span className="truncate" title={activeRun.workflow_name || `流程 #${activeRun.workflow_id}`}>
                  运行中：{activeRun.workflow_name || `流程 #${activeRun.workflow_id}`}
                </span>
              </div>
              <button
                onClick={stopActiveRun}
                className="w-full px-2 py-1 bg-red-600/20 hover:bg-red-600/30 text-red-300 rounded text-xs flex items-center justify-center gap-1 transition-colors"
              >
                <i className="fas fa-stop"></i>
                停止运行
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 主内容区 */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {children}
      </div>
    </div>
  );
}

function App() {
  return (
    <HashRouter>
      <ActiveRunProvider>
        <Routes>
          <Route path="/" element={<SidebarLayout><WorkflowList /></SidebarLayout>} />
          <Route path="/logs" element={<SidebarLayout><RunLogs /></SidebarLayout>} />
          <Route path="/schedules" element={<SidebarLayout><Schedules /></SidebarLayout>} />
          <Route path="/admin/password" element={<SidebarLayout><AdminPassword /></SidebarLayout>} />
          <Route path="/commands/definitions" element={<SidebarLayout><CommandEditor /></SidebarLayout>} />
          <Route path="/ai-config" element={<SidebarLayout><AIConfigPage /></SidebarLayout>} />
          <Route path="/editor/:id" element={<EditorPage />} />
        </Routes>
      </ActiveRunProvider>
    </HashRouter>
  );
}

export default App;
