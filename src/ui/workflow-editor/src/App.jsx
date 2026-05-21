import { HashRouter, Routes, Route, useParams } from 'react-router-dom';
import { WorkflowProvider } from './store/WorkflowContext';
import Layout from './components/Layout';
import WorkflowList from './components/WorkflowList';

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
    <WorkflowProvider wfId={wfId}>
      <Layout />
    </WorkflowProvider>
  );
}

function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<WorkflowList />} />
        <Route path="/editor/:id" element={<EditorPage />} />
      </Routes>
    </HashRouter>
  );
}

export default App
