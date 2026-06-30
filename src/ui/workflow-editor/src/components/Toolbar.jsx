import { useState, useEffect, useRef } from 'react';
import { useWorkflow } from '../store/WorkflowContext';
import { api } from '../api';
import RunParametersDialog from './RunParametersDialog';

function formatResult(result) {
  if (typeof result !== 'object' || result === null) return String(result);
  const parts = [];
  if (result.element) parts.push(`元素「${result.element}」`);
  if (result.clicked) parts.push('点击成功');
  if (result.input !== undefined) parts.push(`输入 ${result.length ?? '?'} 个字符`);
  if (result.text !== undefined) parts.push(`文本: ${String(result.text).slice(0, 40)}`);
  if (result.extracted !== undefined) parts.push(`提取: ${String(result.extracted).slice(0, 40)}`);
  if (result.scrolled) parts.push(`滚动: ${result.scrolled}`);
  if (result.navigatedTo) parts.push(`导航: ${result.navigatedTo}`);
  if (result.hovered) parts.push('悬停成功');
  if (result.pressed) parts.push(`按键: ${result.pressed}`);
  if (result.selected) parts.push(`选择: ${result.text || result.selected}`);
  if (result.cleared) parts.push('已清空');
  if (result.匹配元素数 !== undefined) parts.push(`(匹配 ${result.匹配元素数} 个)`);
  if (result.使用备选方案) parts.push(`[${result.使用备选方案}]`);
  if (result.forList !== undefined) parts.push(`列表项: ${result.forList}`);
  if (result.forEachElement !== undefined) parts.push(`元素数: ${result.forEachElement}`);
  if (result.setVar) parts.push(`设置变量 ${result.setVar} = ${JSON.stringify(result.value).slice(0, 40)}`);
  if (result.ifElementVisible !== undefined) parts.push(`元素可见: ${result.ifElementVisible}`);
  if (result.ifElementExists !== undefined) parts.push(`元素存在: ${result.ifElementExists}`);
  if (result.log !== undefined) parts.push(`日志: ${result.log}`);
  if (parts.length === 0) return JSON.stringify(result).slice(0, 200);
  return parts.join(' ');
}

