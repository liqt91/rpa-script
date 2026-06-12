import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useWorkflow, deriveParentId, computeParents, matchBrackets, getUnclosedContainers } from '../store/WorkflowContext';

export default function NodeList() {
  const {
    treeNodes,
    selectedNodeId,
    selectedNodeIds,
    dispatch,
    deleteNode,
    deleteNodes,
    updateNode,
    nodes,
    NODE_TYPE_MAP,
    saveNode,
    replaceNodes,
    wfId,
    runStatus,
    runningStepId,
    stepErrors,
    elements,
  } = useWorkflow();

  const [dragOver, setDragOver] = useState(false);
  const [insertIndex, setInsertIndex] = useState(null);
  const [draggingIds, setDraggingIds] = useState(null);

  const hasMultiSelection = selectedNodeIds.size > 1;

  // ─── 拖拽时自动滚动 ──────────────────────────────────────────
  const autoScrollRef = useRef({ active: false, direction: 0 });

  const stopAutoScroll = useCallback(() => {
    autoScrollRef.current.active = false;
    autoScrollRef.current.direction = 0;
  }, []);

  const startAutoScroll = useCallback(() => {
    if (autoScrollRef.current.active) return;
    autoScrollRef.current.active = true;
    const tick = () => {
      if (!autoScrollRef.current.active) return;
      const container = document.querySelector('.node-list-container');
      if (container && autoScrollRef.current.direction !== 0) {
        container.scrollTop += autoScrollRef.current.direction * 8;
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, []);

  // 全局 dragend 后备
  useEffect(() => {
    const onDragEnd = () => {
      if (dragOver || draggingIds) {
        setDragOver(false);
        setInsertIndex(null);
        setDraggingIds(null);
        stopAutoScroll();
      }
    };
    window.addEventListener('dragend', onDragEnd);
    return () => window.removeEventListener('dragend', onDragEnd);
  }, [dragOver, draggingIds, stopAutoScroll]);

  // ─── 选区合法性 ──────────────────────────────────────────────

  const selectionValidation = useMemo(() => {
    if (selectedNodeIds.size <= 1) return { valid: true };
    const ids = Array.from(selectedNodeIds);
    const indices = ids.map(id => treeNodes.findIndex(n => n.id === id)).sort((a, b) => a - b);
    for (let i = 1; i < indices.length; i++) {
      if (indices[i] !== indices[i - 1] + 1) {
        return { valid: false, reason: '选区不连续' };
      }
    }
    // 容器完整性：选区包含容器时必须包含对应的结束标记
    const bracketMatch = matchBrackets(treeNodes, NODE_TYPE_MAP);
    const containerClose = new Map();
    for (const [sId, cId] of bracketMatch) containerClose.set(cId, sId);
    for (let i = indices[0]; i <= indices[indices.length - 1]; i++) {
      const node = treeNodes[i];
      const info = NODE_TYPE_MAP[node.type];
      if (info?.isContainer) {
        const closeId = containerClose.get(node.id);
        if (closeId && !selectedNodeIds.has(closeId)) {
          return { valid: false, reason: '选区包含容器但未包含对应的结束标记' };
        }
      }
    }
    return { valid: true };
  }, [selectedNodeIds, treeNodes, NODE_TYPE_MAP]);

  const canBatchMove = hasMultiSelection && selectionValidation.valid;

  // ─── 未闭合容器缩进带警告 ────────────────────────────────────
  const warningBand = useMemo(() => {
    if (!treeNodes.length) return new Map();
    const unclosed = getUnclosedContainers(treeNodes, NODE_TYPE_MAP);
    const band = new Map(); // index -> Set<bandDepth>
    for (const c of unclosed) {
      const containerDepth = c.depth;
      for (let i = c.index + 1; i < treeNodes.length; i++) {
        const nodeDepth = treeNodes[i].depth || 0;
        if (nodeDepth > containerDepth) {
          if (!band.has(i)) band.set(i, new Set());
          band.get(i).add(containerDepth);
        }
      }
    }
    return band;
  }, [treeNodes, NODE_TYPE_MAP]);

  // ─── 选择交互 ────────────────────────────────────────────────

  const handleSelect = useCallback((id, e) => {
    if (e.ctrlKey || e.metaKey) {
      dispatch({ type: 'SELECT_NODE_TOGGLE', payload: id });
    } else if (e.shiftKey) {
      dispatch({ type: 'SELECT_RANGE', payload: id });
    } else {
      dispatch({ type: 'SELECT_NODE', payload: id });
    }
  }, [dispatch]);

  const handleClearSelection = useCallback(() => {
    dispatch({ type: 'CLEAR_SELECTION' });
  }, [dispatch]);

  // ─── 删除 ────────────────────────────────────────────────────

  const handleDelete = useCallback((e, id) => {
    e.stopPropagation();
    if (hasMultiSelection && selectedNodeIds.has(id)) {
      if (!confirm(`确定删除选中的 ${selectedNodeIds.size} 个节点？`)) return;
      deleteNodes(Array.from(selectedNodeIds));
    } else {
      if (!confirm('确定删除该节点？')) return;
      deleteNode(id);
    }
  }, [hasMultiSelection, selectedNodeIds, deleteNodes, deleteNode]);

  const handleToggleEnabled = useCallback((e, node) => {
    e.stopPropagation();
    const newVal = node.enabled === 0 ? 1 : 0;
    updateNode({ id: node.id, enabled: newVal });
  }, [updateNode]);

  // ─── 批量移动 ────────────────────────────────────────────────

  const doMove = useCallback((indices, direction) => {
    const start = indices[0];
    const end = indices[indices.length - 1];
    const count = end - start + 1;
    let newStart = direction === 'up' ? start - 1 : start + 1;
    if (newStart < 0 || newStart + count > treeNodes.length) return;

    const selectedTreeNodes = treeNodes.slice(start, end + 1);
    const remaining = [...treeNodes.slice(0, start), ...treeNodes.slice(end + 1)];
    const newTree = [
      ...remaining.slice(0, newStart),
      ...selectedTreeNodes,
      ...remaining.slice(newStart),
    ];

    const sorted = newTree.map(n => {
      const original = nodes.find(x => x.id === n.id);
      return { ...original };
    });
    for (let i = 0; i < sorted.length; i++) sorted[i].order = i + 1;
    computeParents(sorted, NODE_TYPE_MAP);
    replaceNodes(sorted);
  }, [treeNodes, nodes, NODE_TYPE_MAP, replaceNodes]);

  const handleBatchMove = useCallback((direction) => {
    if (!canBatchMove) return;
    const ids = Array.from(selectedNodeIds);
    const indices = ids.map(id => treeNodes.findIndex(n => n.id === id)).sort((a, b) => a - b);
    for (let i = 1; i < indices.length; i++) {
      if (indices[i] !== indices[i - 1] + 1) return;
    }
    doMove(indices, direction);
  }, [canBatchMove, selectedNodeIds, treeNodes, doMove]);

  // ─── 拖拽：计算插入位置 ──────────────────────────────────────

  const computeInsertIndex = useCallback((clientY) => {
    if (treeNodes.length === 0) return 0;
    const container = document.querySelector('.node-list-container');
    if (!container) return treeNodes.length;
    const rect = container.getBoundingClientRect();
    const scrollTop = container.scrollTop;
    const y = clientY - rect.top + scrollTop - 16;
    const nodeElements = container.querySelectorAll('.step-item');
    for (let i = 0; i < nodeElements.length; i++) {
      const el = nodeElements[i];
      const elRect = el.getBoundingClientRect();
      const elCenter = elRect.top + elRect.height / 2 - rect.top + scrollTop;
      if (y < elCenter) return i;
    }
    return treeNodes.length;
  }, [treeNodes.length]);

  // ─── 内部节点拖拽 ────────────────────────────────────────────

  const handleNodeDragStart = useCallback((e, nodeId) => {
    e.stopPropagation();
    const ids = selectedNodeIds.has(nodeId) && selectionValidation.valid
      ? new Set(selectedNodeIds)
      : new Set([nodeId]);
    setDraggingIds(ids);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', JSON.stringify({ source: 'nodelist', ids: Array.from(ids) }));
  }, [selectedNodeIds, selectionValidation.valid]);

  const handleInternalDrop = useCallback((dropIndex) => {
    if (!draggingIds || draggingIds.size === 0) return;
    const ids = Array.from(draggingIds);
    const indices = ids.map(id => treeNodes.findIndex(n => n.id === id)).sort((a, b) => a - b);
    for (let i = 1; i < indices.length; i++) {
      if (indices[i] !== indices[i - 1] + 1) return;
    }
    const start = indices[0];
    const end = indices[indices.length - 1];
    const selectedTreeNodes = treeNodes.slice(start, end + 1);
    const remaining = [...treeNodes.slice(0, start), ...treeNodes.slice(end + 1)];

    let adjustedDrop = dropIndex;
    if (dropIndex > end) adjustedDrop = dropIndex - selectedTreeNodes.length;

    const newTree = [
      ...remaining.slice(0, adjustedDrop),
      ...selectedTreeNodes,
      ...remaining.slice(adjustedDrop),
    ];

    const sorted = newTree.map(n => {
      const original = nodes.find(x => x.id === n.id);
      return { ...original };
    });
    for (let i = 0; i < sorted.length; i++) sorted[i].order = i + 1;
    computeParents(sorted, NODE_TYPE_MAP);
    replaceNodes(sorted);
  }, [draggingIds, treeNodes, nodes, NODE_TYPE_MAP, replaceNodes]);

  // ─── 面板拖入（左侧指令面板 → 画布）─────────────────────────

  const handleDragOverPanel = useCallback((e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = draggingIds ? 'move' : 'copy';
    setDragOver(true);
    const idx = computeInsertIndex(e.clientY);
    setInsertIndex(idx);

    // 边缘自动滚动
    const container = document.querySelector('.node-list-container');
    if (container) {
      const rect = container.getBoundingClientRect();
      const threshold = 48; // px
      if (e.clientY - rect.top < threshold) {
        autoScrollRef.current.direction = -1;
        startAutoScroll();
      } else if (rect.bottom - e.clientY < threshold) {
        autoScrollRef.current.direction = 1;
        startAutoScroll();
      } else {
        autoScrollRef.current.direction = 0;
      }
    }
  }, [computeInsertIndex, draggingIds, startAutoScroll]);

  const handleDragLeavePanel = useCallback((e) => {
    if (!e.relatedTarget || !e.currentTarget.contains(e.relatedTarget)) {
      setDragOver(false);
      setInsertIndex(null);
      stopAutoScroll();
    }
  }, [stopAutoScroll]);

  const handleDropPanel = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    stopAutoScroll();
    const idx = insertIndex !== null ? insertIndex : treeNodes.length;
    setInsertIndex(null);

    // 内部排序 drop
    if (draggingIds) {
      handleInternalDrop(idx);
      setDraggingIds(null);
      return;
    }

    // 左侧面板拖入
    const raw = e.dataTransfer.getData('text/plain');
    if (!raw) return;
    let payload;
    try { payload = JSON.parse(raw); } catch { payload = { type: raw }; }
    const nodeType = payload.type;
    if (!nodeType) return;
    const typeInfo = NODE_TYPE_MAP[nodeType];
    if (!typeInfo) return;

    const defaultExtra = {};
    if (typeInfo.fields) {
      for (const f of typeInfo.fields) {
        if (f.default !== undefined) {
          defaultExtra[f.name] = f.default;
        }
      }
    }
    const parentId = deriveParentId(nodes, nodeType, NODE_TYPE_MAP, idx);
    saveNode({
      type: nodeType,
      parent_id: parentId,
      extra: defaultExtra,
    }, idx);
  }, [draggingIds, insertIndex, treeNodes, nodes, NODE_TYPE_MAP, saveNode, handleInternalDrop]);

  // ─── 渲染 ────────────────────────────────────────────────────

  return (
    <main
      className="flex-1 flex flex-col min-w-0 bg-white relative"
      onDragOver={handleDragOverPanel}
      onDragEnter={handleDragOverPanel}
      onDragLeave={handleDragLeavePanel}
      onDrop={handleDropPanel}
    >
      <div className={`flex-1 overflow-y-auto p-4 transition-colors node-list-container ${dragOver ? 'bg-blue-50/30' : ''}`}>
        {treeNodes.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="w-full space-y-0.5 relative">
            {dragOver && insertIndex === 0 && <InsertPlaceholder />}
            {treeNodes.map((node, idx) => {
              const typeInfo = NODE_TYPE_MAP[node.type] || {};
              const nextNode = treeNodes[idx + 1];
              const hasChildren = nextNode && nextNode.depth === (node.depth || 0) + 1;
              const isSelected = selectedNodeIds.has(node.id);
              const isDraggingNode = draggingIds && draggingIds.has(node.id);
              return (
                <div key={node.id}>
                  <NodeRow
                    node={node}
                    index={idx}
                    isSelected={isSelected}
                    isDragging={isDraggingNode}
                    NODE_TYPE_MAP={NODE_TYPE_MAP}
                    onSelect={handleSelect}
                    onDelete={handleDelete}
                    onToggleEnabled={handleToggleEnabled}
                    onDragStart={handleNodeDragStart}
                    isRunning={node.id === runningStepId}
                    runError={stepErrors[node.id] || null}
                    elements={elements}
                    warningBand={warningBand}
                  />
                  {/* 容器节点下方的子节点插槽 */}
                  {typeInfo.isContainer && !hasChildren && (
                    <div
                      className="h-0.5 bg-red-500 rounded-sm my-1"
                      style={{ marginLeft: `${(node.depth || 0) * 20 + 24}px` }}
                    />
                  )}
                  {dragOver && insertIndex === idx + 1 && <InsertPlaceholder />}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 多选操作工具栏 */}
      {hasMultiSelection && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-white border shadow-lg rounded-lg px-3 py-2 flex items-center gap-2 z-20">
          <span className="text-xs text-gray-500 mr-1">{selectedNodeIds.size} 个节点</span>
          {!selectionValidation.valid && (
            <span className="text-[10px] text-red-500 bg-red-50 px-1.5 py-0.5 rounded" title={selectionValidation.reason}>
              {selectionValidation.reason}
            </span>
          )}
          <button
            onClick={() => handleBatchMove('up')}
            disabled={!canBatchMove}
            className="w-7 h-7 flex items-center justify-center rounded hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed text-gray-600"
            title="上移"
          >
            <i className="fas fa-arrow-up text-[10px]"></i>
          </button>
          <button
            onClick={() => handleBatchMove('down')}
            disabled={!canBatchMove}
            className="w-7 h-7 flex items-center justify-center rounded hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed text-gray-600"
            title="下移"
          >
            <i className="fas fa-arrow-down text-[10px]"></i>
          </button>
          <div className="w-px h-4 bg-gray-200 mx-1" />
          <button
            onClick={(e) => handleDelete(e, Array.from(selectedNodeIds)[0])}
            className="w-7 h-7 flex items-center justify-center rounded hover:bg-red-100 text-gray-400 hover:text-red-500"
            title="删除"
          >
            <i className="fas fa-trash-alt text-[10px]"></i>
          </button>
          <button
            onClick={handleClearSelection}
            className="w-7 h-7 flex items-center justify-center rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600"
            title="取消选择"
          >
            <i className="fas fa-times text-[10px]"></i>
          </button>
        </div>
      )}

      {/* 画布为空时的拖拽提示 */}
      {dragOver && treeNodes.length === 0 && (
        <div className="absolute inset-0 border-2 border-dashed border-[#1677ff] m-4 rounded flex items-center justify-center pointer-events-none">
          <div className="text-[#1677ff] text-lg font-medium">
            <i className="fas fa-plus-circle mr-2"></i>释放以添加步骤
          </div>
        </div>
      )}
    </main>
  );
}

// ─── 子组件 ───────────────────────────────────────────────────

function NodeRow({ node, index, isSelected, isDragging, NODE_TYPE_MAP, onSelect, onDelete, onToggleEnabled, onDragStart, isRunning, runError, elements, warningBand }) {
  const typeInfo = NODE_TYPE_MAP[node.type] || {};
  const depth = node.depth || 0;
  const indent = depth * 20;
  const isDisabled = node.enabled === 0;

  const runningCls = isRunning ? 'step-running' : '';
  const errorCls = runError ? 'step-error' : '';
  const disabledCls = isDisabled ? 'opacity-40 grayscale' : '';
  const draggingCls = isDragging ? 'opacity-30' : '';
  const colors = ['bg-red-50', 'bg-cyan-50', 'bg-orange-50', 'bg-blue-50', 'bg-green-50', 'bg-purple-50', 'bg-yellow-50'];

  return (
    <div
      className={`
        step-item flex items-start gap-2 px-3 py-2.5 rounded cursor-pointer relative select-none
        ${isSelected ? 'step-selected' : 'hover:bg-[#f5f5f5]'}
        ${runningCls}
        ${errorCls}
        ${disabledCls}
        ${draggingCls}
      `}
      style={{ marginLeft: indent }}
      onClick={(e) => onSelect && onSelect(node.id, e)}
      onDragOver={(e) => { e.preventDefault(); }}
      onDragEnter={(e) => { e.preventDefault(); }}
      title={runError || ''}
    >
      {/* 缩进背景带 — 每层 depth 一条 */}
      {Array.from({ length: depth }).map((_, i) => {
        const bandDepth = i;
        const isWarning = warningBand?.get(index)?.has(bandDepth);
        return (
          <div
            key={i}
            className={`absolute ${isWarning ? 'bg-red-100' : colors[bandDepth % colors.length]}`}
            style={{ left: `${-(depth - i) * 20}px`, top: '-2px', bottom: '-2px', width: '20px' }}
          />
        );
      })}

      {/* 容器/结束行左侧细竖线，颜色与内部最内层缩进带一致 */}
      {(typeInfo.isContainer || typeInfo.isStructural) && (
        <div
          className={`absolute ${warningBand?.get(index)?.has(depth) ? 'bg-red-400' : colors[depth % colors.length]}`}
          style={{ left: '0px', top: '-2px', bottom: '-2px', width: '3px' }}
        />
      )}

      {/* 拖拽手柄 */}
      <div
        draggable
        onDragStart={(e) => onDragStart && onDragStart(e, node.id)}
        className="drag-handle w-6 h-6 flex items-center justify-center shrink-0 mt-0.5 cursor-grab active:cursor-grabbing text-gray-300 hover:text-gray-500 rounded hover:bg-gray-100 touch-none"
        title="拖拽排序"
        onClick={(e) => e.stopPropagation()}
      >
        <i className="fas fa-grip-vertical text-xs pointer-events-none"></i>
      </div>
      <span className="text-xs text-gray-400 font-mono mt-0.5 w-4 text-right shrink-0">{index + 1}</span>
      <div className={`w-6 h-6 rounded flex items-center justify-center shrink-0 mt-0.5 ${typeInfo.bgColor || 'bg-gray-50'}`}>
        <i className={`fas ${typeInfo.icon || 'fa-circle'} ${typeInfo.iconColor || 'text-gray-400'} text-xs`}></i>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <div className="text-xs font-medium text-gray-800">{typeInfo.label || node.type}</div>
          {runError && (
            <span className="text-[10px] text-red-600 bg-red-100 px-1 rounded truncate max-w-[200px]" title={runError}>
              {runError}
            </span>
          )}
        </div>
        <div className="text-[11px] text-gray-500 mt-0.5 truncate">{getNodeDesc(node, NODE_TYPE_MAP, elements)}</div>
      </div>
      {onDelete && (
        <div className="flex items-center gap-1 shrink-0">
          <label
            className="w-6 h-6 flex items-center justify-center rounded hover:bg-gray-100 cursor-pointer"
            title={isDisabled ? '已禁用（执行时跳过）' : '已启用'}
            onClick={(e) => e.stopPropagation()}
          >
            <input
              type="checkbox"
              checked={!isDisabled}
              onChange={(e) => onToggleEnabled && onToggleEnabled(e, node)}
              className="w-3.5 h-3.5 accent-[#1677ff] cursor-pointer"
            />
          </label>
          <button
            onClick={(e) => onDelete(e, node.id)}
            className="w-6 h-6 flex items-center justify-center rounded hover:bg-red-100 text-gray-400 hover:text-red-500"
            title="删除"
          >
            <i className="fas fa-trash-alt text-[10px]"></i>
          </button>
        </div>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center">
      <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
        <i className="fas fa-mouse-pointer text-gray-400 text-2xl"></i>
      </div>
      <p className="text-gray-500 mb-2">画布为空</p>
      <p className="text-sm text-gray-400 mb-4">从左侧拖拽指令到此处，或点击添加</p>
    </div>
  );
}

function InsertPlaceholder() {
  return (
    <div className="relative h-1 -my-0.5 z-10 pointer-events-none">
      <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-0.5 bg-[#1677ff] rounded-full shadow-[0_0_4px_rgba(22,119,255,0.4)]" />
      <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1.5 h-1.5 bg-[#1677ff] rounded-full" />
    </div>
  );
}

// ─── 描述提取 ──────────────────────────────────────────────────

const OP_LABELS = {
  exists: '存在', notExists: '不存在',
  visible: '可见', notVisible: '不可见',
  contains: '包含', notContains: '不包含',
  startsWith: '开头为', endsWith: '结尾为',
  equals: '等于', greaterThan: '大于', lessThan: '小于',
};

function V({ children }) {
  return <span className="font-bold text-red-600">{children}</span>;
}

function getNodeDesc(node, NODE_TYPE_MAP, elements) {
  const typeInfo = NODE_TYPE_MAP[node.type];
  const extra = node.extra && typeof node.extra === 'object' ? node.extra : {};
  const hasElement = typeInfo?.fields?.some(f => f.name === 'element_name');
  const isCondition = node.type.startsWith('if');

  if (hasElement) {
    const parts = [];
    const op = extra.operator;
    const opLabel = op ? (OP_LABELS[op] || op) : null;

    // 条件节点：前缀 + operator 优先显示
    if (isCondition) {
      parts.push(<span key="prefix">如果</span>);
    }
    if (opLabel) {
      parts.push(<span key="op" className="text-gray-500 font-medium">[{opLabel}]</span>);
    }

    if (node.element_name) {
      const el = elements.find(e => e.name === node.element_name);
      parts.push(<span key="el">📎 <V>{el?.name || node.element_name}</V></span>);
    }

    const skipKeys = ['operator', 'scope'];
    for (const [k, v] of Object.entries(extra)) {
      if (skipKeys.includes(k)) continue;
      if (v !== undefined && v !== '' && v !== false) {
        const label = typeInfo.fields?.find(f => f.name === k)?.label || k;
        parts.push(<span key={k}>{label}: <V>{String(v)}</V></span>);
      }
    }

    if (parts.length === 0) return typeInfo?.label || node.type;
    return <span className="space-x-1.5">{parts}</span>;
  }

  const summary = summarizeExtra(node, extra, typeInfo);
  return summary || typeInfo?.label || node.type;
}

function summarizeExtra(node, extra, typeInfo) {
  const val = (k) => extra[k];
  const op = extra.operator;
  const opLabel = op ? (OP_LABELS[op] || op) : null;
  const elName = node?.element_name;

  switch (node?.type) {
    case 'navigate': return val('url') ? <>打开 <V>{val('url')}</V></> : '打开网页';
    case 'newTab': return val('url') ? <>新标签页 <V>{val('url')}</V></> : '新建标签页';
    case 'getCurrentUrl': return <>保存URL → <V>{val('varName') || 'currentUrl'}</V></>;
    case 'input':
    case 'inputAndPressEnter': return val('text') ? <>输入: <V>{val('text')}</V></> : '输入文本';
    case 'clearInput': return '清空输入框';
    case 'pressKey': return <>按键: <V>{val('key') || 'Enter'}</V></>;
    case 'selectOption': return <>选择 (<V>{val('by') || 'label'}</V>): <V>{val('value') || ''}</V></>;
    case 'getText': return <>提取文本 → <V>{val('varName') || 'text'}</V></>;
    case 'getAttr': return <>提取 <V>{val('attrName') || '属性'}</V> → <V>{val('varName') || 'attrVal'}</V></>;
    case 'getHtml': return <>提取HTML → <V>{val('varName') || 'html'}</V></>;
    case 'getValue': return <>提取值 → <V>{val('varName') || 'value'}</V></>;
    case 'scrollToBottom': return '滚动到底部';
    case 'scrollToTop': return '滚动到顶部';
    case 'scrollOneScreen': return '滚动一屏';
    case 'scrollBy': return <>滚动 (<V>{val('x') || 0}, {val('y') || 500}</V>)</>;
    case 'sleep': return <>等待 <V>{val('seconds') || 1}</V> 秒</>;
    case 'waitForElement': return elName ? <>等待出现: <V>{elName}</V></> : '等待元素出现';
    case 'ifElementVisible': return elName ? <>如果<V>{opLabel || '可见'}</V>: <V>{elName}</V></> : `如果元素${opLabel || '可见'}`;
    case 'ifTextContains': return <>文本<V>{opLabel || '包含'}</V>: <V>{val('text') || ''}</V></>;
    case 'ifTextEquals': return <>文本等于: <V>{val('text') || ''}</V></>;
    case 'ifVarEquals': return <><V>{val('varName') || 'x'}</V> <V>{opLabel || '=='}</V> <V>{val('value') || ''}</V></>;
    case 'else': return '否则';
    case 'endIf': return '结束条件';
    case 'forEachElement': return elName ? <>遍历: <V>{elName}</V></> : '循环相似元素';
    case 'forRange': return <>循环 <V>{val('start') || 0}..{val('end') || 10}</V></>;
    case 'forList': return <>遍历列表: <V>{val('listVar') || 'items'}</V></>;
    case 'whileCondition': return <>循环直到: <V>{val('conditionType') || ''}</V></>;
    case 'break': return '跳出循环';
    case 'continue': return '继续下一次';
    case 'endFor': return '结束循环';
    case 'setVar': return <><V>{val('name') || 'x'}</V> = <V>{val('value') || ''}</V></>;
    case 'appendToList': return <>追加: <V>{val('value') || ''}</V></>;
    case 'stringConcat': return <>拼接 → <V>{val('targetVar') || 'result'}</V></>;
    case 'increment': return <><V>{val('varName') || 'count'}</V> += <V>{val('step') || 1}</V></>;
    case 'log': return <><V>[{val('level') || 'info'}]</V> <V>{val('message') || ''}</V></>;
    case 'httpRequest': return <><V>{val('method') || 'GET'}</V> <V>{val('url') || ''}</V></>;
    case 'try': return '捕获异常';
    case 'catch': return '异常处理';
    case 'endTry': return '结束捕获';
    case 'custom': return val('description') || '自定义代码';
    case 'executeJs': return '执行JS';
    default:
      if (typeInfo?.fields) {
        for (const f of typeInfo.fields) {
          const v = extra[f.name];
          if (v !== undefined && v !== '' && v !== false) {
            return <><V>{f.label}</V>: <V>{String(v)}</V></>;
          }
        }
      }
      return typeInfo?.label || node?.type;
  }
}
