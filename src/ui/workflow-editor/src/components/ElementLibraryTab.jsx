import { useState, useEffect, useRef, useMemo } from 'react';
import { useWorkflow } from '../store/WorkflowContext';
import { api } from '../api';
import DataTableTab from './DataTableTab';

const BOTTOM_TABS = [
  { key: 'elements', label: '元素库', icon: 'fa-crosshairs' },
  { key: 'images', label: '图像库', icon: 'fa-image' },
  { key: 'dataTable', label: '数据表格', icon: 'fa-table' },
  { key: 'logs', label: '运行日志', icon: 'fa-terminal' },
  { key: 'params', label: '流程参数', icon: 'fa-sliders-h' },
];

export default function ElementLibraryTab() {
  const { elements, loadElements, runLogs, runStatus, wfId } = useWorkflow();
  const [selectedHost, setSelectedHost] = useState('');
  const [activeTab, setActiveTab] = useState('elements');
  const [expanded, setExpanded] = useState(() => {
    try { return localStorage.getItem('wf_editor_bottom_expanded') !== 'false'; }
    catch { return true; }
  });
  const [selectedElementId, setSelectedElementId] = useState(null);
  const [extOnline, setExtOnline] = useState(false);
  const [extCount, setExtCount] = useState(0);
  const [extBrowsers, setExtBrowsers] = useState([]);  // [{browser, count}]
  const [targetBrowser, setTargetBrowser] = useState(''); // '' = all, 'chrome', 'edge'
  const [capturing, setCapturing] = useState(false);
  const [toast, setToast] = useState(null);
  const [renamingId, setRenamingId] = useState(null);
  const [renamingValue, setRenamingValue] = useState('');
  const renameRef = useRef(null);
  const logsRef = useRef(null);
  const panelRef = useRef(null);
  const importRef = useRef(null);

  function toggleExpanded(next) {
    try { localStorage.setItem('wf_editor_bottom_expanded', String(next)); } catch {}
    setExpanded(next);
  }

  // 点击运行后自动切换到运行日志 tab
  useEffect(() => {
    if (runStatus === 'running') {
      setActiveTab('logs');
    }
  }, [runStatus]);

  // 展开时从 localStorage 恢复高度
  useEffect(() => {
    if (!expanded || !panelRef.current) return;
    try {
      const saved = JSON.parse(localStorage.getItem('wf_editor_layout') || '{}');
      if (saved.bottomHeight) {
        panelRef.current.style.height = saved.bottomHeight + 'px';
      }
    } catch {}
  }, [expanded]);

  // 运行日志自动滚底：切换标签或新增日志时，若之前在底部则保持底部
  useEffect(() => {
    if (activeTab !== 'logs' || !logsRef.current) return;
    const el = logsRef.current;
    // 切换标签时直接滚到底部
    if (runLogs.length > 0) {
      el.scrollTop = el.scrollHeight;
    }
  }, [activeTab]);

  useEffect(() => {
    if (!logsRef.current || runLogs.length === 0) return;
    const el = logsRef.current;
    const isAtBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
    if (isAtBottom) {
      el.scrollTop = el.scrollHeight;
    }
  }, [runLogs]);

  const selectedElement = elements.find(e => e.id === selectedElementId) || null;

  // 从 elements 派生站点列表，捕获新站点后自动更新
  const hosts = useMemo(() => {
    const set = new Set();
    for (const e of elements) {
      if (e.hostname) set.add(e.hostname);
    }
    return Array.from(set).sort();
  }, [elements]);

  useEffect(() => {
    if (renamingId && renameRef.current) {
      renameRef.current.focus();
      renameRef.current.select();
    }
  }, [renamingId]);

  // 加载元素库
  const refresh = async () => {
    await loadElements();
  };

  useEffect(() => {
    refresh();
  }, []);

  // 轮询扩展在线状态
  useEffect(() => {
    let timer = null;
    const checkStatus = async () => {
      try {
        const data = await api.getExtensionStatus();
        setExtOnline(data.online);
        setExtCount(data.count);
        setExtBrowsers(data.browsers || []);
        // 如果只有一个浏览器在线，自动选它
        if ((data.browsers || []).length === 1 && !targetBrowser) {
          setTargetBrowser(data.browsers[0].browser);
        }
      } catch {
        setExtOnline(false);
        setExtCount(0);
        setExtBrowsers([]);
      }
    };
    checkStatus();
    timer = setInterval(checkStatus, 3000);
    return () => clearInterval(timer);
  }, [targetBrowser]);

  // 捕获完成后自动刷新（轮询检测新元素）
  useEffect(() => {
    if (!capturing) return;
    const beforeCount = elements.length;
    const timer = setInterval(async () => {
      await loadElements();
      if (elements.length > beforeCount) {
        setCapturing(false);
        clearInterval(timer);
      }
    }, 2000);
    // 最长等待 30 秒
    const timeout = setTimeout(() => {
      setCapturing(false);
      clearInterval(timer);
    }, 30000);
    return () => {
      clearInterval(timer);
      clearTimeout(timeout);
    };
  }, [capturing]);

  // 智能轮询：只在元素库 tab 激活且页面可见时刷新（跨浏览器/桌面应用唯一可靠方案）
  useEffect(() => {
    if (activeTab !== 'elements') return;
    const tick = () => {
      if (!document.hidden) loadElements();
    };
    tick(); // 立即刷新一次
    const timer = setInterval(tick, 5000);
    return () => clearInterval(timer);
  }, [activeTab]);

  const filtered = selectedHost
    ? elements.filter(e => e.hostname === selectedHost)
    : elements;

  const showToast = (msg, type = 'info') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleDelete = async (id, name) => {
    if (!window.confirm(`确认删除元素 "${name}"？`)) return;
    try {
      await api.deleteElement(id);
      showToast(`已删除 "${name}"`);
      if (selectedElementId === id) setSelectedElementId(null);
      await refresh();
    } catch (e) {
      showToast('删除失败: ' + e.message, 'error');
    }
  };

  const startRename = (el) => {
    setRenamingId(el.id);
    setRenamingValue(el.name);
  };

  const submitRename = async (id) => {
    const name = renamingValue.trim();
    if (!name) {
      setRenamingId(null);
      return;
    }
    try {
      await api.updateElement(id, { name });
      showToast('重命名成功');
      setRenamingId(null);
      await refresh();
    } catch (e) {
      showToast('重命名失败: ' + e.message, 'error');
      setRenamingId(null);
    }
  };

  const cancelRename = () => setRenamingId(null);

  const handleCapture = async () => {
    if (!extOnline) {
      showToast('浏览器扩展未连接，请确认扩展已安装并刷新页面', 'error');
      return;
    }
    setCapturing(true);
    try {
      const res = await api.sendExtensionCommand('enterCaptureMode', {}, targetBrowser || undefined);
      if (res.success) {
        const browserLabel = targetBrowser ? `[${targetBrowser}] ` : '';
        showToast(`${browserLabel}已发送抓取命令，请点击元素捕获`);
      } else {
        showToast('抓取命令发送失败: ' + (res.error || '未知错误'), 'error');
        setCapturing(false);
      }
    } catch (e) {
      showToast('抓取失败: ' + e.message, 'error');
      setCapturing(false);
    }
  };

  const handleExport = async () => {
    try {
      const res = await api.exportElements();
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `elements-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      showToast(`已导出 ${data.length} 个元素`);
    } catch (e) {
      showToast('导出失败: ' + e.message, 'error');
    }
  };

  const handleImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    try {
      const text = await file.text();
      const items = JSON.parse(text);
      if (!Array.isArray(items)) {
        showToast('文件格式错误: 应为 JSON 数组', 'error');
        return;
      }
      const result = await api.importElements(items);
      showToast(`导入完成: ${result.imported} 个成功${result.failed ? `, ${result.failed} 个失败` : ''}`);
      await refresh();
    } catch (err) {
      showToast('导入失败: ' + err.message, 'error');
    }
  };

  if (!expanded) {
    return (
      <div className="h-8 bg-white border-t border-[#e8e8e8] flex items-center px-4 cursor-pointer hover:bg-gray-50"
           onClick={() => toggleExpanded(true)}>
        <span className="text-xs text-gray-500">
          <i className="fas fa-chevron-up mr-1"></i>
          元素库 ({elements.length})
        </span>
      </div>
    );
  }

  return (
    <div ref={panelRef} className="h-[220px] bg-white border-t border-[#e8e8e8] flex flex-col shrink-0 select-none">
      {/* Tab 栏 */}
      <div className="flex items-center border-b border-[#e8e8e8] px-2">
        {BOTTOM_TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-3 py-2 text-xs ${activeTab === tab.key ? 'tab-active' : 'text-gray-500 hover:text-gray-700'}`}
          >
            <i className={`fas ${tab.icon} mr-1`}></i>
            {tab.label}
          </button>
        ))}
        <button
          onClick={() => toggleExpanded(false)}
          className="ml-auto px-2 py-2 text-xs text-gray-400 hover:text-gray-600"
        >
          <i className="fas fa-chevron-down"></i>
        </button>
      </div>

      {/* 内容区 */}
      <div className="flex-1 flex overflow-hidden">
        {activeTab === 'logs' ? (
          <div ref={logsRef} className="flex-1 overflow-y-auto p-2 font-mono text-xs select-text">
            {runLogs.length === 0 ? (
              <div className="text-center text-gray-400 py-8">
                {runStatus === 'running' ? (
                  <span><i className="fas fa-spinner fa-spin mr-1"></i>等待执行日志...</span>
                ) : (
                  <span>暂无运行日志</span>
                )}
              </div>
            ) : (
              <div className="space-y-1">
                {runLogs.map((log, i) => {
                  const stepMatch = log.msg.match(/^#(\d+)\s/);
                  const stepNum = stepMatch ? stepMatch[1] : null;
                  const msgWithoutStep = stepNum ? log.msg.slice(stepMatch[0].length) : log.msg;
                  return (
                    <div key={i} className={`flex gap-2 px-2 py-1 rounded ${
                      log.level === 'error' ? 'bg-red-50 text-red-700' :
                      log.level === 'success' ? 'bg-green-50 text-green-700' :
                      'text-gray-600'
                    }`}>
                      <span className="text-gray-400 shrink-0">{log.time}</span>
                      {stepNum && (
                        <span className="shrink-0 px-1.5 py-0.5 rounded bg-gray-200 text-gray-600 text-[10px] font-mono leading-4">
                          #{stepNum}
                        </span>
                      )}
                      <span className="break-all">{msgWithoutStep}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ) : activeTab === 'dataTable' ? (
          <DataTableTab wfId={wfId} />
        ) : activeTab === 'elements' ? (
          <>
            {/* 左侧元素树 */}
            <div className="w-[280px] border-r border-[#e8e8e8] overflow-y-auto p-2">
              <div className="flex items-center gap-2 mb-2">
                <select
                  value={selectedHost}
                  onChange={(e) => setSelectedHost(e.target.value)}
                  className="flex-1 px-2 py-1 bg-[#fafafa] border border-[#d9d9d9] rounded text-xs text-gray-700 outline-none"
                >
                  <option value="">全部站点</option>
                  {hosts.map(h => (
                    <option key={h} value={h}>{h}</option>
                  ))}
                </select>
                <span className="text-xs text-gray-400">{filtered.length}</span>
                <button
                  onClick={handleExport}
                  className="text-gray-400 hover:text-blue-500 px-1"
                  title="导出全部"
                >
                  <i className="fas fa-download text-[10px]"></i>
                </button>
                <button
                  onClick={() => importRef.current?.click()}
                  className="text-gray-400 hover:text-green-500 px-1"
                  title="导入"
                >
                  <i className="fas fa-upload text-[10px]"></i>
                </button>
                <input
                  ref={importRef}
                  type="file"
                  accept=".json"
                  className="hidden"
                  onChange={handleImport}
                />
              </div>
              {filtered.length === 0 ? (
                <div className="text-center text-gray-400 text-xs py-8">暂无元素</div>
              ) : (
                <div className="space-y-0.5">
                  {filtered.map(el => (
                    <div
                      key={el.id}
                      onClick={() => { if (renamingId !== el.id) setSelectedElementId(el.id); }}
                      className={`group flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer ${
                        selectedElementId === el.id
                          ? 'bg-blue-50 border border-blue-200'
                          : 'hover:bg-gray-100 border border-transparent'
                      }`}
                    >
                      <i className={`fas fa-crosshairs text-[10px] w-4 text-center ${
                        selectedElementId === el.id ? 'text-blue-500' : 'text-gray-400'
                      }`}></i>
                      <div className="flex-1 min-w-0">
                        {renamingId === el.id ? (
                          <input
                            ref={renameRef}
                            value={renamingValue}
                            onChange={(e) => setRenamingValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') submitRename(el.id);
                              if (e.key === 'Escape') cancelRename();
                            }}
                            onBlur={() => submitRename(el.id)}
                            onClick={(e) => e.stopPropagation()}
                            className="w-full text-xs px-1 py-0.5 border border-blue-300 rounded outline-none bg-white"
                          />
                        ) : (
                          <>
                            <div className={`text-xs truncate ${
                              selectedElementId === el.id ? 'text-blue-700 font-medium' : 'text-gray-700'
                            }`}>{el.name}</div>
                            <div className="text-[10px] text-gray-400 truncate">{el.locator}</div>
                          </>
                        )}
                      </div>
                      {renamingId !== el.id && (
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={(e) => { e.stopPropagation(); startRename(el); }}
                            className="text-gray-400 hover:text-blue-500 px-1"
                            title="重命名"
                          >
                            <i className="fas fa-pen text-[10px]"></i>
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDelete(el.id, el.name); }}
                            className="text-gray-400 hover:text-red-500 px-1"
                            title="删除"
                          >
                            <i className="fas fa-trash text-[10px]"></i>
                          </button>
                        </div>
                      )}
                      <span className="text-[10px] text-gray-400">{el.locator_type}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            {/* 右侧详情区 */}
            <div className="flex-1 overflow-y-auto p-4">
              <div className="flex items-center justify-end mb-4 gap-2">
                {/* 浏览器选择器（多浏览器时显示） */}
                {extBrowsers.length > 1 && (
                  <select
                    value={targetBrowser}
                    onChange={(e) => setTargetBrowser(e.target.value)}
                    className="px-2 py-1 bg-[#fafafa] border border-[#d9d9d9] rounded text-xs text-gray-700 outline-none"
                  >
                    <option value="">所有浏览器</option>
                    {extBrowsers.map(b => (
                      <option key={b.browser} value={b.browser}>
                        {b.browser === 'edge' ? 'Edge' : 'Chrome'} ({b.count})
                      </option>
                    ))}
                  </select>
                )}
                <div className="flex items-center gap-1.5 mr-1">
                  <div
                    className={`w-2 h-2 rounded-full ${extOnline ? 'bg-green-500' : 'bg-gray-300'}`}
                    title={extOnline ? `扩展在线 (${extCount})` : '扩展未连接'}
                  />
                  <span className="text-[10px] text-gray-400">
                    {extOnline ? `在线 (${extCount})` : '未连接'}
                  </span>
                </div>
                <button
                  className={`flex items-center gap-1 px-3 py-1.5 rounded text-xs transition-colors ${
                    extOnline
                      ? 'bg-orange-500 hover:bg-orange-600 text-white'
                      : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                  }`}
                  onClick={handleCapture}
                  disabled={!extOnline || capturing}
                  title={extOnline ? `发送到: ${targetBrowser || '所有浏览器'}` : '扩展未连接'}
                >
                  <i className={`fas ${capturing ? 'fa-spinner fa-spin' : 'fa-plus'} text-[10px]`}></i>
                  <span>{capturing ? '等待捕获...' : '捕获新元素'}</span>
                </button>
              </div>
              {selectedElement ? (
                <div className="max-w-2xl">
                  {/* 标题 */}
                  <div className="flex items-center gap-2 mb-4">
                    <i className="fas fa-crosshairs text-blue-500"></i>
                    <h3 className="text-sm font-medium text-gray-800">{selectedElement.name}</h3>
                    {selectedElement.tag && (
                      <span className="px-1.5 py-0.5 bg-gray-100 rounded text-[10px] text-gray-500">
                        {selectedElement.tag}
                      </span>
                    )}
                    <div className="ml-auto flex items-center gap-1">
                      <button
                        onClick={() => startRename(selectedElement)}
                        className="text-gray-400 hover:text-blue-500 px-1.5 py-0.5 rounded hover:bg-gray-100"
                        title="重命名"
                      >
                        <i className="fas fa-pen text-xs"></i>
                      </button>
                      <button
                        onClick={() => handleDelete(selectedElement.id, selectedElement.name)}
                        className="text-gray-400 hover:text-red-500 px-1.5 py-0.5 rounded hover:bg-gray-100"
                        title="删除"
                      >
                        <i className="fas fa-trash text-xs"></i>
                      </button>
                    </div>
                  </div>

                  {/* 截图 */}
                  {selectedElement.screenshot && (
                    <div className="mb-4">
                      <div className="text-xs text-gray-500 mb-1">截图</div>
                      <img
                        src={selectedElement.screenshot}
                        alt={selectedElement.name}
                        className="max-h-48 border border-gray-200 rounded cursor-zoom-in hover:border-blue-300"
                        onClick={() => window.open(selectedElement.screenshot, '_blank')}
                      />
                    </div>
                  )}

                  {/* 定位信息 */}
                  <div className="grid grid-cols-3 gap-3 mb-4">
                    <div>
                      <div className="text-[10px] text-gray-400 mb-0.5">定位方式</div>
                      <div className="text-xs text-gray-700 font-mono bg-gray-50 px-2 py-1 rounded">
                        {selectedElement.locator_type}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-gray-400 mb-0.5">方法</div>
                      <div className="text-xs text-gray-700 font-mono bg-gray-50 px-2 py-1 rounded">
                        {selectedElement.method}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-gray-400 mb-0.5">站点</div>
                      <div className="text-xs text-gray-700 truncate bg-gray-50 px-2 py-1 rounded" title={selectedElement.hostname}>
                        {selectedElement.hostname}
                      </div>
                    </div>
                  </div>

                  {/* Locator */}
                  <div className="mb-3">
                    <div className="text-[10px] text-gray-400 mb-0.5">Locator</div>
                    <code className="block text-xs text-gray-700 bg-gray-50 px-2 py-1.5 rounded break-all font-mono">
                      {selectedElement.locator}
                    </code>
                  </div>

                  {/* CSS Selector */}
                  {selectedElement.css_selector && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-0.5">CSS Selector</div>
                      <code className="block text-xs text-gray-700 bg-gray-50 px-2 py-1.5 rounded break-all font-mono">
                        {selectedElement.css_selector}
                      </code>
                    </div>
                  )}

                  {/* 描述 */}
                  {selectedElement.description && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-0.5">描述</div>
                      <div className="text-xs text-gray-600">{selectedElement.description}</div>
                    </div>
                  )}

                  {/* 文本预览 */}
                  {selectedElement.text_preview && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-0.5">文本预览</div>
                      <div className="text-xs text-gray-600 bg-yellow-50 px-2 py-1.5 rounded border border-yellow-100">
                        {selectedElement.text_preview}
                      </div>
                    </div>
                  )}

                  {/* 页面 URL */}
                  {selectedElement.page_url && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-0.5">页面 URL</div>
                      <a
                        href={selectedElement.page_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-600 hover:underline truncate block"
                        title={selectedElement.page_url}
                      >
                        {selectedElement.page_url}
                      </a>
                    </div>
                  )}

                  {/* 候选方案 */}
                  {selectedElement.candidates && selectedElement.candidates.length > 0 && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-1">
                        候选方案 ({selectedElement.candidates.length})
                      </div>
                      <div className="space-y-1">
                        {selectedElement.candidates.map((cand, idx) => (
                          <div key={idx} className="text-xs bg-gray-50 px-2 py-1 rounded">
                            <span className="text-gray-400 mr-1">#{idx + 1}</span>
                            <span className="text-gray-600 font-mono">
                              {typeof cand === 'string' ? cand : JSON.stringify(cand)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 特征 */}
                  {selectedElement.features && Object.keys(selectedElement.features).length > 0 && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-1">特征</div>
                      <div className="grid grid-cols-2 gap-1">
                        {Object.entries(selectedElement.features).map(([k, v]) => (
                          <div key={k} className="text-xs bg-gray-50 px-2 py-1 rounded flex justify-between">
                            <span className="text-gray-400">{k}</span>
                            <span className="text-gray-600 font-mono truncate ml-2">{String(v)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 时间 */}
                  <div className="flex gap-4 text-[10px] text-gray-400 mt-4 pt-3 border-t border-gray-100">
                    {selectedElement.created_at && (
                      <span>创建: {new Date(selectedElement.created_at).toLocaleString('zh-CN')}</span>
                    )}
                    {selectedElement.updated_at && (
                      <span>更新: {new Date(selectedElement.updated_at).toLocaleString('zh-CN')}</span>
                    )}
                  </div>
                </div>
              ) : (
                <div className="text-center text-gray-400 text-sm mt-12">
                  选择左侧元素查看详情
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center">
            <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mb-3">
              <i className="fas fa-inbox text-gray-400 text-xl"></i>
            </div>
            <p className="text-gray-500 text-sm">{BOTTOM_TABS.find(t => t.key === activeTab)?.label}</p>
            <p className="text-gray-400 text-xs mt-1">暂无内容</p>
          </div>
        )}
      </div>

      {/* Toast 提示 */}
      {toast && (
        <div className={`fixed bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 rounded shadow-lg text-xs z-50 transition-opacity ${
          toast.type === 'error' ? 'bg-red-600 text-white' : 'bg-gray-800 text-white'
        }`}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}