export default function Toolbar() {
  const { workflow, saving, wfId, isDirty, commit, nodes, NODE_TYPE_MAP, dispatch, elements, updateWorkflowParameters } = useWorkflow();
  const [running, setRunning] = useState(false);
  const [paused, setPaused] = useState(false);
  const [currentRunId, setCurrentRunId] = useState(null);
  const [runResult, setRunResult] = useState(null);
  const [runMode, setRunMode] = useState('extension'); // 'python' | 'extension'
  const [runParamsOpen, setRunParamsOpen] = useState(false);
  const [extStatus, setExtStatus] = useState(null);
  const [editingName, setEditingName] = useState(false);
  const [editNameValue, setEditNameValue] = useState('');
  const importInputRef = useRef(null);
  const stoppedRef = useRef(false);

  // Poll extension status when in extension mode
  useEffect(() => {
    if (runMode !== 'extension') {
      setExtStatus(null);
      return;
    }
    let mounted = true;
    const poll = async () => {
      try {
        const data = await api.getExtensionStatus();
        if (mounted) setExtStatus(data);
      } catch {
        if (mounted) setExtStatus({ online: false, count: 0 });
      }
    };
    poll();
    const timer = setInterval(poll, 5000);
    return () => { mounted = false; clearInterval(timer); };
  }, [runMode]);

  const handleExport = async () => {
    console.log(`[Toolbar] exportPython wfId=${wfId}`);
    try {
      const data = await api.exportPython(wfId);
      console.log(`[Toolbar] exportPython success, ${data.python?.length || 0} chars`);
      if (data.python) {
        await navigator.clipboard.writeText(data.python);
        alert('Python 脚本已复制到剪贴板');
      }
    } catch (e) {
      console.error(`[Toolbar] exportPython failed: ${e.message}`);
      alert('导出失败: ' + e.message);
    }
  };

  // 收集节点引用的 element_name（包括 extra.element_names 中的附加元素）
  const resolveElementNamesFromNode = (node) => {
    const names = new Set();
    if (node.element_name) names.add(node.element_name);
    let extra = node.extra;
    if (typeof extra === 'string') {
      try { extra = JSON.parse(extra); } catch { extra = {}; }
    }
    if (extra?.element_names && Array.isArray(extra.element_names)) {
      for (const name of extra.element_names) {
        if (name) names.add(name);
      }
    }
    return names;
  };

  const handleExportJSON = async () => {
    const usedElementNames = new Set();
    for (const n of nodes) {
      for (const name of resolveElementNamesFromNode(n)) {
        usedElementNames.add(name);
      }
    }
    const usedElements = elements.filter(e => usedElementNames.has(e.name)).map(e => ({ ...e }));
    const data = {
      workflow: {
        id: workflow?.id,
        name: workflow?.name,
        url: workflow?.url,
        parameters: Array.isArray(workflow?.parameters) ? workflow.parameters : [],
      },
      nodes: nodes.map(n => ({ ...n })),
      elements: usedElements,
      exportedAt: new Date().toISOString(),
    };
    const jsonStr = JSON.stringify(data, null, 2);
    const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    const filename = `${workflow?.name || 'workflow'}_${dateStr}.json`;

    // 桌面应用（pywebview）通过桥接调用系统保存对话框
    if (typeof window !== 'undefined' && window.pywebview?.api) {
      try {
        const res = await window.pywebview.api.saveFileDialog(jsonStr, filename);
        if (res?.success) {
          alert(`已保存到: ${res.path}`);
        } else if (res?.cancelled) {
          // 用户取消，不提示
        } else {
          alert('保存失败: ' + (res?.error || '未知错误'));
        }
      } catch (e) {
        alert('保存失败: ' + e.message);
      }
      return;
    }

    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImportJSON = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      if (!Array.isArray(data.nodes)) {
        alert('JSON 格式错误：缺少 nodes 数组');
        return;
      }
      const elementCount = Array.isArray(data.elements) ? data.elements.length : 0;
      const paramCount = Array.isArray(data.workflow?.parameters) ? data.workflow.parameters.length : 0;
      if (!confirm(`确定导入 "${file.name}"？\n共 ${data.nodes.length} 个节点${elementCount > 0 ? `，含 ${elementCount} 个元素` : ''}${paramCount > 0 ? `，含 ${paramCount} 个流程参数` : ''}，将覆盖当前流程。`)) {
        e.target.value = '';
        return;
      }
      // 先导入元素到当前流程：同名更新，不同名创建
      if (Array.isArray(data.elements) && data.elements.length > 0) {
        try {
          const existing = await api.getWorkflowElements(wfId);
          const existingByName = new Map(existing.map(e => [e.name, e]));
          for (const el of data.elements) {
            const payload = { ...el };
            delete payload.id;
            delete payload.workflow_id;
            delete payload.created_at;
            delete payload.updated_at;
            const old = existingByName.get(el.name);
            if (old) {
              await api.updateWorkflowElement(wfId, old.id, payload);
            } else {
              await api.createWorkflowElement(wfId, payload);
            }
          }
          const fresh = await api.getWorkflowElements(wfId);
          dispatch({ type: 'SET_ELEMENTS', payload: fresh });
        } catch (err) {
          console.error('[Toolbar] import elements failed:', err);
          alert('元素库导入失败: ' + err.message);
        }
      }
      // 恢复流程参数（旧版导出文件可能没有此字段，则跳过保留现有参数）
      const importedParams = data.workflow?.parameters;
      if (Array.isArray(importedParams)) {
        try {
          await updateWorkflowParameters(importedParams);
        } catch (err) {
          console.error('[Toolbar] import parameters failed:', err);
          alert('流程参数导入失败: ' + err.message);
        }
      }
      // 重新生成 temp_id 并修正 parent_id 映射，避免与现有节点 ID 冲突
      const oldToTemp = new Map();
      const imported = data.nodes.map((n) => {
        const tempId = crypto.randomUUID();
        oldToTemp.set(n.id, tempId);
        const copy = { ...n };
        delete copy.workflow_id;
        delete copy.created_at;
        copy.id = tempId;        // frontend tree/dnd needs id
        copy.temp_id = tempId;   // backend batch save uses temp_id
        return copy;
      });
      imported.forEach((n) => {
        if (n.parent_id != null && oldToTemp.has(n.parent_id)) {
          n.parent_id = oldToTemp.get(n.parent_id);
        } else if (n.parent_id != null) {
          // 父节点不在导入列表中，提升到顶层
          n.parent_id = null;
        }
      });
      dispatch({ type: 'REPLACE_NODES', payload: imported });
      e.target.value = '';
    } catch (err) {
      alert('导入失败: ' + err.message);
      e.target.value = '';
    }
  };

  const handleSave = async () => {
    try {
      await commit();
    } catch (e) {
      alert('保存失败: ' + e.message);
    }
  };

  const handleSaveName = async () => {
    const newName = editNameValue.trim();
    if (!newName || newName === workflow?.name) {
      setEditingName(false);
      return;
    }
    try {
      await api.updateWorkflow(wfId, { name: newName });
      dispatch({ type: 'SET_WORKFLOW', payload: { ...workflow, name: newName } });
      setEditingName(false);
    } catch (e) {
      alert('重命名失败: ' + e.message);
    }
  };

  const handleRunClick = () => {
    const params = workflow?.parameters;
    if (Array.isArray(params) && params.length > 0) {
      setRunParamsOpen(true);
      return;
    }
    doRun(null);
  };

  const doRun = async (parameters = null) => {
    console.log(`[Toolbar] run clicked, mode=${runMode}, isDirty=${isDirty}`);
    if (isDirty) {
      const ok = confirm('工作流有未保存的更改，先保存再运行？');
      if (!ok) return;
      try {
        await commit();
      } catch (e) {
        alert('保存失败，无法运行: ' + e.message);
        return;
      }
    }

    setRunning(true);
    setPaused(false);
    setRunResult(null);
    dispatch({ type: 'RUN_START' });
    dispatch({ type: 'CLEAR_RUN_LOGS' });

    if (runMode === 'extension') {
      dispatch({ type: 'APPEND_RUN_LOG', payload: { time: new Date().toLocaleTimeString('zh-CN'), level: 'info', msg: '开始执行（扩展模式）' } });
    } else {
      dispatch({ type: 'APPEND_RUN_LOG', payload: { time: new Date().toLocaleTimeString('zh-CN'), level: 'info', msg: '开始执行（Python 模式）' } });
    }

    let es = null;
    const runId = crypto.randomUUID();
    setCurrentRunId(runId);

    if (runMode === 'extension') {
      // Open SSE stream before POST so we don't miss early events
      es = new EventSource(`/api/workflows/${wfId}/run/stream?run_id=${runId}`);
      es.onmessage = (e) => {
        try {
          const evt = JSON.parse(e.data);
          console.log('[Toolbar] SSE event:', evt.type, evt);
          const t = new Date().toLocaleTimeString('zh-CN');
          if (evt.type === 'stepStart') {
            dispatch({ type: 'RUN_STEP', payload: { nodeId: evt.nodeId } });
          } else if (evt.type === 'stepComplete') {
            dispatch({ type: 'RUN_STEP', payload: { nodeId: null } });
            const node = nodes.find(n => n.id === evt.nodeId);
            const label = node ? `#${node.order} ${NODE_TYPE_MAP[node.type]?.label || node.type}` : evt.stepId;
            const resultStr = evt.result ? formatResult(evt.result) : '完成';
            dispatch({ type: 'APPEND_RUN_LOG', payload: { time: t, level: 'success', msg: `${label}: ${resultStr}` } });
            if (evt.result?.log !== undefined) {
              dispatch({ type: 'APPEND_RUN_LOG', payload: { time: t, level: 'info', msg: `  📝 ${evt.result.log}` } });
            }
            if (evt.result?.prints?.length) {
              for (const line of evt.result.prints) {
                dispatch({ type: 'APPEND_RUN_LOG', payload: { time: t, level: 'info', msg: `  🖨 ${line}` } });
              }
            }
            // Real-time table updates pushed to DataTableTab via CustomEvent
            if (evt.result?.tableData) {
              window.dispatchEvent(new CustomEvent('runtime-table-update', {
                detail: { wfId, tableData: evt.result.tableData }
              }));
            }
          } else if (evt.type === 'stepError') {
            dispatch({ type: 'RUN_STEP_ERROR', payload: { nodeId: evt.nodeId, error: evt.error } });
            const node = nodes.find(n => n.id === evt.nodeId);
            const label = node ? `#${node.order} ${NODE_TYPE_MAP[node.type]?.label || node.type}` : evt.stepId;
            dispatch({ type: 'APPEND_RUN_LOG', payload: { time: t, level: 'error', msg: `${label}: ${evt.error}` } });
          } else if (evt.type === 'paused') {
            dispatch({ type: 'RUN_PAUSED' });
            dispatch({ type: 'APPEND_RUN_LOG', payload: { time: t, level: 'warn', msg: '⏸ 已暂停' } });
          } else if (evt.type === 'done') {
            dispatch({ type: 'RUN_DONE', payload: { success: evt.success, stopped: evt.stopped } });
            const msg = evt.stopped ? '用户停止运行' : (evt.success ? '执行完成' : '执行失败');
            const level = evt.stopped ? 'warn' : (evt.success ? 'success' : 'error');
            dispatch({ type: 'APPEND_RUN_LOG', payload: { time: t, level, msg } });
            es.close();
          }
        } catch (err) {
          console.error('[Toolbar] SSE parse error', err);
        }
      };
      es.onerror = (err) => {
        console.error('[Toolbar] SSE error', err);
        // Recover UI when SSE connection drops unexpectedly
        setRunning(false);
        setPaused(false);
        setCurrentRunId(null);
        dispatch({ type: 'RUN_DONE', payload: { success: false, stopped: false } });
        dispatch({ type: 'APPEND_RUN_LOG', payload: { time: new Date().toLocaleTimeString('zh-CN'), level: 'warn', msg: '连接中断，执行状态未知' } });
      };
    }

    // Read design-time table data from localStorage for runtime initialization
    const getDesignTableData = () => {
      try {
        const raw = localStorage.getItem(`workflow_table_${wfId}`);
        return raw ? JSON.parse(raw) : null;
      } catch { return null; }
    };

    console.log(`[Toolbar] calling runWorkflow mode=${runMode} wfId=${wfId}`);
    try {
      const data = runMode === 'extension'
        ? await api.runWorkflowExtension(wfId, runId, getDesignTableData(), parameters)
        : await api.runWorkflow(wfId, parameters);
      console.log(`[Toolbar] runWorkflow result success=${data.success}`);
      if (!stoppedRef.current) {
        setRunResult(data);
      }
      // Final table data: push to DataTableTab for display only (do NOT overwrite design-time data)
      if (data.tableRows || data.tableColumns) {
        const finalTable = { rows: data.tableRows || [], columns: data.tableColumns || [] };
        window.dispatchEvent(new CustomEvent('runtime-table-update', {
          detail: { wfId, tableData: finalTable }
        }));
      }
      dispatch({ type: 'RUN_DONE', payload: { success: data.success, stopped: data.stopped } });
    } catch (e) {
      console.error(`[Toolbar] runWorkflow failed: ${e.message}`);
      if (!stoppedRef.current) {
        setRunResult({ success: false, stderr: e.message, stdout: '', returncode: -1 });
      }
      dispatch({ type: 'RUN_DONE', payload: { success: false, stopped: false } });
    } finally {
      setRunning(false);
      setPaused(false);
      setCurrentRunId(null);
      stoppedRef.current = false;
      if (es) {
        try { es.close(); } catch {}
      }
    }
  };

  const handlePause = async () => {
    if (!currentRunId) return;
    try {
      await api.pauseRun(wfId, currentRunId);
      setPaused(true);
      // 日志由 SSE paused 事件统一追加，避免重复
    } catch (e) {
      console.error('[Toolbar] pause failed:', e);
    }
  };

  const handleResume = async () => {
    if (!currentRunId) return;
    try {
      await api.resumeRun(wfId, currentRunId);
      setPaused(false);
      dispatch({ type: 'APPEND_RUN_LOG', payload: { time: new Date().toLocaleTimeString('zh-CN'), level: 'info', msg: '▶ 已继续' } });
    } catch (e) {
      console.error('[Toolbar] resume failed:', e);
    }
  };

  const handleStop = async () => {
    if (!currentRunId) return;
    stoppedRef.current = true;
    try {
      await api.stopRun(wfId, currentRunId);
      setRunResult({ stopped: true });
      dispatch({ type: 'APPEND_RUN_LOG', payload: { time: new Date().toLocaleTimeString('zh-CN'), level: 'error', msg: '⏹ 已停止' } });
    } catch (e) {
      console.error('[Toolbar] stop failed:', e);
    }
    // Reset UI immediately regardless of API success — the runner will eventually emit done
    setRunning(false);
    setPaused(false);
    setCurrentRunId(null);
  };

  const closeResult = () => setRunResult(null);

  const extDotColor = extStatus?.online ? 'bg-green-500' : 'bg-red-500';

  return (
    <>
      <header className="h-11 bg-white border-b border-[#e8e8e8] flex items-center justify-between px-3 select-none shrink-0">
        {/* 左侧：标题 */}
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex items-center gap-1.5">
            <div className="w-6 h-6 bg-[#1677ff] rounded flex items-center justify-center text-white text-xs font-bold">
              <i className="fas fa-project-diagram text-[10px]"></i>
            </div>
            {editingName ? (
              <input
                autoFocus
                className="text-sm font-medium text-gray-700 border border-[#1677ff] rounded px-1.5 py-0.5 outline-none w-48"
                value={editNameValue}
                onChange={(e) => setEditNameValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    handleSaveName();
                  } else if (e.key === 'Escape') {
                    setEditingName(false);
                  }
                }}
                onBlur={handleSaveName}
              />
            ) : (
              <span
                className="text-sm font-medium text-gray-700 truncate max-w-[200px] cursor-pointer hover:text-[#1677ff]"
                onClick={() => {
                  setEditNameValue(workflow?.name || '');
                  setEditingName(true);
                }}
                title="点击修改流程名称"
              >
                {workflow?.name || '加载中...'}
              </span>
            )}
          </div>
          {saving && <span className="text-xs text-gray-400">保存中...</span>}
          {isDirty && !saving && <span className="text-xs text-orange-500">● 未保存</span>}
        </div>

        {/* 中间：工具按钮 */}
        <div className="flex items-center gap-1">
          <button
            className={`h-7 px-3 flex items-center gap-1.5 rounded text-xs transition-colors ${
              isDirty
                ? 'bg-[#1677ff] hover:bg-[#4096ff] text-white'
                : 'bg-gray-100 text-gray-400 cursor-not-allowed'
            }`}
            onClick={handleSave}
            disabled={!isDirty || saving}
            title="保存到服务器"
          >
            <i className="fas fa-save text-[10px]"></i>
            <span>保存</span>
          </button>
          <div className="w-px h-5 bg-gray-200 mx-1"></div>
          <button
            className="h-7 px-3 flex items-center gap-1.5 rounded border border-[#d9d9d9] hover:border-[#1677ff] hover:text-[#1677ff] text-xs text-gray-600 transition-colors"
            onClick={handleExport}
          >
            <i className="fas fa-code text-[10px]"></i>
            <span>导出 Python</span>
          </button>
          <button
            className="h-7 px-3 flex items-center gap-1.5 rounded border border-[#d9d9d9] hover:border-[#1677ff] hover:text-[#1677ff] text-xs text-gray-600 transition-colors"
            onClick={handleExportJSON}
          >
            <i className="fas fa-file-export text-[10px]"></i>
            <span>导出 JSON</span>
          </button>
          <button
            className="h-7 px-3 flex items-center gap-1.5 rounded border border-[#d9d9d9] hover:border-[#1677ff] hover:text-[#1677ff] text-xs text-gray-600 transition-colors"
            onClick={() => importInputRef.current?.click()}
          >
            <i className="fas fa-file-import text-[10px]"></i>
            <span>导入 JSON</span>
          </button>
          <input
            ref={importInputRef}
            type="file"
            accept=".json"
            className="hidden"
            onChange={handleImportJSON}
          />
          <div className="w-px h-5 bg-gray-200 mx-1"></div>

          {/* Run mode toggle */}
          <div className="flex items-center bg-gray-100 rounded p-0.5">
            <button
              className={`h-6 px-2 rounded text-xs transition-colors ${runMode === 'python' ? 'bg-white shadow-sm text-gray-800' : 'text-gray-500 hover:text-gray-700'}`}
              onClick={() => setRunMode('python')}
              title="在子进程中运行 Python 脚本"
            >
              Python
            </button>
            <button
              className={`h-6 px-2 rounded text-xs transition-colors flex items-center gap-1 ${runMode === 'extension' ? 'bg-white shadow-sm text-gray-800' : 'text-gray-500 hover:text-gray-700'}`}
              onClick={() => setRunMode('extension')}
              title="通过浏览器扩展执行"
            >
              {runMode === 'extension' && (
                <span className={`w-1.5 h-1.5 rounded-full ${extDotColor}`}></span>
              )}
              扩展
            </button>
          </div>

          {/* Run controls */}
          {!running ? (
            <button
              className={`h-7 px-3 flex items-center gap-1.5 rounded bg-[#1f1f1f] hover:bg-black text-white text-xs transition-colors run-pulse`}
              onClick={handleRunClick}
            >
              <i className="fas fa-play text-[10px]"></i>
              <span>运行</span>
            </button>
          ) : runMode === 'python' ? (
            <div className="flex items-center gap-1">
              <button
                className="h-7 px-3 flex items-center gap-1.5 rounded bg-red-500 hover:bg-red-600 text-white text-xs transition-colors"
                onClick={handleStop}
              >
                <i className="fas fa-stop text-[10px]"></i>
                <span>停止</span>
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-1">
              {paused ? (
                <button
                  className="h-7 px-3 flex items-center gap-1.5 rounded bg-green-600 hover:bg-green-700 text-white text-xs transition-colors"
                  onClick={handleResume}
                >
                  <i className="fas fa-play text-[10px]"></i>
                  <span>继续</span>
                </button>
              ) : (
                <button
                  className="h-7 px-3 flex items-center gap-1.5 rounded bg-amber-500 hover:bg-amber-600 text-white text-xs transition-colors"
                  onClick={handlePause}
                >
                  <i className="fas fa-pause text-[10px]"></i>
                  <span>暂停</span>
                </button>
              )}
              <button
                className="h-7 px-3 flex items-center gap-1.5 rounded bg-red-500 hover:bg-red-600 text-white text-xs transition-colors"
                onClick={handleStop}
              >
                <i className="fas fa-stop text-[10px]"></i>
                <span>停止</span>
              </button>
            </div>
          )}
          <a
            href="/workflow-editor/"
            className="h-7 px-2.5 flex items-center gap-1.5 rounded border border-[#d9d9d9] hover:border-[#1677ff] hover:text-[#1677ff] text-xs text-gray-600 transition-colors"
          >
            <i className="fas fa-arrow-left text-[10px]"></i>
            <span>返回</span>
          </a>
        </div>

        {/* 右侧：用户信息 */}
        <div className="flex items-center gap-3">
          {typeof window !== 'undefined' && window.__USER__ ? (
            <>
              <div className="flex items-center gap-1.5 text-xs text-gray-500">
                <i className="fas fa-user-circle text-gray-400"></i>
                <span className="font-medium">{window.__USER__.username}</span>
              </div>
              <a
                href="/admin/logout"
                className="text-xs text-gray-400 hover:text-red-500 transition-colors"
                title="退出登录"
              >
                <i className="fas fa-sign-out-alt"></i>
              </a>
            </>
          ) : (
            <span className="text-xs text-gray-400">workflow-editor</span>
          )}
        </div>
      </header>

      {/* 运行参数弹窗 */}
      {runParamsOpen && (
        <RunParametersDialog
          parameters={workflow?.parameters}
          onConfirm={(values) => {
            setRunParamsOpen(false);
            doRun(values);
          }}
          onCancel={() => setRunParamsOpen(false)}
        />
      )}

      {/* 运行结果弹窗 */}
      {runResult && (
        <RunResultModal result={runResult} onClose={closeResult} mode={runMode} nodes={nodes} typeMap={NODE_TYPE_MAP} />
      )}
    </>
  );
}

