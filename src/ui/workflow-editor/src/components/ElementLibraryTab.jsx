import { useState, useEffect, useRef, useMemo } from 'react';
import { useWorkflow } from '../store/WorkflowContext';
import { api } from '../api';
import DataTableTab from './DataTableTab';
import CaptureToolModal from './CaptureToolModal';
import UploadImageModal from './UploadImageModal';
import ImageLightbox from './ImageLightbox';
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
  const { elements, loadElements, runLogs, runStatus, wfId, projectDir, buildElementTree, getElementChain } = useWorkflow();
  const [activeTab, setActiveTab] = useState('elements');
  const switchTab = (key) => setActiveTab(key);
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
  const [uploadModal, setUploadModal] = useState(false);
  const [lightbox, setLightbox] = useState(null); // {src, alt} 截图灯箱
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

  // 列表接口不返回 base64 截图：选中元素时按需拉详情取 screenshot（带缓存）
  const [shotCache, setShotCache] = useState({});
  useEffect(() => {
    if (projectDir || !selectedElement || selectedElement.screenshot || shotCache[selectedElement.id]) return;
    let cancelled = false;
    api.getWorkflowElementByName(wfId, selectedElement.name)
      .then((d) => {
        if (!cancelled && d && d.screenshot) {
          setShotCache((m) => ({ ...m, [selectedElement.id]: d.screenshot }));
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [selectedElement && selectedElement.id]);
  const selectedScreenshot = selectedElement
    ? (selectedElement.screenshot || shotCache[selectedElement.id] || '')
    : '';

  const elementTree = useMemo(() => buildElementTree(elements), [elements, buildElementTree]);
  const selectedChain = useMemo(() =>
    selectedElement ? getElementChain(elements, selectedElement.name) : [],
    [elements, selectedElement, getElementChain]
  );
  useEffect(() => {
    setExpandedNames(new Set(elements.map(e => e.name)));
  }, [elements]);

  const typeLabel = { web: '网页', win32: '桌面', uia: 'UIA', image: '图像' };
  const typeClass = {
    web: 'bg-accent-soft text-accent',
    win32: 'bg-purple-100 text-purple-600',
    uia: 'bg-ok-soft text-ok',
    image: 'bg-vision-soft text-vision',
  };
  const kindLabel = { plain: '普通', anchor: '锚点', child: '子元素' };
  const kindClass = {
    plain: 'bg-surface-3 text-muted',
    anchor: 'bg-accent-soft text-accent',
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
            className="absolute border-t border-border"
            style={{ left: parentGuideLeft, top: 11, width: rowPaddingLeft - parentGuideLeft }}
          />
        )}
        {isExpanded && hasChildren && (
          <div
            className="absolute border-l border-border"
            style={{ left: guideLeft, top: 24, bottom: 0 }}
          />
        )}
        <div
          onClick={() => { if (renamingId !== node.id) setSelectedElementId(node.id); }}
          style={{ paddingLeft: rowPaddingLeft }}
          className={`group relative z-10 flex items-center gap-1 py-1 pr-2 cursor-pointer ${
            selectedElementId === node.id
              ? 'bg-accent-soft'
              : 'hover:bg-surface-3'
          }`}
        >
          {hasChildren ? (
            <button
              onClick={(e) => { e.stopPropagation(); toggleExpandedName(node.name); }}
              className="w-4 h-4 flex items-center justify-center text-faint hover:text-muted shrink-0"
            >
              <i className={`fas fa-chevron-${isExpanded ? 'down' : 'right'} text-[9px]`}></i>
            </button>
          ) : (
            <span className="w-4 shrink-0"></span>
          )}
          <span className={`flex-1 min-w-0 text-xs truncate ${
            selectedElementId === node.id ? 'text-accent font-medium' : 'text-body'
          }`}>
            {node.name}
          </span>
          {isOrphan && (
            <span className="w-1.5 h-1.5 rounded-full bg-danger shrink-0" title="父元素不存在" />
          )}
          {renamingId !== node.id && !projectDir && (
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
              <button
                onClick={(e) => { e.stopPropagation(); startRename(node); }}
                className="text-faint hover:text-accent px-1"
                title="重命名"
              >
                <i className="fas fa-pen text-[9px]"></i>
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); handleDelete(node.id, node.name); }}
                className="text-faint hover:text-danger px-1"
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
      <div className="h-8 bg-surface border-t border-border flex items-center px-4 cursor-pointer hover:bg-surface-2"
           onClick={() => toggleExpanded(true)}>
        <span className="text-xs text-muted">
          <i className="fas fa-chevron-up mr-1"></i>
          元素库 ({elements.length})
        </span>
      </div>
    );
  }

  return (
    <div ref={panelRef} className="h-[220px] bg-surface border-t border-border flex flex-col shrink-0 select-none">
      {/* Tab 栏：全部保留；项目模式下 dataTable/logs/api 显示占位说明 */}
      <div className="flex items-center border-b border-border px-2">
        {BOTTOM_TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => switchTab(tab.key)}
            className={`px-3 py-2 text-xs ${activeTab === tab.key ? 'tab-active' : 'text-muted hover:text-body'}`}
          >
            <i className={`fas ${tab.icon} mr-1`}></i>
            {tab.label}
          </button>
        ))}
        <button
          onClick={() => toggleExpanded(false)}
          className="ml-auto px-2 py-2 text-xs text-faint hover:text-muted"
        >
          <i className="fas fa-chevron-down"></i>
        </button>
      </div>

      {/* 内容区 */}
      <div className="flex-1 flex overflow-hidden">
        {activeTab === 'logs' && (
          <div ref={logsRef} className="flex-1 overflow-y-auto p-2 font-mono text-xs select-text">
            {runLogs.length === 0 ? (
              <div className="text-center text-faint py-8">
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
                      log.level === 'error' ? 'bg-danger-soft text-danger' :
                      log.level === 'warn' ? 'bg-warn-soft text-warn' :
                      log.level === 'success' ? 'bg-ok-soft text-ok' :
                      'text-muted'
                    }`}>
                      <span className="text-faint shrink-0">{log.time}</span>
                      {stepNum && (
                        <span className="shrink-0 px-1.5 py-0.5 rounded bg-surface-3 text-muted text-[10px] font-mono leading-4">
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
            <div className="w-[280px] border-r border-border overflow-y-auto p-2">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs text-faint flex-1">{elements.length} 个元素</span>
              </div>
              {elements.length === 0 ? (
                <div className="text-center text-faint text-xs py-8">暂无元素</div>
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
                      className="flex items-center gap-1 text-[10px] text-faint"
                      title={`${label} 扩展${online ? '在线' : '离线'}`}
                    >
                      <span className={`w-2 h-2 rounded-full ${online ? 'bg-ok' : 'bg-surface-3'}`}></span>
                      {label} {online ? '在线' : '离线'}
                    </span>
                  );
                })}
              </div>
              {!projectDir && (
                <button
                  className="flex items-center gap-1 px-3 py-1.5 rounded text-xs transition-colors bg-vision hover:bg-vision text-white"
                  onClick={() => setUploadModal(true)}
                  title="上传截图作为图像元素（供「图像查找 / 图像点击」指令使用）"
                >
                  <i className="fas fa-upload text-[10px]"></i>
                  <span>上传图像</span>
                </button>
              )}
              {!projectDir && (
                <button
                  className="flex items-center gap-1 px-3 py-1.5 rounded text-xs transition-colors bg-accent hover:bg-accent-strong text-white"
                  onClick={handleCaptureTool}
                  title="捕获元素（统一捕获网页/桌面/UIA 元素）"
                >
                  <i className="fas fa-tools text-[10px]"></i>
                  <span>捕获元素</span>
                </button>
              )}
              </div>
              {selectedElement ? (
                <div className="max-w-2xl">
                  {/* 标题 */}
                  <div className="flex items-center gap-2 mb-2">
                    <i className="fas fa-crosshairs text-accent"></i>
                    <h3 className="text-sm font-medium text-inverse">{selectedElement.name}</h3>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${typeClass[selectedElement.element_type || 'web']}`}>
                      {typeLabel[selectedElement.element_type || 'web']}
                    </span>
                    {selectedElement.element_kind && selectedElement.element_kind !== 'plain' && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${kindClass[selectedElement.element_kind]}`}>
                        {kindLabel[selectedElement.element_kind]}
                      </span>
                    )}
                    {selectedElement.tag && (
                      <span className="px-1.5 py-0.5 bg-surface-3 rounded text-[10px] text-muted">
                        {selectedElement.tag}
                      </span>
                    )}
                    <div className="ml-auto flex items-center gap-1">
                      {!projectDir && (
                        <button
                          onClick={() => startRename(selectedElement)}
                          className="text-faint hover:text-accent px-1.5 py-0.5 rounded hover:bg-surface-3"
                          title="重命名"
                        >
                          <i className="fas fa-pen text-xs"></i>
                        </button>
                      )}
                      {!projectDir && (
                        <button
                          onClick={() => handleDelete(selectedElement.id, selectedElement.name)}
                          className="text-faint hover:text-danger px-1.5 py-0.5 rounded hover:bg-surface-3"
                          title="删除"
                        >
                          <i className="fas fa-trash text-xs"></i>
                        </button>
                      )}
                    </div>
                  </div>

                  {selectedChain.length > 1 && (
                    <div className="mb-3 text-[10px] text-muted bg-surface-2 px-2 py-1 rounded truncate">
                      {'父链: '}
                      {selectedChain.map((e, i) => (
                        <span key={e.name}>
                          {i > 0 && <span className="text-muted mx-1">/</span>}
                          <span className={e.name === selectedElement.name ? 'text-inverse font-medium' : ''}>{e.name}</span>
                        </span>
                      ))}
                    </div>
                  )}

                  {/* ─── Win32 / UIA 桌面元素 ─── */}
                  {(selectedElement.element_type === 'win32' || selectedElement.element_type === 'uia') && (() => {
                    const attr = selectedElement.attributes || {};
                    const isUia = selectedElement.element_type === 'uia';
                    const _tidx = (isUia && typeof attr.uia_target_index === 'number'
                      && attr.uia_target_index >= 0 && attr.uia_target_index < (attr.path?.length || 0))
                      ? attr.uia_target_index : (attr.path?.length || 1) - 1;
                    const target = attr.path?.[_tidx];
                    return (
                      <div className="space-y-2 mb-4">
                        {/* 截图（图像兜底参考） */}
                        {selectedScreenshot && (
                          <div className="mb-2">
                            <div className="text-xs text-muted mb-1">截图</div>
                            <div
                              className="relative inline-block group cursor-zoom-in"
                              title="点击预览大图"
                              onClick={() => setLightbox({ src: selectedScreenshot, alt: selectedElement.name })}
                            >
                              <img
                                src={selectedScreenshot}
                                alt={selectedElement.name}
                                className="max-h-40 border border-border rounded bg-surface"
                              />
                              <div className="absolute inset-0 rounded bg-black/0 group-hover:bg-accent-strong/30 flex items-center justify-center opacity-0 group-hover:opacity-100 transition">
                                <i className="fas fa-expand text-body text-xs"></i>
                              </div>
                            </div>
                          </div>
                        )}
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <div className="text-[10px] text-faint">{isUia ? '名称' : '类名'}</div>
                            <div className="text-xs text-body bg-surface-2 px-2 py-1 rounded font-mono">{isUia ? (target?.name || '-') : (target?.class_name || '-')}</div>
                          </div>
                          {isUia ? (
                            <>
                              <div>
                                <div className="text-[10px] text-faint">控件类型</div>
                                <div className="text-xs text-body bg-surface-2 px-2 py-1 rounded font-mono">{target?.control_type || '-'}</div>
                              </div>
                              <div>
                                <div className="text-[10px] text-faint">类名</div>
                                <div className="text-xs text-body bg-surface-2 px-2 py-1 rounded font-mono">{target?.class_name || '-'}</div>
                              </div>
                              <div>
                                <div className="text-[10px] text-faint">AutomationId</div>
                                <div className="text-xs text-body bg-surface-2 px-2 py-1 rounded font-mono truncate">{target?.automation_id || '(空)'}</div>
                              </div>
                            </>
                          ) : (
                            <>
                              <div>
                                <div className="text-[10px] text-faint">句柄 (HWND)</div>
                                <div className="text-xs text-body bg-surface-2 px-2 py-1 rounded font-mono">0x{(target?.hwnd || 0).toString(16).toUpperCase()}</div>
                              </div>
                              <div>
                                <div className="text-[10px] text-faint">标题</div>
                                <div className="text-xs text-body bg-surface-2 px-2 py-1 rounded truncate">{target?.title || '(空)'}</div>
                              </div>
                              <div>
                                <div className="text-[10px] text-faint">尺寸</div>
                                <div className="text-xs text-body bg-surface-2 px-2 py-1 rounded">{target?.rect?.width || '?'} x {target?.rect?.height || '?'}</div>
                              </div>
                            </>
                          )}
                        </div>

                        {/* 控件层级路径 */}
                        {attr.path && attr.path.length > 0 && (() => {
                          const tidx = (isUia && typeof attr.uia_target_index === 'number'
                            && attr.uia_target_index >= 0 && attr.uia_target_index < attr.path.length)
                            ? attr.uia_target_index : attr.path.length - 1;
                          return (
                          <div>
                            <div className="text-[10px] text-faint mb-1">控件层级 ({attr.path.length})</div>
                            <div className="space-y-0.5 max-h-48 overflow-y-auto">
                              {attr.path.map((node, idx) => (
                                <div key={idx} className={`text-xs px-2 py-1 rounded flex items-center gap-2 ${idx === tidx ? 'bg-accent-soft ring-1 ring-blue-200' : 'bg-surface-2'}`}>
                                  <span className="text-muted w-4 text-right shrink-0">{idx === 0 ? '⊞' : '└'}</span>
                                  <span className={isUia ? 'text-ok font-mono text-[10px]' : 'text-purple-600 font-mono text-[10px]'}>{isUia ? (node.control_type || node.class_name) : node.class_name}</span>
                                  {node.index != null && <span className="text-faint text-[10px] font-mono shrink-0">#{node.index}</span>}
                                  {isUia ? (node.name && <span className="text-muted truncate">"{node.name}"</span>) : (node.title && <span className="text-muted truncate">"{node.title}"</span>)}
                                  {isUia && node.automation_id && <span className="text-faint text-[10px] font-mono truncate" title={node.automation_id}>{node.automation_id}</span>}
                                  {node.enabled === false && <span className="text-warn text-[10px] shrink-0">禁用</span>}
                                  {idx === tidx && <span className="text-accent text-[10px] font-medium shrink-0">目标</span>}
                                  <span className="text-muted text-[10px] ml-auto">{node.rect?.width}x{node.rect?.height}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                          );
                        })()}
                      </div>
                    );
                  })()}

                  {/* ─── 图像元素（参考图，findImage/clickImage 用） ─── */}
                  {selectedElement.element_type === 'image' && (() => {
                    const attr = selectedElement.attributes || {};
                    const imgPath = attr.imagePath || '';
                    const imgUrl = imgPath ? `/api/images/${imgPath}` : '';
                    const sim = attr.similarity != null ? attr.similarity : 0.8;
                    const scope = attr.scope || 'screen';
                    const scopeLabel = scope === 'page' ? '浏览器页面内容' : '全屏幕';
                    const capturedAt = attr.capturedAt ? new Date(attr.capturedAt).toLocaleString() : '';
                    return (
                      <div className="space-y-3 mb-4">
                        {/* 参考图 */}
                        <div>
                          <div className="text-xs text-muted mb-1">参考图（findImage/clickImage 匹配模板）</div>
                          {imgUrl ? (
                            <div
                              className="relative inline-block group cursor-zoom-in"
                              title="点击预览大图"
                              onClick={() => setLightbox({ src: imgUrl, alt: selectedElement.name })}
                            >
                              <img
                                src={imgUrl}
                                alt={selectedElement.name}
                                className="max-h-48 border border-border rounded bg-surface"
                              />
                              <div className="absolute inset-0 rounded bg-black/0 group-hover:bg-accent-strong/30 flex items-center justify-center opacity-0 group-hover:opacity-100 transition">
                                <i className="fas fa-expand text-body text-xs"></i>
                              </div>
                            </div>
                          ) : (
                            <div className="text-xs text-faint bg-surface-2 px-2 py-3 rounded text-center">参考图文件缺失（{imgPath || '无路径'}）</div>
                          )}
                        </div>
                        {/* 匹配参数 */}
                        <div className="grid grid-cols-3 gap-3">
                          <div>
                            <div className="text-[10px] text-faint mb-0.5">相似度阈值</div>
                            <div className="text-xs text-body bg-surface-2 px-2 py-1 rounded">{sim}</div>
                          </div>
                          <div>
                            <div className="text-[10px] text-faint mb-0.5">默认匹配范围</div>
                            <div className="text-xs text-body bg-surface-2 px-2 py-1 rounded">{scopeLabel}</div>
                          </div>
                          <div>
                            <div className="text-[10px] text-faint mb-0.5">注册时间</div>
                            <div className="text-xs text-body bg-surface-2 px-2 py-1 rounded truncate">{capturedAt || '-'}</div>
                          </div>
                        </div>
                        <div className="text-[10px] text-faint leading-relaxed">
                          图像元素是全局可复用的参考图素材：任何工作流的「图像查找 / 图像点击」指令
                          都可从元素库下拉选中它（也可在运行参数中直接传文件路径）。
                        </div>
                      </div>
                    );
                  })()}

                  {/* ─── Web 元素（非 win32/uia/image） ─── */}
                  {selectedElement.element_type === 'web' && (<>

                  {/* 截图 */}
                  {selectedScreenshot && (
                    <div className="mb-4">
                      <div className="text-xs text-muted mb-1">截图</div>
                      <div
                        className="relative inline-block group cursor-zoom-in"
                        title="点击预览大图"
                        onClick={() => setLightbox({ src: selectedScreenshot, alt: selectedElement.name })}
                      >
                        <img
                          src={selectedScreenshot}
                          alt={selectedElement.name}
                          className="max-h-48 border border-border rounded bg-surface"
                        />
                        <div className="absolute inset-0 rounded bg-black/0 group-hover:bg-accent-strong/30 flex items-center justify-center opacity-0 group-hover:opacity-100 transition">
                          <i className="fas fa-expand text-body text-xs"></i>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 定位信息 */}
                  <div className="grid grid-cols-3 gap-3 mb-4">
                    <div>
                      <div className="text-[10px] text-faint mb-0.5">选择器类型</div>
                      <div className="text-xs text-body bg-surface-2 px-2 py-1 rounded truncate">
                        {(selectedElement.web_selector || '').toLowerCase().startsWith('xpath:') ? 'XPath' : 'CSS'}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-faint mb-0.5">页面 URL</div>
                      <div className="text-xs text-body truncate bg-surface-2 px-2 py-1 rounded" title={selectedElement.page_url}>
                        {selectedElement.page_url || '-'}
                      </div>
                    </div>
                  </div>

                  {/* 相对锚点 */}
                  <div className="mb-4">
                    <div className="text-[10px] text-faint mb-1">相对锚点</div>
                    <div className="flex items-center gap-2">
                      <select
                        value={selectedElement.anchor_element_name || ''}
                        onChange={(e) => updateAnchor(selectedElement, e.target.value)}
                        className="flex-1 min-w-0 px-2 py-1 bg-surface-2 border border-border rounded text-xs text-body outline-none"
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
                          className="text-faint hover:text-danger px-1.5 py-1 rounded hover:bg-surface-3"
                          title="清除锚点"
                        >
                          <i className="fas fa-times text-xs"></i>
                        </button>
                      )}
                    </div>
                    {selectedElement.relative_selector && (
                      <div className="mt-1">
                        <div className="text-[10px] text-faint mb-0.5">相对选择器</div>
                        <code className="block text-xs text-muted bg-surface-2 px-2 py-1 rounded break-all font-mono">
                          {selectedElement.relative_selector}
                        </code>
                      </div>
                    )}
                  </div>

                  {/* Web Selector */}
                  {selectedElement.web_selector && (
                    <div className="mb-3">
                      <div className="text-[10px] text-faint mb-0.5">网页选择器（扩展执行用）</div>
                      <code className="block text-xs text-body bg-surface-2 px-2 py-1.5 rounded break-all font-mono">
                        {selectedElement.web_selector}
                      </code>
                    </div>
                  )}

                  {/* Drission Selector */}
                  {selectedElement.drission_selector && (
                    <div className="mb-3">
                      <div className="text-[10px] text-faint mb-0.5">Drission 选择器（Python 导出用）</div>
                      <code className="block text-xs text-body bg-surface-2 px-2 py-1.5 rounded break-all font-mono">
                        {selectedElement.drission_selector}
                      </code>
                    </div>
                  )}

                  {/* 候选方案 */}
                  {selectedElement.css_candidates && selectedElement.css_candidates.length > 0 && (
                    <div className="mb-3">
                      <div className="text-[10px] text-faint mb-1">CSS 候选方案 ({selectedElement.css_candidates.length})</div>
                      <div className="space-y-1">
                        {selectedElement.css_candidates.map((cand, idx) => (
                          <div key={idx} className="text-xs bg-surface-2 px-2 py-1 rounded">
                            <span className="text-faint mr-1">#{idx + 1}</span>
                            <span className="text-muted font-mono">{cand.syntax || cand}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {selectedElement.xpath_candidates && selectedElement.xpath_candidates.length > 0 && (
                    <div className="mb-3">
                      <div className="text-[10px] text-faint mb-1">XPath 候选方案 ({selectedElement.xpath_candidates.length})</div>
                      <div className="space-y-1">
                        {selectedElement.xpath_candidates.map((cand, idx) => (
                          <div key={idx} className="text-xs bg-surface-2 px-2 py-1 rounded">
                            <span className="text-faint mr-1">#{idx + 1}</span>
                            <span className="text-muted font-mono">{cand.syntax || cand}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {selectedElement.drission_candidates && selectedElement.drission_candidates.length > 0 && (
                    <div className="mb-3">
                      <div className="text-[10px] text-faint mb-1">Drission 候选方案 ({selectedElement.drission_candidates.length})</div>
                      <div className="space-y-1">
                        {selectedElement.drission_candidates.map((cand, idx) => (
                          <div key={idx} className="text-xs bg-surface-2 px-2 py-1 rounded">
                            <span className="text-faint mr-1">#{idx + 1}</span>
                            <span className="text-muted font-mono">{cand.syntax || cand}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* DOM Path */}
                  {selectedElement.dom_path && selectedElement.dom_path.length > 0 && (
                    <div className="mb-3">
                      <div className="text-[10px] text-faint mb-1">DOM 层级 ({selectedElement.dom_path.length})</div>
                      <div className="space-y-0.5">
                        {selectedElement.dom_path.map((node, idx) => (
                          <div key={idx} className="text-xs bg-surface-2 px-2 py-1 rounded font-mono">
                            {'  '.repeat(idx)}&lt;{node.tag || 'div'}{node.id ? ` #${node.id}` : ''}{node.classes?.length ? ` .${node.classes.join('.')}` : ''} /&gt;
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  </>)}

                  {/* 时间 */}
                  <div className="flex gap-4 text-[10px] text-faint mt-4 pt-3 border-t border-border">
                    {selectedElement.created_at && (
                      <span>创建: {new Date(selectedElement.created_at).toLocaleString('zh-CN')}</span>
                    )}
                    {selectedElement.updated_at && (
                      <span>更新: {new Date(selectedElement.updated_at).toLocaleString('zh-CN')}</span>
                    )}
                  </div>
                </div>
              ) : (
                <div className="text-center text-faint text-sm mt-12">
                  选择左侧元素查看详情
                </div>
              )}
            </div>
          </>
        )}
        {activeTab !== 'logs' && activeTab !== 'elements' && activeTab !== 'dataTable' && activeTab !== 'params' && activeTab !== 'api' && (
          <div className="flex-1 flex flex-col items-center justify-center text-center">
            <div className="w-12 h-12 bg-surface-3 rounded-full flex items-center justify-center mb-3">
              <i className="fas fa-inbox text-faint text-xl"></i>
            </div>
            <p className="text-muted text-sm">{BOTTOM_TABS.find(t => t.key === activeTab)?.label}</p>
            <p className="text-faint text-xs mt-1">暂无内容</p>
          </div>
        )}

        {activeTab === 'params' && (
          <WorkflowParametersPanel variant="bottom" />
        )}

        {/* 项目模式占位：数据表格/运行日志/API 设置依赖全局 DB，目录模式后续接入 */}
        {projectDir && (activeTab === 'api' || activeTab === 'dataTable' || activeTab === 'logs') && (
          <div className="flex-1 flex flex-col items-center justify-center text-center">
            <div className="w-12 h-12 bg-surface-3 rounded-full flex items-center justify-center mb-3">
              <i className="fas fa-box-open text-faint text-xl"></i>
            </div>
            <p className="text-muted text-sm">{BOTTOM_TABS.find(t => t.key === activeTab)?.label}</p>
            <p className="text-faint text-xs mt-1">目录模式暂不支持（数据表格/运行日志/API 设置将随流程目录化接入）</p>
          </div>
        )}

        {activeTab === 'api' && !projectDir && (
          <ApiSettingsPanel />
        )}

        {/* DataTableTab 始终挂载，通过 hidden 控制显隐，确保运行时事件不丢失（项目模式不可用） */}
        {!projectDir && (
          <div className={`flex-1 flex flex-col ${activeTab === 'dataTable' ? '' : 'hidden'}`}>
            <DataTableTab wfId={wfId} />
          </div>
        )}
      </div>

      {/* Toast 提示 */}
      {toast && (
        <div className={`fixed bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 rounded shadow-lg text-xs z-50 transition-opacity ${
          toast.type === 'error' ? 'bg-danger-solid text-inverse' : 'bg-surface-3 text-inverse'
        }`}>
          {toast.msg}
        </div>
      )}

      {/* 重命名弹窗 */}
      {showRenameModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="bg-surface rounded-lg shadow-xl p-6 w-96" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-medium text-inverse mb-4">重命名元素</h3>
            <input
              autoFocus
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') confirmRename(); if (e.key === 'Escape') cancelRename(); }}
              className="w-full px-3 py-2 border border-border-strong rounded text-sm outline-none focus:border-accent"
              placeholder="输入新名称"
            />
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={cancelRename} className="px-4 py-1.5 text-xs text-muted hover:bg-surface-3 rounded border border-border">
                取消
              </button>
              <button onClick={confirmRename} className="px-4 py-1.5 text-xs text-white bg-accent hover:bg-accent-strong rounded">
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

    {/* 图像元素上传（截图 → findImage/clickImage 参考图） */}
    {uploadModal && (
      <UploadImageModal
        wfId={wfId}
        onClose={() => setUploadModal(false)}
        onSaved={loadElements}
      />
    )}

    {/* 截图灯箱 */}
    {lightbox && (
      <ImageLightbox src={lightbox.src} alt={lightbox.alt} onClose={() => setLightbox(null)} />
    )}
    </div>
  );
}
