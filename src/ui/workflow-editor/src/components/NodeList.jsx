import { useState, useEffect } from 'react';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  DragOverlay,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useWorkflow, deriveParentId } from '../store/WorkflowContext';

export default function NodeList() {
  const {
    treeNodes,
    selectedNodeId,
    dispatch,
    deleteNode,
    nodes,
    NODE_TYPE_MAP,
    saveNode,
    replaceNodes,
    wfId,
    runStatus,
    runningStepId,
    stepErrors,
  } = useWorkflow();
  const [dragOver, setDragOver] = useState(false);
  const [insertIndex, setInsertIndex] = useState(null);
  const [activeId, setActiveId] = useState(null);

  // 全局 dragend 后备：任何 HTML5 拖拽结束时重置状态
  useEffect(() => {
    const onDragEnd = () => {
      if (dragOver) {
        console.log('[NodeList] global dragend fallback -> reset dragOver');
        setDragOver(false);
        setInsertIndex(null);
      }
    };
    window.addEventListener('dragend', onDragEnd);
    return () => window.removeEventListener('dragend', onDragEnd);
  }, [dragOver]);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 }, // 鼠标移动 5px 才触发拖拽，避免误触
    })
  );

  const handleSelect = (id) => {
    dispatch({ type: 'SELECT_NODE', payload: id });
  };

  const handleDelete = (e, id) => {
    e.stopPropagation();
    console.log(`[NodeList] deleteNode id=${id}`);
    if (!confirm('确定删除该节点？')) return;
    deleteNode(id);
  };

  // ─── 从左侧指令面板拖入新指令 ───────────────────────────

  const handleDragOverPanel = (e) => {
    // 允许任何 drop，具体校验在 handleDropPanel 里做
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    setDragOver(true);

    // 实时计算插入位置
    if (treeNodes.length > 0) {
      const container = e.currentTarget.querySelector('.overflow-y-auto');
      if (container) {
        const rect = container.getBoundingClientRect();
        const scrollTop = container.scrollTop;
        const y = e.clientY - rect.top + scrollTop - 16;
        const nodeElements = container.querySelectorAll('.step-item');
        let idx = treeNodes.length;
        for (let i = 0; i < nodeElements.length; i++) {
          const el = nodeElements[i];
          const elRect = el.getBoundingClientRect();
          const elCenter = elRect.top + elRect.height / 2 - rect.top + scrollTop;
          if (y < elCenter) {
            idx = i;
            break;
          }
        }
        setInsertIndex(prev => prev === idx ? prev : idx);
      }
    } else {
      setInsertIndex(0);
    }
  };

  const handleDragLeavePanel = (e) => {
    // relatedTarget 为 null（离开窗口/按 Escape）或不在容器内时重置
    if (!e.relatedTarget || !e.currentTarget.contains(e.relatedTarget)) {
      console.log('[NodeList] dragLeave -> reset dragOver');
      setDragOver(false);
      setInsertIndex(null);
    }
  };

  const handleDropPanel = (e) => {
    e.preventDefault();
    console.log('[NodeList] drop -> reset dragOver');
    setDragOver(false);
    setInsertIndex(null);
    const raw = e.dataTransfer.getData('text/plain');
    if (!raw) {
      console.log('[NodeList] drop empty data, skipped');
      return;
    }
    let payload;
    try { payload = JSON.parse(raw); } catch { payload = { type: raw }; }
    const nodeType = payload.type;
    console.log(`[NodeList] dropPanel type=${nodeType}`);
    if (!nodeType) return;
    const typeInfo = NODE_TYPE_MAP[nodeType];
    if (!typeInfo) { console.warn(`[NodeList] unknown nodeType: ${nodeType}`); return; }

    const defaultExtra = {};
    if (typeInfo.fields) {
      for (const f of typeInfo.fields) {
        if (f.default !== undefined && !['locator', 'locator_type', 'method'].includes(f.name)) {
          defaultExtra[f.name] = f.default;
        }
      }
    }

    const dropIndex = insertIndex !== null ? insertIndex : treeNodes.length;
    console.log(`[NodeList] drop insertIndex=${dropIndex} total=${treeNodes.length}`);

    const parentId = deriveParentId(nodes, nodeType, NODE_TYPE_MAP, dropIndex);
    saveNode({
      type: nodeType,
      parent_id: parentId,
      locator: '',
      locator_type: 'css',
      method: 'ele',
      extra: defaultExtra,
    }, dropIndex);
  };

  // ─── dnd-kit 拖拽排序 ──────────────────────────────────────

  const handleDragStart = (event) => {
    setActiveId(event.active.id);
    document.body.classList.add('dragging-node');
  };

  const handleDragEnd = (event) => {
    document.body.classList.remove('dragging-node');
    const { active, over } = event;
    console.log(`[NodeList] dragEnd active=${active?.id} over=${over?.id}`);
    setActiveId(null);
    if (!over || active.id === over.id) return;

    const oldIndex = treeNodes.findIndex(n => n.id === active.id);
    const newIndex = treeNodes.findIndex(n => n.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    // 用 arrayMove 计算新顺序
    const movedTree = arrayMove(treeNodes, oldIndex, newIndex);

    // 用原始 nodes 数据构建新顺序
    const sorted = movedTree.map(n => {
      const original = nodes.find(x => x.id === n.id);
      return { ...original };
    });

    // 重新分配 order
    for (let i = 0; i < sorted.length; i++) {
      sorted[i].order = i + 1;
    }

    // 基于新顺序重新计算 parent_id
    const stack = [];
    for (const node of sorted) {
      const info = NODE_TYPE_MAP[node.type];
      if (info?.isBranch) {
        const closed = stack.pop();
        node.parent_id = closed || null;
        stack.push(node.id);
      } else if (info?.isContainer) {
        node.parent_id = stack.length > 0 ? stack[stack.length - 1] : null;
        stack.push(node.id);
      } else if (info?.isStructural) {
        const closed = stack.pop();
        node.parent_id = closed || null;
      } else {
        node.parent_id = stack.length > 0 ? stack[stack.length - 1] : null;
      }
    }

    replaceNodes(sorted);
  };

  // ─── 描述渲染 ──────────────────────────────────────────────

  const activeNode = activeId ? treeNodes.find(n => n.id === activeId) : null;

  return (
    <main
      className="flex-1 flex flex-col min-w-0 bg-white relative"
      onDragOver={handleDragOverPanel}
      onDragLeave={handleDragLeavePanel}
      onDrop={handleDropPanel}
    >
      <div className={`flex-1 overflow-y-auto p-4 transition-colors ${dragOver ? 'bg-blue-50/30' : ''}`}>
        {treeNodes.length === 0 ? (
          <EmptyState />
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
          >
            <SortableContext
              items={treeNodes.map(n => n.id)}
              strategy={verticalListSortingStrategy}
            >
              <div className="w-full space-y-0.5 relative">
                {dragOver && insertIndex === 0 && <InsertPlaceholder />}
                {treeNodes.map((node, idx) => {
                  const typeInfo = NODE_TYPE_MAP[node.type] || {};
                  const nextNode = treeNodes[idx + 1];
                  const hasChildren = nextNode && nextNode.depth === (node.depth || 0) + 1;
                  return (
                    <div key={node.id}>
                      <SortableNode
                        node={node}
                        index={idx}
                        isSelected={node.id === selectedNodeId}
                        NODE_TYPE_MAP={NODE_TYPE_MAP}
                        onSelect={handleSelect}
                        onDelete={handleDelete}
                        isRunning={node.id === runningStepId}
                        runError={stepErrors[node.id] || null}
                      />
                      {/* 容器节点下方的子节点插槽 */}
                      {typeInfo.isContainer && !hasChildren && (
                        <div
                          className={`border border-dashed rounded py-2.5 px-3 text-xs flex items-center gap-2 transition-colors ${dragOver ? 'border-[#1677ff] bg-blue-50/60 text-[#1677ff]' : 'border-gray-300 bg-gray-50/50 text-gray-400'}`}
                          style={{ marginLeft: `${(node.depth || 0) * 20 + 24}px` }}
                        >
                          <i className="fas fa-plus text-[10px]"></i>
                          拖入指令到此处
                        </div>
                      )}
                      {dragOver && insertIndex === idx + 1 && <InsertPlaceholder />}
                    </div>
                  );
                })}
              </div>
            </SortableContext>
            <DragOverlay>
              {activeNode ? (
                <NodeRow
                  node={activeNode}
                  index={treeNodes.findIndex(n => n.id === activeNode.id)}
                  isSelected={false}
                  isOverlay
                  NODE_TYPE_MAP={NODE_TYPE_MAP}
                  isRunning={false}
                  runError={null}
                />
              ) : null}
            </DragOverlay>
          </DndContext>
        )}
      </div>

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

function SortableNode({ node, index, isSelected, NODE_TYPE_MAP, onSelect, onDelete, isRunning, runError }) {
  const {
    listeners,
    attributes,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: node.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.3 : 1,
  };

  return (
    <div ref={setNodeRef} style={style}>
      <NodeRow
        node={node}
        index={index}
        isSelected={isSelected}
        listeners={listeners}
        attributes={attributes}
        NODE_TYPE_MAP={NODE_TYPE_MAP}
        onSelect={onSelect}
        onDelete={onDelete}
        isRunning={isRunning}
        runError={runError}
      />
    </div>
  );
}

function NodeRow({ node, index, isSelected, listeners, attributes, NODE_TYPE_MAP, onSelect, onDelete, isOverlay, isRunning, runError }) {
  const typeInfo = NODE_TYPE_MAP[node.type] || {};
  const depth = node.depth || 0;
  const indent = depth * 20;

  const runningCls = isRunning ? 'step-running' : '';
  const errorCls = runError ? 'step-error' : '';

  return (
    <div
      className={`
        step-item flex items-start gap-2 px-3 py-2.5 rounded cursor-pointer relative
        ${isSelected ? 'step-selected' : 'hover:bg-[#f5f5f5]'}
        ${isOverlay ? 'bg-white shadow-lg border border-[#1677ff]' : ''}
        ${runningCls}
        ${errorCls}
      `}
      style={{ marginLeft: indent }}
      onClick={() => onSelect && onSelect(node.id)}
      title={runError || ''}
    >
      {/* 缩进竖线 — 每层 depth 一条 */}
      {Array.from({ length: depth }).map((_, i) => (
        <div
          key={i}
          className="absolute border-l border-gray-200"
          style={{ left: `${-(depth - i) * 20 - 2}px`, top: '-2px', bottom: '-2px' }}
        />
      ))}

      {/* 分支线 — else/catch 左侧水平线连回前序容器 */}
      {typeInfo.isBranch && depth > 0 && (
        <div
          className="absolute border-t border-gray-300"
          style={{ left: `${-20}px`, top: '50%', width: '18px' }}
        />
      )}

      {/* 闭合线 — endIf/endFor/endTry L 形返回线 */}
      {typeInfo.isStructural && depth > 0 && (
        <div
          className="absolute border-l border-b border-gray-200 rounded-bl"
          style={{ left: `${-18}px`, top: '-50%', height: 'calc(50% + 1px)', width: '16px' }}
        />
      )}

      {/* 拖拽手柄 */}
      <div
        {...listeners}
        {...attributes}
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
        <div className="text-[11px] text-gray-500 mt-0.5 truncate">{getNodeDesc(node, NODE_TYPE_MAP)}</div>
      </div>
      {isSelected && onDelete && (
        <div className="flex items-center gap-1 shrink-0">
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

function getNodeDesc(node, NODE_TYPE_MAP) {
  const typeInfo = NODE_TYPE_MAP[node.type];
  const extra = node.extra && typeof node.extra === 'object' ? node.extra : {};
  const hasLocator = typeInfo?.fields?.some(f => f.name === 'locator');
  if (hasLocator) {
    const parts = [];
    if (node.locator) parts.push(node.locator);
    if (node.method && node.locator) parts.push(`${node.method}()`);
    return parts.join(' · ') || typeInfo?.label || node.type;
  }
  const summary = summarizeExtra(node.type, extra, typeInfo);
  return summary || typeInfo?.label || node.type;
}

function summarizeExtra(type, extra, typeInfo) {
  const val = (k) => extra[k];
  switch (type) {
    case 'navigate': return val('url') ? `打开 ${val('url')}` : '打开网页';
    case 'goBack': return '返回上一页';
    case 'goForward': return '前进';
    case 'refresh': return val('hardReload') ? '强制刷新' : '刷新页面';
    case 'newTab': return val('url') ? `新标签页 ${val('url')}` : '新建标签页';
    case 'closeTab': return '关闭标签页';
    case 'switchTab': return `切换标签页 (${val('by') || 'index'}=${val('value') || ''})`;
    case 'switchToFrame': return val('locator') ? `进入 iframe: ${val('locator')}` : '进入 iframe';
    case 'switchToMain': return '退出 iframe';
    case 'getCurrentUrl': return `保存URL → ${val('varName') || 'currentUrl'}`;
    case 'getPageTitle': return `保存标题 → ${val('varName') || 'pageTitle'}`;
    case 'input':
    case 'inputAndPressEnter': return val('text') ? `输入: ${val('text')}` : '输入文本';
    case 'clearInput': return '清空输入框';
    case 'pressKey': return `按键: ${val('key') || 'Enter'}`;
    case 'selectOption': return `选择: ${val('value') || ''}`;
    case 'getText': return `提取文本 → ${val('varName') || 'text'}`;
    case 'getAttr': return `提取 ${val('attrName') || '属性'} → ${val('varName') || 'attrVal'}`;
    case 'getHtml': return `提取HTML → ${val('varName') || 'html'}`;
    case 'getValue': return `提取值 → ${val('varName') || 'value'}`;
    case 'getElementCount': return `计数 → ${val('varName') || 'count'}`;
    case 'getElementList': return `获取列表 → ${val('varName') || 'elements'}`;
    case 'scrollToBottom': return '滚动到底部';
    case 'scrollToTop': return '滚动到顶部';
    case 'scrollIntoView': return val('locator') ? `滚动到: ${val('locator')}` : '滚动到元素';
    case 'scrollBy': return `滚动 (${val('x') || 0}, ${val('y') || 500})`;
    case 'infiniteScroll': return `无限滚动 (最大${val('maxScrolls') || 50}次)`;
    case 'sleep': return `等待 ${val('seconds') || 1} 秒`;
    case 'waitForElement': return val('locator') ? `等待出现: ${val('locator')}` : '等待元素出现';
    case 'waitForElementHide': return val('locator') ? `等待消失: ${val('locator')}` : '等待元素消失';
    case 'waitForText': return `等待文本: ${val('text') || ''}`;
    case 'waitForUrl': return `等待URL: ${val('urlPattern') || ''}`;
    case 'waitForLoad': return `等待页面加载 (${val('state') || 'networkidle'})`;
    case 'ifElementExists': return val('locator') ? `如果存在: ${val('locator')}` : '如果元素存在';
    case 'ifElementNotExists': return val('locator') ? `如果不存在: ${val('locator')}` : '如果元素不存在';
    case 'ifElementVisible': return val('locator') ? `如果可见: ${val('locator')}` : '如果元素可见';
    case 'ifTextContains': return `文本包含: ${val('text') || ''}`;
    case 'ifTextEquals': return `文本等于: ${val('text') || ''}`;
    case 'ifUrlContains': return `URL包含: ${val('urlPattern') || ''}`;
    case 'ifVarEquals': return `${val('varName') || 'x'} == ${val('value') || ''}`;
    case 'ifVarGreaterThan': return `${val('varName') || 'x'} > ${val('value') || 0}`;
    case 'else': return '否则';
    case 'endIf': return '结束条件';
    case 'forEachElement': return val('locator') ? `遍历: ${val('locator')}` : '循环相似元素';
    case 'forRange': return `循环 ${val('start') || 0}..${val('end') || 10}`;
    case 'forList': return `遍历列表: ${val('listVar') || 'items'}`;
    case 'whileCondition': return `循环直到: ${val('conditionType') || ''}`;
    case 'break': return '跳出循环';
    case 'continue': return '继续下一次';
    case 'endFor': return '结束循环';
    case 'setVar': return `${val('name') || 'x'} = ${val('value') || ''}`;
    case 'appendToList': return `追加: ${val('value') || ''}`;
    case 'stringConcat': return `拼接 → ${val('targetVar') || 'result'}`;
    case 'increment': return `${val('varName') || 'count'} += ${val('step') || 1}`;
    case 'log': return `[${val('level') || 'info'}] ${val('message') || ''}`;
    case 'pushItem': return '推送结果项';
    case 'takeScreenshot': return `截图: ${val('savePath') || ''}`;
    case 'saveToFile': return `保存到: ${val('filePath') || ''}`;
    case 'keyCombo': return `按键: ${val('keys') || ''}`;
    case 'httpRequest': return `${val('method') || 'GET'} ${val('url') || ''}`;
    case 'callAiApp': return `AI: ${val('appType') || ''}`;
    case 'callWorkflow': return `调用流程 #${val('workflowId') || ''}`;
    case 'return': return '结束并返回';
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
            return `${f.label}: ${v}`;
          }
        }
      }
      return typeInfo?.label || type;
  }
}