function RunResultModal({ result, onClose, mode, nodes, typeMap }) {
  const isExtension = mode === 'extension';
  const success = result.success;
  const stopped = result.stopped;

  const getLabel = (r) => {
    if (!nodes || !r.nodeId) return r.stepId;
    const node = nodes.find(n => n.id === r.nodeId);
    if (!node) return r.stepId;
    return `#${node.order} ${typeMap[node.type]?.label || node.type}`;
  };

  const title = stopped ? '停止执行' : (success ? '运行成功' : '运行失败');
  const titleIcon = stopped ? 'fa-hand-paper text-amber-500' : (success ? 'fa-check-circle text-green-500' : 'fa-times-circle text-red-500');

  return (
    <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
        {/* 头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <i className={`fas ${titleIcon}`}></i>
            <span className="text-sm font-medium">
              {title}
            </span>
            {!isExtension && (
              <span className="text-xs text-gray-400">exit code: {result.returncode}</span>
            )}
            {isExtension && result.completedSteps !== undefined && (
              <span className="text-xs text-gray-400">
                步骤: {result.completedSteps}/{result.totalSteps}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded hover:bg-gray-100 text-gray-400"
          >
            <i className="fas fa-times text-xs"></i>
          </button>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {/* Extension mode results */}
          {isExtension && result.results && (
            <div>
              <div className="text-xs text-gray-500 mb-1 font-medium">执行结果</div>
              <div className="bg-gray-50 rounded p-3 space-y-1 max-h-48 overflow-y-auto">
                {result.results.map((r, i) => (
                  <div key={i} className="text-xs font-mono flex items-start gap-2">
                    <span className={`shrink-0 w-4 h-4 rounded-full flex items-center justify-center text-[8px] ${r.status === 'success' ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-600'}`}>
                      {r.status === 'success' ? '✓' : '✗'}
                    </span>
                    <span className="text-gray-600">{getLabel(r)}:</span>
                    <span className="text-gray-800 truncate">
                      {r.status === 'success' ? (r.result?.log !== undefined ? r.result.log : JSON.stringify(r.result)) : r.error}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {isExtension && result.failedSteps && result.failedSteps.length > 0 && (
            <div>
              <div className="text-xs text-red-500 mb-1 font-medium">失败步骤</div>
              <div className="bg-red-50 rounded p-3 space-y-1 max-h-48 overflow-y-auto">
                {result.failedSteps.map((s, i) => (
                  <pre key={i} className="text-xs text-red-700 whitespace-pre-wrap font-mono">
                    {getLabel(s)}: {s.error}
                  </pre>
                ))}
              </div>
            </div>
          )}

          {/* Python mode output */}
          {!isExtension && result.stdout && (
            <div>
              <div className="text-xs text-gray-500 mb-1 font-medium">标准输出</div>
              <pre className="bg-gray-50 rounded p-3 text-xs text-gray-700 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto">
                {result.stdout}
              </pre>
            </div>
          )}
          {!isExtension && result.stderr && (
            <div>
              <div className="text-xs text-red-500 mb-1 font-medium">错误输出</div>
              <pre className="bg-red-50 rounded p-3 text-xs text-red-700 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto">
                {result.stderr}
              </pre>
            </div>
          )}

          {/* No output fallback */}
          {!result.stdout && !result.stderr && (!result.results || result.results.length === 0) && (
            <div className="text-sm text-gray-400 text-center py-8">无输出</div>
          )}
        </div>

        {/* 底部 */}
        <div className="px-4 py-3 border-t border-gray-200 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-[#1677ff] hover:bg-[#4096ff] text-white text-xs rounded transition-colors"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
