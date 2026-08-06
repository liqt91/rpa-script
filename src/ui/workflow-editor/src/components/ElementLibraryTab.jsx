import { useState, useEffect, useRef, useMemo } from 'react';
import { useWorkflow } from '../store/WorkflowContext';
import { api } from '../api';
import DataTableTab from './DataTableTab';
import CaptureToolModal from './CaptureToolModal';
import WorkflowParametersPanel from './WorkflowParametersPanel';
import ApiSettingsPanel from './ApiSettingsPanel';

const BOTTOM_TABS = [
  { key: 'elements', label: '元素库', icon: 'fa-crosshairs' },
  { key: 'dataTable', label: '数据表格', icon: 'fa-table' },
  { key: 'logs', label: '运行日志', icon: 'fa-terminal' },
  { key: 'params', label: '流程参数', icon: 'fa-sliders-h' },
  { key: 'api', label: 'API 设置', icon: 'fa-plug' },
];

export default function ElementLibraryTab() {
  const { elements, loadElements, runLogs, runStatus, wfId, buildElementTree, getElementChain } = useWorkflow();
  const [activeTab, setActiveTab] = useState('elements');
  const [expanded, setExpanded] = useState(() => {
    try { return localStorage.getItem('wf_editor_bottom_expanded') !== 'false'; }
    catch { return true; }
  });
  const [selectedElementId, setSelectedElementId] = useState(null);
  const [expandedNames, setExpandedNames] = useState(new Set());
  const [extBrowsers, setExtBrowsers] = useState({});  // {chrome: count, edge: count}
  const [capturing, setCapturing] = useState(false);
  const [toast, setToast] = useState(null);
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const renameRef = useRef(null);
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [captureModal, setCaptureModal] = useState(false);
  const logsRef = useRef(null);
  const panelRef = useRef(null);

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

  const elementTree = useMemo(() => buildElementTree(elements), [elements, buildElementTree]);
  const selectedChain = useMemo(() =>
    selectedElement ? getElementChain(elements, selectedElement.name) : [],
    [elements, selectedElement, getElementChain]
  );
  useEffect(() => {
    setExpandedNames(new Set(elements.map(e => e.name)));
  }, [elements]);

  const typeLabel = { web: '网页', win32: '桌面', uia: 'UIA' };
  const typeClass = {
    web: 'bg-blue-100 text-blue-600',
    win32: 'bg-purple-100 text-purple-600',
    uia: 'bg-green-100 text-green-600',
  };
  const kindLabel = { plain: '普通', anchor: '锚点', child: '子元素' };
  const kindClass = {
    plain: 'bg-gray-100 text-gray-500',
    anchor: 'bg-blue-100 text-blue-600',
    child: 'bg-orange-100 text-orange-600',
  };

  function toggleExpandedName(name) {
    const next = new Set(expandedNames);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setExpandedNames(next);
  }

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

  // 轮询扩展在线状态（按浏览器细分）
  useEffect(() => {
    let timer = null;
    const checkStatus = async () => {
      try {
        const data = await api.getExtensionStatus();
        const browsers = {};
        (data.browsers || []).forEach(b => { browsers[b.browser] = b.count; });
        setExtBrowsers(browsers);
      } catch {
        setExtBrowsers({});
      }
    };
    checkStatus();
    timer = setInterval(checkStatus, 3000);
    return () => clearInterval(timer);
  }, []);

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
  // renamingIdRef 避免重命名时刷新导致失焦
  const renamingIdRef = useRef(null);
  useEffect(() => { renamingIdRef.current = renamingId; }, [renamingId]);
  useEffect(() => {
    if (activeTab !== 'elements') return;
    const tick = () => {
      if (!document.hidden && !renamingIdRef.current) loadElements();
    };
    tick();
    const timer = setInterval(tick, 5000);
    return () => clearInterval(timer);
  }, [activeTab]);

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
    setRenameValue(el.name);
    setShowRenameModal(true);
  };

  const confirmRename = async () => {
    const name = renameValue.trim();
    const id = renamingId;
    if (!name || !id) { setShowRenameModal(false); return; }
    try {
      const el = elements.find(e => e.id === id);
      if (!el) { setShowRenameModal(false); return; }
      await api.updateWorkflowElement(wfId, id, { ...el, name });
      showToast('重命名成功');
      setShowRenameModal(false);
      await refresh();
    } catch (e) {
      showToast('重命名失败: ' + e.message, 'error');
    }
  };

  const cancelRename = () => setShowRenameModal(false);

  const handleCaptureTool = () => {
    setCaptureModal(true);
  };

  const updateAnchor = async (el, anchorName) => {
    const payload = { ...el, anchor_element_name: anchorName || null };
    if (anchorName) {
      const anchorEl = elements.find(e => e.name === anchorName);
      payload.anchor_selector = anchorEl?.web_selector || '';
      payload.anchor_mode = 'manual';
    } else {
      payload.anchor_selector = '';
      payload.relative_selector = '';
      payload.anchor_mode = 'none';
    }
    try {
      await api.updateWorkflowElement(wfId, el.id, payload);
      showToast(anchorName ? `已设置相对锚点: ${anchorName}` : '已清除相对锚点');
      await refresh();
    } catch (e) {
      showToast('更新锚点失败: ' + e.message, 'error');
    }
  };

  function ElementTreeNode({ node, depth = 0, parentGuideLeft = null }) {
    const hasChildren = (node.children || []).length > 0;
    const isExpanded = expandedNames.has(node.name);
    const isOrphan = node.isOrphan;
    const rowPaddingLeft = 6 + depth * 16;
    const guideLeft = rowPaddingLeft + 8;
    return (
      <div className="relative">
        {parentGuideLeft !== null && (
          <div
            className="absolute border-t border-gray-200"
            style={{ left: parentGuideLeft, top: 11, width: rowPaddingLeft - parentGuideLeft }}
          />
        )}
        {isExpanded && hasChildren && (
          <div
            className="absolute border-l border-gray-200"
            style={{ left: guideLeft, top: 24, bottom: 0 }}
          />
        )}
        <div
          onClick={() => { if (renamingId !== node.id) setSelectedElementId(node.id); }}
          style={{ paddingLeft: rowPaddingLeft }}
          className={`group relative z-10 flex items-center gap-1 py-1 pr-2 cursor-pointer ${
            selectedElementId === node.id
              ? 'bg-blue-50'
              : 'hover:bg-gray-100'
          }`}
        >
          {hasChildren ? (
            <button
              onClick={(e) => { e.stopPropagation(); toggleExpandedName(node.name); }}
              className="w-4 h-4 flex items-center justify-center text-gray-400 hover:text-gray-600 shrink-0"
            >
              <i className={`fas fa-chevron-${isExpanded ? 'down' : 'right'} text-[9px]`}></i>
            </button>
          ) : (
            <span className="w-4 shrink-0"></span>
          )}
          <span className={`flex-1 min-w-0 text-xs truncate ${
            selectedElementId === node.id ? 'text-blue-700 font-medium' : 'text-gray-700'
          }`}>
            {node.name}
          </span>
          {isOrphan && (
            <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" title="父元素不存在" />
          )}
          {renamingId !== node.id && (
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
              <button
                onClick={(e) => { e.stopPropagation(); startRename(node); }}
                className="text-gray-400 hover:text-blue-500 px-1"
                title="重命名"
              >
                <i className="fas fa-pen text-[9px]"></i>
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); handleDelete(node.id, node.name); }}
                className="text-gray-400 hover:text-red-500 px-1"
                title="删除"
              >
                <i className="fas fa-trash text-[9px]"></i>
              </button>
            </div>
          )}
        </div>
        {isExpanded && hasChildren && (
          <div>
            {node.children.map((child) => (
              <ElementTreeNode key={child.id} node={child} depth={depth + 1} parentGuideLeft={guideLeft} />
            ))}
          </div>
        )}
      </div>
    );
  }

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
                      log.level === 'warn' ? 'bg-amber-50 text-amber-700' :
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
                <span className="text-xs text-gray-400 flex-1">{elements.length} 个元素</span>
              </div>
              {elements.length === 0 ? (
                <div className="text-center text-gray-400 text-xs py-8">暂无元素</div>
              ) : (
                <div>
                  {elementTree.map((root) => (
                    <ElementTreeNode key={root.id} node={root} depth={0} />
                  ))}
                </div>
              )}
            </div>
            {/* 右侧详情区 */}
            <div className="flex-1 overflow-y-auto p-4">
              <div className="flex items-center justify-end mb-4 gap-2">
              <div className="flex items-center gap-1.5 mr-1">
                {['chrome', 'edge'].map(b => {
                  const online = !!extBrowsers[b];
                  const label = b === 'edge' ? 'Edge' : 'Chrome';
                  return (
                    <span
                      key={b}
                      className="flex items-center gap-1 text-[10px] text-gray-400"
                      title={`${label} 扩展${online ? '在线' : '离线'}`}
                    >
                      <span className={`w-2 h-2 rounded-full ${online ? 'bg-green-500' : 'bg-gray-300'}`}></span>
                      {label} {online ? '在线' : '离线'}
                    </span>
                  );
                })}
              </div>
              <button
                className="flex items-center gap-1 px-3 py-1.5 rounded text-xs transition-colors bg-blue-500 hover:bg-blue-600 text-white"
                onClick={handleCaptureTool}
                title="捕获元素（统一捕获网页/桌面/UIA 元素）"
              >
                <i className="fas fa-tools text-[10px]"></i>
                <span>捕获元素</span>
              </button>
              </div>
              {selectedElement ? (
                <div className="max-w-2xl">
                  {/* 标题 */}
                  <div className="flex items-center gap-2 mb-2">
                    <i className="fas fa-crosshairs text-blue-500"></i>
                    <h3 className="text-sm font-medium text-gray-800">{selectedElement.name}</h3>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${typeClass[selectedElement.element_type || 'web']}`}>
                      {typeLabel[selectedElement.element_type || 'web']}
                    </span>
                    {selectedElement.element_kind && selectedElement.element_kind !== 'plain' && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${kindClass[selectedElement.element_kind]}`}>
                        {kindLabel[selectedElement.element_kind]}
                      </span>
                    )}
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

                  {selectedChain.length > 1 && (
                    <div className="mb-3 text-[10px] text-gray-500 bg-gray-50 px-2 py-1 rounded truncate">
                      {'父链: '}
                      {selectedChain.map((e, i) => (
                        <span key={e.name}>
                          {i > 0 && <span className="text-gray-300 mx-1">/</span>}
                          <span className={e.name === selectedElement.name ? 'text-gray-800 font-medium' : ''}>{e.name}</span>
                        </span>
                      ))}
                    </div>
                  )}

                  {/* ─── Win32 / UIA 桌面元素 ─── */}
                  {(selectedElement.element_type === 'win32' || selectedElement.element_type === 'uia') && (() => {
                    const attr = selectedElement.attributes || {};
                    const target = attr.path?.[attr.path.length - 1];
                    const isUia = selectedElement.element_type === 'uia';
                    return (
                      <div className="space-y-2 mb-4">
                        {/* 截图（图像兜底参考） */}
                        {selectedElement.screenshot && (
                          <div className="mb-2">
                            <div className="text-xs text-gray-500 mb-1">截图</div>
                            <img
                              src={selectedElement.screenshot}
                              alt={selectedElement.name}
                              className="max-h-40 border border-gray-200 rounded cursor-zoom-in hover:border-blue-300"
                              onClick={() => window.open(selectedElement.screenshot, '_blank')}
                            />
                          </div>
                        )}
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <div className="text-[10px] text-gray-400">{isUia ? '名称' : '类名'}</div>
                            <div className="text-xs text-gray-700 bg-gray-50 px-2 py-1 rounded font-mono">{isUia ? (target?.name || '-') : (target?.class_name || '-')}</div>
                          </div>
                          {isUia ? (
                            <>
                              <div>
                                <div className="text-[10px] text-gray-400">控件类型</div>
                                <div className="text-xs text-gray-700 bg-gray-50 px-2 py-1 rounded font-mono">{target?.control_type || '-'}</div>
                              </div>
                              <div>
                                <div className="text-[10px] text-gray-400">类名</div>
                                <div className="text-xs text-gray-700 bg-gray-50 px-2 py-1 rounded font-mono">{target?.class_name || '-'}</div>
                              </div>
                              <div>
                                <div className="text-[10px] text-gray-400">AutomationId</div>
                                <div className="text-xs text-gray-700 bg-gray-50 px-2 py-1 rounded font-mono truncate">{target?.automation_id || '(空)'}</div>
                              </div>
                            </>
                          ) : (
                            <>
                              <div>
                                <div className="text-[10px] text-gray-400">句柄 (HWND)</div>
                                <div className="text-xs text-gray-700 bg-gray-50 px-2 py-1 rounded font-mono">0x{(target?.hwnd || 0).toString(16).toUpperCase()}</div>
                              </div>
                              <div>
                                <div className="text-[10px] text-gray-400">标题</div>
                                <div className="text-xs text-gray-700 bg-gray-50 px-2 py-1 rounded truncate">{target?.title || '(空)'}</div>
                              </div>
                              <div>
                                <div className="text-[10px] text-gray-400">尺寸</div>
                                <div className="text-xs text-gray-700 bg-gray-50 px-2 py-1 rounded">{target?.rect?.width || '?'} x {target?.rect?.height || '?'}</div>
                              </div>
                            </>
                          )}
                        </div>

                        {/* 控件层级路径 */}
                        {attr.path && attr.path.length > 0 && (
                          <div>
                            <div className="text-[10px] text-gray-400 mb-1">控件层级 ({attr.path.length})</div>
                            <div className="space-y-0.5 max-h-48 overflow-y-auto">
                              {attr.path.map((node, idx) => (
                                <div key={idx} className="text-xs bg-gray-50 px-2 py-1 rounded flex items-center gap-2">
                                  <span className="text-gray-300 w-4 text-right shrink-0">{idx === 0 ? '⊞' : '└'}</span>
                                  <span className={isUia ? 'text-green-600 font-mono text-[10px]' : 'text-purple-600 font-mono text-[10px]'}>{isUia ? (node.control_type || node.class_name) : node.class_name}</span>
                                  {isUia ? (node.name && <span className="text-gray-500 truncate">"{node.name}"</span>) : (node.title && <span className="text-gray-500 truncate">"{node.title}"</span>)}
                                  <span className="text-gray-300 text-[10px] ml-auto">{node.rect?.width}x{node.rect?.height}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })()}

                  {/* ─── Web 元素（非 win32/uia） ─── */}
                  {selectedElement.element_type !== 'win32' && selectedElement.element_type !== 'uia' && (<>

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
                      <div className="text-[10px] text-gray-400 mb-0.5">选择器类型</div>
                      <div className="text-xs text-gray-700 bg-gray-50 px-2 py-1 rounded truncate">
                        {(selectedElement.web_selector || '').toLowerCase().startsWith('xpath:') ? 'XPath' : 'CSS'}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-gray-400 mb-0.5">页面 URL</div>
                      <div className="text-xs text-gray-700 truncate bg-gray-50 px-2 py-1 rounded" title={selectedElement.page_url}>
                        {selectedElement.page_url || '-'}
                      </div>
                    </div>
                  </div>

                  {/* 相对锚点 */}
                  <div className="mb-4">
                    <div className="text-[10px] text-gray-400 mb-1">相对锚点</div>
                    <div className="flex items-center gap-2">
                      <select
                        value={selectedElement.anchor_element_name || ''}
                        onChange={(e) => updateAnchor(selectedElement, e.target.value)}
                        className="flex-1 min-w-0 px-2 py-1 bg-gray-50 border border-gray-200 rounded text-xs text-gray-700 outline-none"
                      >
                        <option value="">不使用相对解析</option>
                        {elements
                          .filter((e) => e.id !== selectedElement.id && e.name !== selectedElement.name)
                          .map((e) => (
                            <option key={e.id} value={e.name}>
                              {e.name}
                            </option>
                          ))}
                      </select>
                      {selectedElement.anchor_element_name && (
                        <button
                          onClick={() => updateAnchor(selectedElement, '')}
                          className="text-gray-400 hover:text-red-500 px-1.5 py-1 rounded hover:bg-gray-100"
                          title="清除锚点"
                        >
                          <i className="fas fa-times text-xs"></i>
                        </button>
                      )}
                    </div>
                    {selectedElement.relative_selector && (
                      <div className="mt-1">
                        <div className="text-[10px] text-gray-400 mb-0.5">相对选择器</div>
                        <code className="block text-xs text-gray-600 bg-gray-50 px-2 py-1 rounded break-all font-mono">
                          {selectedElement.relative_selector}
                        </code>
                      </div>
                    )}
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
                  </>)}

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
        {activeTab !== 'logs' && activeTab !== 'elements' && activeTab !== 'dataTable' && activeTab !== 'params' && activeTab !== 'api' && (
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

        {activeTab === 'api' && (
          <ApiSettingsPanel />
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

      {/* 重命名弹窗 */}
      {showRenameModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="bg-white rounded-lg shadow-xl p-6 w-96" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-medium text-gray-800 mb-4">重命名元素</h3>
            <input
              autoFocus
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') confirmRename(); if (e.key === 'Escape') cancelRename(); }}
              className="w-full px-3 py-2 border border-gray-300 rounded text-sm outline-none focus:border-blue-400"
              placeholder="输入新名称"
            />
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={cancelRename} className="px-4 py-1.5 text-xs text-gray-600 hover:bg-gray-100 rounded border border-gray-200">
                取消
              </button>
              <button onClick={confirmRename} className="px-4 py-1.5 text-xs text-white bg-blue-500 hover:bg-blue-600 rounded">
                确认
              </button>
            </div>
          </div>
        </div>
      )}

    {/* 元素捕获工具 — 原生模态框 */}
    {captureModal && (
      <CaptureToolModal
        wfId={wfId}
        onClose={() => setCaptureModal(false)}
        onSaved={loadElements}
      />
    )}
    </div>
  );
}
