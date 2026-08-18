import { HashRouter, Routes, Route, useParams, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { WorkflowProvider } from './store/WorkflowContext';
import { ActiveRunProvider, useActiveRun } from './context/ActiveRunContext';
import Layout from './components/Layout';
import WorkflowList from './components/WorkflowList';
import RunLogs from './components/RunLogs';
import Schedules from './components/Schedules';
import CommandEditor from './components/CommandEditor';
import AIConfigPage from './components/AIConfigPage';

function EditorPage() {
  const { id } = useParams();
  const wfId = parseInt(id, 10);
  if (isNaN(wfId)) {
    return (
      <div className="h-screen flex items-center justify-center bg-bg text-white">
        <div className="text-center">
          <p className="text-faint mb-4">无效的工作流 ID</p>
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
  const navigate = useNavigate();
  const { activeRun, stopActiveRun, runResult, clearRunResult } = useActiveRun();
  const hideSidebar = location.pathname.startsWith('/editor/');

  if (hideSidebar) {
    return children;
  }

  return (
    <div className="h-screen bg-bg text-body flex overflow-hidden">
      {/* 侧边栏 */}
      <div className="w-52 bg-surface-2 border-r border-border flex flex-col shrink-0">
        <div className="px-4 py-5 flex items-center gap-2 border-b border-border">
          <i className="fas fa-project-diagram text-accent text-lg"></i>
          <span className="font-semibold text-white">RPA Script</span>
        </div>
        <nav className="flex-1 py-3 space-y-1">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                isActive ? 'bg-accent/20 text-accent-strong border-r-2 border-accent' : 'text-faint hover:text-body hover:bg-gray-800/50'
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
                isActive ? 'bg-accent/20 text-accent-strong border-r-2 border-accent' : 'text-faint hover:text-body hover:bg-gray-800/50'
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
                isActive ? 'bg-accent/20 text-accent-strong border-r-2 border-accent' : 'text-faint hover:text-body hover:bg-gray-800/50'
              }`
            }
          >
            <i className="fas fa-file-alt w-4 text-center"></i>
            运行日志
          </NavLink>
          <NavLink
            to="/commands/definitions"
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                isActive ? 'bg-accent/20 text-accent-strong border-r-2 border-accent' : 'text-faint hover:text-body hover:bg-gray-800/50'
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
                isActive ? 'bg-accent/20 text-accent-strong border-r-2 border-accent' : 'text-faint hover:text-body hover:bg-gray-800/50'
              }`
            }
          >
            <i className="fas fa-brain w-4 text-center"></i>
            AI 配置
          </NavLink>
        </nav>

        {activeRun && (
          <div className="px-3 py-3 border-t border-border">
            <div className="bg-accent/15 border border-accent/30 rounded-lg p-2.5">
              <div className="flex items-center gap-2 text-xs text-accent-strong mb-1.5">
                <i className="fas fa-circle-notch fa-spin"></i>
                <span className="truncate" title={activeRun.workflow_name || `流程 #${activeRun.workflow_id}`}>
                  运行中：{activeRun.workflow_name || `流程 #${activeRun.workflow_id}`}
                </span>
              </div>
              <button
                onClick={stopActiveRun}
                className="w-full px-2 py-1 bg-danger/20 hover:bg-danger/30 text-danger rounded text-xs flex items-center justify-center gap-1 transition-colors"
              >
                <i className="fas fa-stop"></i>
                停止运行
              </button>
            </div>
          </div>
        )}
        {!activeRun && runResult && (
          <div className="px-3 py-3 border-t border-border">
            <div className={`rounded-lg p-2.5 border ${
              runResult.kind === 'success'
                ? 'bg-ok/10 border-green-600/30'
                : runResult.kind === 'stopped'
                  ? 'bg-yellow-600/10 border-yellow-600/30'
                  : 'bg-danger/15 border-danger/30'
            }`}>
              <div className={`flex items-center gap-2 text-xs ${
                runResult.kind === 'success' ? 'text-ok' : runResult.kind === 'stopped' ? 'text-warn' : 'text-danger'
              }`}>
                <i className={`fas ${runResult.kind === 'success' ? 'fa-check-circle' : runResult.kind === 'stopped' ? 'fa-pause-circle' : 'fa-times-circle'}`}></i>
                <span className="truncate" title={runResult.error || ''}>
                  {runResult.kind === 'success' ? '执行成功' : runResult.kind === 'stopped' ? '已停止' : `失败: ${runResult.error || '未知错误'}`}
                </span>
                <button onClick={clearRunResult} className="ml-auto opacity-60 hover:opacity-100 shrink-0">×</button>
              </div>
              {runResult.run_id && (
                <button
                  onClick={() => {
                    navigate(`/logs?wf=${runResult.workflow_id}&run=${encodeURIComponent(runResult.run_id)}`);
                    clearRunResult();
                  }}
                  className="mt-1.5 w-full px-2 py-1 bg-accent/20 hover:bg-accent-strong/30 text-accent-strong rounded text-xs flex items-center justify-center gap-1 transition-colors"
                >
                  <i className="fas fa-file-alt"></i>
                  查看日志
                </button>
              )}
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
          <Route path="/commands/definitions" element={<SidebarLayout><CommandEditor /></SidebarLayout>} />
          <Route path="/ai-config" element={<SidebarLayout><AIConfigPage /></SidebarLayout>} />
          <Route path="/editor/:id" element={<EditorPage />} />
        </Routes>
      </ActiveRunProvider>
    </HashRouter>
  );
}

export default App;
