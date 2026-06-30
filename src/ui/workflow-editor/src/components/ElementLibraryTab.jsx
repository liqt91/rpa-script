import { useState, useEffect, useRef, useMemo } from 'react';
import { useWorkflow } from '../store/WorkflowContext';
import { api } from '../api';
import DataTableTab from './DataTableTab';
import WorkflowParametersPanel from './WorkflowParametersPanel';

const BOTTOM_TABS = [
  { key: 'elements', label: '元素库', icon: 'fa-crosshairs' },
  { key: 'images', label: '图像库', icon: 'fa-image' },
  { key: 'dataTable', label: '数据表格', icon: 'fa-table' },
  { key: 'logs', label: '运行日志', icon: 'fa-terminal' },
  { key: 'params', label: '流程参数', icon: 'fa-sliders-h' },
];

export default function ElementLibraryTab() {
  const { elements, loadElements, runLogs, runStatus, wfId } = useWorkflow();
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
  const [showGuide, setShowGuide] = useState(false);
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
    console.log('[ElementLibraryTab] runLogs updated, count=', runLogs.length, 'last=', runLogs[runLogs.length - 1]);
  }, [runLogs]);

  useEffect(() => {
    if (!logsRef.current || runLogs.length === 0) return;
    const el = logsRef.current;
    const isAtBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
    if (isAtBottom) {
      el.scrollTop = el.scrollHeight;
    }
  }, [runLogs]);

  const selectedElement = elements.find(e => e.id === selectedElementId) || null;

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

  const filtered = elements;

  const showToast = (msg, type = 'info') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleDelete = async (id, name) => {
    if (!window.confirm(`确认删除元素 "${name}"？`)) return;
    try {
      await api.deleteWorkflowElement(wfId, id);
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
      const el = elements.find(e => e.id === id);
      if (!el) return;
      await api.updateWorkflowElement(wfId, id, { ...el, name });
      showToast('重命名成功');
      setRenamingId(null);
      await refresh();
    } catch (e) {
      showToast('重命名失败: ' + e.message, 'error');
      setRenamingId(null);
    }
  };

  const cancelRename = () => setRenamingId(null);

  const handleCapture = () => {
    setShowGuide(true);
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
        {activeTab === 'logs' && (
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
        )}
        {activeTab === 'elements' && (
          <>
            {/* 左侧元素树 */}
            <div className="w-[280px] border-r border-[#e8e8e8] overflow-y-auto p-2">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs text-gray-400 flex-1">{filtered.length} 个元素</span>
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
                            <div className="text-[10px] text-gray-400 truncate">{el.web_selector || el.drission_selector || '-'}</div>
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
                      <span className="text-[10px] text-gray-400">{el.target_mode || 'single'}</span>
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
                  className="flex items-center gap-1 px-3 py-1.5 rounded text-xs transition-colors bg-orange-500 hover:bg-orange-600 text-white"
                  onClick={handleCapture}
                  title="查看捕获指南"
                >
                  <i className="fas fa-plus text-[10px]"></i>
                  <span>捕获新元素</span>
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
                      <div className="text-[10px] text-gray-400 mb-0.5">目标模式</div>
                      <select
                        value={selectedElement.target_mode || 'single'}
                        onChange={async (e) => {
                          const val = e.target.value;
                          try {
                            await api.updateWorkflowElement(wfId, selectedElement.id, { ...selectedElement, target_mode: val });
                            await refresh();
                          } catch (err) {
                            showToast('更新失败: ' + err.message, 'error');
                          }
                        }}
                        className="w-full text-xs text-gray-700 bg-white border border-gray-200 rounded px-2 py-1 outline-none focus:border-blue-400"
                      >
                        <option value="single">single</option>
                        <option value="list">list</option>
                      </select>
                    </div>
                    <div>
                      <div className="text-[10px] text-gray-400 mb-0.5">页面 URL</div>
                      <div className="text-xs text-gray-700 truncate bg-gray-50 px-2 py-1 rounded" title={selectedElement.page_url}>
                        {selectedElement.page_url || '-'}
                      </div>
                    </div>
                  </div>

                  {/* Web Selector */}
                  {selectedElement.web_selector && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-0.5">网页选择器（扩展执行用）</div>
                      <code className="block text-xs text-gray-700 bg-gray-50 px-2 py-1.5 rounded break-all font-mono">
                        {selectedElement.web_selector}
                      </code>
                    </div>
                  )}

                  {/* Drission Selector */}
                  {selectedElement.drission_selector && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-0.5">Drission 选择器（Python 导出用）</div>
                      <code className="block text-xs text-gray-700 bg-gray-50 px-2 py-1.5 rounded break-all font-mono">
                        {selectedElement.drission_selector}
                      </code>
                    </div>
                  )}

                  {/* 候选方案 */}
                  {selectedElement.css_candidates && selectedElement.css_candidates.length > 0 && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-1">CSS 候选方案 ({selectedElement.css_candidates.length})</div>
                      <div className="space-y-1">
                        {selectedElement.css_candidates.map((cand, idx) => (
                          <div key={idx} className="text-xs bg-gray-50 px-2 py-1 rounded">
                            <span className="text-gray-400 mr-1">#{idx + 1}</span>
                            <span className="text-gray-600 font-mono">{cand.syntax || cand}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {selectedElement.xpath_candidates && selectedElement.xpath_candidates.length > 0 && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-1">XPath 候选方案 ({selectedElement.xpath_candidates.length})</div>
                      <div className="space-y-1">
                        {selectedElement.xpath_candidates.map((cand, idx) => (
                          <div key={idx} className="text-xs bg-gray-50 px-2 py-1 rounded">
                            <span className="text-gray-400 mr-1">#{idx + 1}</span>
                            <span className="text-gray-600 font-mono">{cand.syntax || cand}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {selectedElement.drission_candidates && selectedElement.drission_candidates.length > 0 && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-1">Drission 候选方案 ({selectedElement.drission_candidates.length})</div>
                      <div className="space-y-1">
                        {selectedElement.drission_candidates.map((cand, idx) => (
                          <div key={idx} className="text-xs bg-gray-50 px-2 py-1 rounded">
                            <span className="text-gray-400 mr-1">#{idx + 1}</span>
                            <span className="text-gray-600 font-mono">{cand.syntax || cand}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* DOM Path */}
                  {selectedElement.dom_path && selectedElement.dom_path.length > 0 && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-1">DOM 层级 ({selectedElement.dom_path.length})</div>
                      <div className="space-y-0.5">
                        {selectedElement.dom_path.map((node, idx) => (
                          <div key={idx} className="text-xs bg-gray-50 px-2 py-1 rounded font-mono">
                            {'  '.repeat(idx)}&lt;{node.tag || 'div'}{node.id ? ` #${node.id}` : ''}{node.classes?.length ? ` .${node.classes.join('.')}` : ''} /&gt;
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
        )}
        {activeTab !== 'logs' && activeTab !== 'elements' && activeTab !== 'dataTable' && (
          <div className="flex-1 flex flex-col items-center justify-center text-center">
            <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mb-3">
              <i className="fas fa-inbox text-gray-400 text-xl"></i>
            </div>
            <p className="text-gray-500 text-sm">{BOTTOM_TABS.find(t => t.key === activeTab)?.label}</p>
            <p className="text-gray-400 text-xs mt-1">暂无内容</p>
          </div>
        )}

        {activeTab === 'params' && (
          <WorkflowParametersPanel variant="bottom" />
        )}

        {/* DataTableTab 始终挂载，通过 hidden 控制显隐，确保运行时事件不丢失 */}
        <div className={`flex-1 flex flex-col ${activeTab === 'dataTable' ? '' : 'hidden'}`}>
          <DataTableTab wfId={wfId} />
        </div>
      </div>

      {/* Toast 提示 */}
      {toast && (
        <div className={`fixed bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 rounded shadow-lg text-xs z-50 transition-opacity ${
          toast.type === 'error' ? 'bg-red-600 text-white' : 'bg-gray-800 text-white'
        }`}>
          {toast.msg}
        </div>
      )}

      {/* 捕获指南弹窗 */}
      {showGuide && (
        <div
          className="fixed inset-0 bg-black/30 flex items-center justify-center z-50"
          onClick={() => setShowGuide(false)}
        >
          <div
            className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-gray-800">
                <i className="fas fa-info-circle text-orange-500 mr-1.5"></i>
                捕获新元素
              </h3>
              <button
                onClick={() => setShowGuide(false)}
                className="text-gray-400 hover:text-gray-600 w-6 h-6 flex items-center justify-center"
              >
                <i className="fas fa-times text-xs"></i>
              </button>
            </div>
            <div className="space-y-3 text-xs text-gray-600">
              <p className="text-orange-600 font-medium bg-orange-50 px-3 py-2 rounded">
                请在已安装插件的浏览器中完成元素捕获。
              </p>

              <div>
                <div className="font-medium text-gray-700 mb-1.5 flex items-center gap-1">
                  <i className="fas fa-list-ol text-[10px] text-gray-400"></i>
                  捕获步骤
                </div>
                <ol className="list-decimal pl-4 space-y-1 text-gray-600">
                  <li>打开需要捕获元素的网页</li>
                  <li>点击浏览器工具栏中的 RPA 扩展图标</li>
                  <li>点击"捕获元素"按钮进入捕获模式</li>
                  <li>将鼠标悬停在目标元素上，点击左键确认捕获</li>
                  <li>输入元素名称后保存，元素将自动同步到编辑器</li>
                </ol>
              </div>

              <div>
                <div className="font-medium text-gray-700 mb-1.5 flex items-center gap-1">
                  <i className="fas fa-puzzle-piece text-[10px] text-gray-400"></i>
                  插件安装方式
                </div>
                <ol className="list-decimal pl-4 space-y-1 text-gray-600">
                  <li>打开 Chrome/Edge 的扩展管理页面（<code className="bg-gray-100 px-1 rounded text-[10px]">chrome://extensions</code> 或 <code className="bg-gray-100 px-1 rounded text-[10px]">edge://extensions</code>）</li>
                  <li>开启右上角"开发者模式"</li>
                  <li>点击"加载已解压的扩展程序"</li>
                  <li>选择项目目录下的 <code className="bg-gray-100 px-1 rounded text-[10px]">extension/</code> 文件夹</li>
                  <li>扩展图标将出现在浏览器工具栏中，点击即可使用</li>
                </ol>
              </div>
            </div>
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setShowGuide(false)}
                className="px-4 py-1.5 bg-blue-500 hover:bg-blue-600 text-white text-xs rounded transition-colors"
              >
                知道了
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
