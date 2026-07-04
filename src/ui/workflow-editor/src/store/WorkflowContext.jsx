import { createContext, useContext, useReducer, useCallback, useEffect, useRef } from 'react';
import { api } from '../api';

const initialState = {
  wfId: null,
  workflow: null,
  nodes: [],
  treeNodes: [],
  selectedNodeId: null,
  selectedNodeIds: new Set(),
  selectionAnchor: null,
  loading: false,
  error: null,
  elements: [],
  elementHosts: [],
  saving: false,
  commands: null,
  commandsLoading: true,
  isDirty: false,
  runStatus: 'idle', // 'idle' | 'running' | 'error' | 'completed'
  runningStepId: null,
  stepErrors: {},
  runLogs: [],
};

function buildTree(flatNodes) {
  const byParent = {};
  const allIds = new Set(flatNodes.map(n => n.id));
  for (const n of flatNodes) {
    const pid = n.parent_id || 0;
    if (!byParent[pid]) byParent[pid] = [];
    byParent[pid].push(n);
  }
  for (const k in byParent) {
    byParent[k].sort((a, b) => a.order - b.order);
  }
  const result = [];
  function walk(parentId, depth) {
    const nodes = byParent[parentId] || [];
    for (const n of nodes) {
      result.push({ ...n, depth });
      walk(n.id, depth + 1);
    }
  }
  walk(0, 0);
  // 兜底：把孤儿节点（parent_id 指向不存在的节点）挂到根层，避免丢失
  for (const n of flatNodes) {
    const pid = n.parent_id || 0;
    if (pid !== 0 && !allIds.has(pid)) {
      if (!result.find(r => r.id === n.id)) {
        result.push({ ...n, depth: 0 });
      }
    }
  }
  return result;
}

/**
 * Build a nested element tree from a flat element list.
 * Uses backend-derived parent_name/anchor_element_name fields.
 */
export function buildElementTree(elements = []) {
  const byParent = {};
  const roots = [];
  const nameSet = new Set(elements.map(e => e.name));
  for (const el of elements) {
    const parent = el.parent_name || el.anchor_element_name;
    if (!parent || !nameSet.has(parent)) {
      roots.push({ ...el, isOrphan: !!parent });
    } else {
      if (!byParent[parent]) byParent[parent] = [];
      byParent[parent].push(el);
    }
  }
  function walk(el) {
    return {
      ...el,
      children: (byParent[el.name] || []).map(walk),
    };
  }
  return roots.map(walk);
}

/**
 * Walk upward from an element through its parent chain and return the chain
 * from the outermost root to the target element.
 */
export function getElementChain(elements = [], targetName) {
  const byName = Object.fromEntries(elements.map(e => [e.name, e]));
  const chain = [];
  const seen = new Set();
  let current = byName[targetName];
  while (current) {
    if (seen.has(current.name)) break;
    seen.add(current.name);
    chain.unshift(current);
    const parentName = current.parent_name || current.anchor_element_name;
    current = parentName ? byName[parentName] : null;
  }
  return chain;
}

/**
 * Walk upward from a node through parent_id and return ancestor nodes whose
 * type matches one of the given types. Nearest ancestor first.
 */
export function findAncestorNodes(nodes, selectedNodeId, types) {
  const idToNode = new Map(nodes.map(n => [n.id, n]));
  const typeSet = new Set(types);
  const result = [];
  let node = idToNode.get(selectedNodeId);
  while (node && node.parent_id != null) {
    node = idToNode.get(node.parent_id);
    if (node && typeSet.has(node.type)) {
      result.push(node);
    }
  }
  return result;
}

const isTempId = (id) => id && typeof id === 'string' && id.includes('-');

function reducer(state, action) {
  switch (action.type) {
    case 'SET_WF_ID':
      return { ...state, wfId: action.payload };
    case 'SET_WORKFLOW':
      return { ...state, workflow: action.payload };
    case 'SET_NODES': {
      const nodes = action.payload;
      const isDirty = action.isDirty !== undefined ? action.isDirty : false;
      console.log(`[reducer] SET_NODES count=${nodes.length} dirty=${isDirty}`);
      return { ...state, nodes, treeNodes: buildTree(nodes), isDirty };
    }
    case 'SELECT_NODE': {
      const id = action.payload;
      console.log(`[reducer] SELECT_NODE id=${id}`);
      return { ...state, selectedNodeId: id, selectedNodeIds: new Set([id]), selectionAnchor: id };
    }
    case 'SELECT_NODE_TOGGLE': {
      const id = action.payload;
      const ids = new Set(state.selectedNodeIds);
      if (ids.has(id)) {
        ids.delete(id);
      } else {
        ids.add(id);
      }
      const newAnchor = ids.size === 1 ? Array.from(ids)[0] : state.selectionAnchor;
      return { ...state, selectedNodeId: id, selectedNodeIds: ids, selectionAnchor: newAnchor };
    }
    case 'SELECT_RANGE': {
      const targetId = action.payload;
      const anchorId = state.selectionAnchor;
      if (!anchorId) {
        return { ...state, selectedNodeId: targetId, selectedNodeIds: new Set([targetId]), selectionAnchor: targetId };
      }
      const anchorIdx = state.treeNodes.findIndex(n => n.id === anchorId);
      const targetIdx = state.treeNodes.findIndex(n => n.id === targetId);
      if (anchorIdx === -1 || targetIdx === -1) {
        return { ...state, selectedNodeId: targetId };
      }
      const start = Math.min(anchorIdx, targetIdx);
      const end = Math.max(anchorIdx, targetIdx);
      const ids = new Set();
      for (let i = start; i <= end; i++) {
        ids.add(state.treeNodes[i].id);
      }
      return { ...state, selectedNodeIds: ids, selectedNodeId: targetId };
    }
    case 'CLEAR_SELECTION':
      return { ...state, selectedNodeIds: new Set(), selectedNodeId: null, selectionAnchor: null };
    case 'SET_LOADING':
      return { ...state, loading: action.payload };
    case 'SET_ERROR':
      console.error(`[reducer] SET_ERROR: ${action.payload}`);
      return { ...state, error: action.payload };
    case 'SET_ELEMENTS':
      return { ...state, elements: action.payload };
    case 'SET_ELEMENT_HOSTS':
      return { ...state, elementHosts: action.payload };
    case 'SET_SAVING':
      return { ...state, saving: action.payload };
    case 'SET_COMMANDS':
      console.log(`[reducer] SET_COMMANDS categories=${action.payload?.categories?.length || 0}`);
      return { ...state, commands: action.payload, commandsLoading: false };
    case 'SET_DIRTY':
      return { ...state, isDirty: action.payload };
    case 'UPDATE_NODE_LOCAL': {
      const nodes = state.nodes.map(n =>
        n.id === action.payload.id ? { ...n, ...action.payload } : n
      );
      console.log(`[reducer] UPDATE_NODE_LOCAL id=${action.payload.id} dirty=true`);
      return { ...state, nodes, treeNodes: buildTree(nodes), isDirty: true };
    }
    case 'REMOVE_NODE': {
      const removeId = action.payload;
      const removedNode = state.nodes.find(n => n.id === removeId);
      const promoteTo = removedNode?.parent_id ?? null;
      // 删除目标节点，同时将其子节点上提一级（parent_id 指向被删节点的父节点）
      const nodes = state.nodes
        .filter(n => n.id !== removeId)
        .map(n => n.parent_id === removeId ? { ...n, parent_id: promoteTo } : n);
      console.log(`[reducer] REMOVE_NODE id=${removeId} remaining=${nodes.length}`);
      return { ...state, nodes, treeNodes: buildTree(nodes), selectedNodeId: null, selectedNodeIds: new Set(), isDirty: true };
    }
    case 'REMOVE_NODES': {
      const removeIds = new Set(action.payload);
      const idToNode = Object.fromEntries(state.nodes.map(n => [n.id, n]));
      const nodes = state.nodes
        .filter(n => !removeIds.has(n.id))
        .map(n => {
          let pid = n.parent_id;
          while (pid !== null && removeIds.has(pid)) {
            pid = idToNode[pid]?.parent_id ?? null;
          }
          return pid !== n.parent_id ? { ...n, parent_id: pid } : n;
        });
      console.log(`[reducer] REMOVE_NODES count=${removeIds.size} remaining=${nodes.length}`);
      return { ...state, nodes, treeNodes: buildTree(nodes), selectedNodeId: null, selectedNodeIds: new Set(), selectionAnchor: null, isDirty: true };
    }
    case 'ADD_NODE_LOCAL': {
      const { _insertIndex, ...nodeData } = action.payload;
      const newNode = { ...nodeData };

      let nodes;
      if (typeof _insertIndex === 'number' && _insertIndex >= 0 && _insertIndex <= state.nodes.length) {
        const sorted = [...state.nodes].sort((a, b) => a.order - b.order);
        sorted.splice(_insertIndex, 0, newNode);
        for (let i = 0; i < sorted.length; i++) {
          sorted[i].order = i + 1;
        }
        nodes = sorted;
        console.log(`[reducer] ADD_NODE_LOCAL id=${newNode.id} type=${newNode.type} insertAt=${_insertIndex} total=${nodes.length}`);
      } else {
        nodes = [...state.nodes, newNode];
        console.log(`[reducer] ADD_NODE_LOCAL id=${newNode.id} type=${newNode.type} append total=${nodes.length}`);
      }

      return { ...state, nodes, treeNodes: buildTree(nodes), selectedNodeId: newNode.id, isDirty: true };
    }
    case 'REPLACE_NODES': {
      const nodes = action.payload;
      console.log(`[reducer] REPLACE_NODES count=${nodes.length}`);
      return { ...state, nodes, treeNodes: buildTree(nodes), isDirty: true };
    }
    case 'RUN_START':
      return { ...state, runStatus: 'running', runningStepId: null, stepErrors: {} };
    case 'RUN_STEP':
      // 暂停时 stepComplete 发送 nodeId=null，不要清除高亮
      if (state.runStatus === 'paused' && action.payload.nodeId === null) {
        return state;
      }
      return { ...state, runningStepId: action.payload.nodeId ?? null };
    case 'RUN_PAUSED':
      return { ...state, runStatus: 'paused' };
    case 'RUN_STEP_ERROR':
      return {
        ...state,
        runStatus: 'error',
        runningStepId: action.payload.nodeId ?? null,
        stepErrors: { ...state.stepErrors, [action.payload.nodeId]: action.payload.error },
      };
    case 'RUN_DONE':
      if (action.payload.stopped) {
        return { ...state, runStatus: 'stopped', runningStepId: null };
      }
      return {
        ...state,
        runStatus: action.payload.success ? 'completed' : 'error',
        runningStepId: null,
      };
    case 'RUN_RESET':
      return { ...state, runStatus: 'idle', runningStepId: null, stepErrors: {} };
    case 'APPEND_RUN_LOG':
      return { ...state, runLogs: [...state.runLogs, action.payload] };
    case 'CLEAR_RUN_LOGS':
      return { ...state, runLogs: [] };
    default:
      return state;
  }
}

const WorkflowContext = createContext(null);

// ─── Derived selectors ────────────────────────────────────────────

function getNodeTypes(commands) {
  if (!commands || !commands.commands) return [];
  const result = [];
  for (const categoryName of commands.categories || []) {
    const cat = commands.commands[categoryName] || [];
    for (const cmd of cat) {
      result.push({ ...cmd, category: categoryName });
    }
  }
  return result;
}

function getCategories(commands) {
  return commands?.categories || [];
}

function getNodeTypeMap(nodeTypes) {
  return Object.fromEntries(nodeTypes.map(n => [n.type, n]));
}

function getContainerTypes(commands) {
  return commands?.containerTypes || [];
}

// ─── derive parent_id from position-based indentation ─────────────

/**
 * 括号匹配：为每个结构标记（右括号）找到对应的容器（左括号）。
 * 返回 Map<structuralId, containerId>
 */
export function matchBrackets(sorted, typeMap) {
  const stack = []; // { id, closesWith }[]
  const match = new Map();
  for (const node of sorted) {
    const info = typeMap[node.type];
    if (info?.isBranch) {
      // 分支（else/catch）与原始容器共享同一个结束标记，不进入栈
      if (stack.length > 0) {
        stack[stack.length - 1].closesWith = info.closesWith || stack[stack.length - 1].closesWith;
      }
    } else if (info?.isContainer) {
      stack.push({ id: node.id, closesWith: info.closesWith });
    } else if (info?.isStructural) {
      const closeType = node.type; // e.g. "endFor"
      let idx = stack.length - 1;
      while (idx >= 0 && stack[idx].closesWith !== closeType) idx--;
      if (idx >= 0) {
        const closed = stack.splice(idx, 1)[0];
        match.set(node.id, closed.id);
      }
    }
  }
  return match;
}

/**
 * 找出所有未闭合的容器。
 * 返回 { id, closesWith, index, depth }[]
 */
export function getUnclosedContainers(sorted, typeMap) {
  const stack = [];
  for (let i = 0; i < sorted.length; i++) {
    const node = sorted[i];
    const info = typeMap[node.type];
    if (info?.isBranch) {
      // 分支（else/catch）与原始容器共享同一个结束标记，不进入栈
      if (stack.length > 0) {
        stack[stack.length - 1].closesWith = info.closesWith || stack[stack.length - 1].closesWith;
      }
    } else if (info?.isContainer) {
      stack.push({ id: node.id, closesWith: info.closesWith, index: i, depth: node.depth || 0 });
    } else if (info?.isStructural) {
      const closeType = node.type;
      let idx = stack.length - 1;
      while (idx >= 0 && stack[idx].closesWith !== closeType) idx--;
      if (idx >= 0) {
        stack.splice(idx, 1);
      }
    }
  }
  return stack;
}

/**
 * 基于括号匹配结果计算每个节点的 parent_id。
 * 规则：节点属于离它最近且尚未闭合的容器。
 * 结构标记和容器平级（parent = 容器的 parent）。
 */
export function computeParents(sorted, typeMap) {
  const bracketMatch = matchBrackets(sorted, typeMap);
  // 反向映射：容器 id → 结构标记 id
  const containerClose = new Map();
  for (const [sId, cId] of bracketMatch) containerClose.set(cId, sId);

  const scope = []; // 当前打开的容器 {containerId, branchId, closesWith}[]
  for (const node of sorted) {
    const info = typeMap[node.type];
    if (info?.isContainer) {
      node.parent_id = scope.length > 0 ? scope[scope.length - 1].branchId : null;
      scope.push({ containerId: node.id, branchId: node.id, closesWith: info.closesWith });
    } else if (info?.isBranch) {
      // 分支与原始容器平级，但其后代属于该分支
      const closed = scope.pop();
      const closedParent = closed ? (sorted.find(n => n.id === closed.containerId)?.parent_id ?? null) : null;
      node.parent_id = closedParent;
      scope.push({
        containerId: closed.containerId,
        branchId: node.id,
        closesWith: info.closesWith || closed?.closesWith,
      });
    } else if (info?.isStructural) {
      const closeType = node.type;
      let idx = scope.length - 1;
      while (idx >= 0 && scope[idx].closesWith !== closeType) idx--;
      if (idx >= 0) {
        const closed = scope.splice(idx, 1)[0];
        const closedParent = sorted.find(n => n.id === closed.containerId)?.parent_id ?? null;
        node.parent_id = closedParent;
      } else {
        node.parent_id = null;
      }
    } else {
      node.parent_id = scope.length > 0 ? scope[scope.length - 1].branchId : null;
    }
  }
  return sorted;
}

export function deriveParentId(nodes, newNodeType, typeMap, insertIndex) {
  /* 推导新节点的 parent_id。
     先把现有节点做一次括号匹配，然后按插入位置截断，看新节点落在哪个作用域里。 */
  const sorted = [...nodes].sort((a, b) => a.order - b.order);

  // 只处理插入位置之前的节点，做括号匹配
  const prefix = insertIndex !== undefined ? sorted.slice(0, insertIndex) : sorted;
  const scope = []; // 当前未闭合的容器 {containerId, branchId, closesWith}[]
  for (const node of prefix) {
    const info = typeMap[node.type];
    if (info?.isContainer) {
      scope.push({ containerId: node.id, branchId: node.id, closesWith: info.closesWith });
    } else if (info?.isBranch) {
      if (scope.length > 0) {
        const closed = scope[scope.length - 1];
        scope[scope.length - 1] = {
          containerId: closed.containerId,
          branchId: node.id,
          closesWith: info.closesWith || closed.closesWith,
        };
      }
    } else if (info?.isStructural) {
      const closeType = node.type;
      let idx = scope.length - 1;
      while (idx >= 0 && scope[idx].closesWith !== closeType) idx--;
      if (idx >= 0) scope.splice(idx, 1);
    }
  }

  const newInfo = typeMap[newNodeType];
  if (newInfo?.isBranch) {
    // 分支：与栈顶原始容器平级
    const closed = scope[scope.length - 1];
    return closed
      ? (sorted.find(n => n.id === closed.containerId)?.parent_id ?? null)
      : null;
  }
  if (newInfo?.isStructural) {
    // 结构标记：找到匹配的原始容器，与其平级
    const closeType = newNodeType;
    let idx = scope.length - 1;
    while (idx >= 0 && scope[idx].closesWith !== closeType) idx--;
    if (idx >= 0) {
      const closed = scope[idx];
      return sorted.find(n => n.id === closed.containerId)?.parent_id ?? null;
    }
    return null;
  }
  // 容器/普通节点：落在当前最内层作用域里
  return scope.length > 0 ? scope[scope.length - 1].branchId : null;
}

export function WorkflowProvider({ children, wfId }) {
  const [state, dispatch] = useReducer(reducer, { ...initialState, wfId });
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  });

  const loadCommands = useCallback(async () => {
    try {
      const data = await api.getCommands();
      dispatch({ type: 'SET_COMMANDS', payload: data });
    } catch (e) {
      dispatch({ type: 'SET_ERROR', payload: e.message });
      dispatch({ type: 'SET_COMMANDS', payload: null });
    }
  }, []);

  useEffect(() => {
    loadCommands();
  }, [loadCommands]);

  const STORAGE_KEY = (id) => `workflow_editor_nodes_${id}`;

  // 辅助：立即保存当前 state 到 localStorage
  const persistToLocal = useCallback(() => {
    const { wfId, isDirty, nodes } = stateRef.current;
    console.log(`[WorkflowContext] persistToLocal called: wfId=${wfId}, isDirty=${isDirty}, nodes=${nodes.length}`);
    if (!wfId) {
      console.log('[WorkflowContext] persistToLocal skipped: no wfId');
      return;
    }
    if (isDirty && nodes.length > 0) {
      try {
        const key = STORAGE_KEY(wfId);
        const serialized = JSON.stringify(nodes);
        localStorage.setItem(key, serialized);
        console.log(`[WorkflowContext] ✅ persistToLocal saved ${nodes.length} nodes (key=${key})`);
      } catch (e) {
        console.error(`[WorkflowContext] ❌ persistToLocal failed: ${e.message}`);
      }
    } else if (!isDirty) {
      localStorage.removeItem(STORAGE_KEY(wfId));
      console.log('[WorkflowContext] persistToLocal: cleared localStorage (not dirty)');
    }
  }, []);

  const loadWorkflow = useCallback(async () => {
    if (!stateRef.current.wfId) return;
    console.log(`[WorkflowContext] loading workflow id=${stateRef.current.wfId}`);
    dispatch({ type: 'SET_LOADING', payload: true });
    try {
      const wf = await api.getWorkflow(stateRef.current.wfId);
      dispatch({ type: 'SET_WORKFLOW', payload: wf });

      // 优先恢复本地未提交的节点
      const key = STORAGE_KEY(stateRef.current.wfId);
      const saved = localStorage.getItem(key);
      console.log(`[WorkflowContext] localStorage check for wf ${stateRef.current.wfId}: key=${key}, found=${!!saved}`);
      if (saved) {
        try {
          const parsed = JSON.parse(saved);
          console.log(`[WorkflowContext] ✅ restored ${parsed.length} nodes from localStorage`);
          dispatch({ type: 'SET_NODES', payload: parsed, isDirty: true });
        } catch (e) {
          console.error(`[WorkflowContext] ❌ failed to parse localStorage data: ${e.message}`);
          localStorage.removeItem(key);
          const nodes = await api.getWorkflowNodes(stateRef.current.wfId);
          dispatch({ type: 'SET_NODES', payload: nodes });
        }
      } else {
        const nodes = await api.getWorkflowNodes(stateRef.current.wfId);
        console.log(`[WorkflowContext] loaded '${wf.name}' with ${nodes.length} nodes from server`);
        dispatch({ type: 'SET_NODES', payload: nodes });
      }
    } catch (e) {
      console.error(`[WorkflowContext] loadWorkflow failed: ${e.message}`);
      dispatch({ type: 'SET_ERROR', payload: e.message });
    } finally {
      dispatch({ type: 'SET_LOADING', payload: false });
    }
  }, []);

  const loadElements = useCallback(async () => {
    if (!stateRef.current.wfId) return;
    try {
      const els = await api.getWorkflowElements(stateRef.current.wfId);
      dispatch({ type: 'SET_ELEMENTS', payload: els });
    } catch (e) {
      // silent
    }
  }, []);

  // ─── Local node operations ──────────────────────────────────────

  const saveNode = useCallback((payload, insertIndex) => {
    if (!stateRef.current.wfId) return;
    const tempId = crypto.randomUUID();
    const node = { ...payload, id: tempId, order: payload.order || (stateRef.current.nodes.length + 1), _insertIndex: insertIndex };
    console.log(`[WorkflowContext] saveNode tempId=${tempId} type=${node.type} insertIndex=${insertIndex ?? 'end'}`);
    dispatch({ type: 'ADD_NODE_LOCAL', payload: node });
    setTimeout(() => persistToLocal(), 0);
    return node;
  }, [persistToLocal]);

  const updateNode = useCallback((payload) => {
    console.log(`[WorkflowContext] updateNode id=${payload.id} type=${payload.type}`);
    dispatch({ type: 'UPDATE_NODE_LOCAL', payload });
    setTimeout(() => persistToLocal(), 0);
  }, [persistToLocal]);

  const deleteNode = useCallback(async (nodeId) => {
    console.log(`[WorkflowContext] deleteNode id=${nodeId}`);
    const currentWfId = stateRef.current.wfId;
    if (currentWfId && !isTempId(nodeId)) {
      try {
        await api.deleteNode(currentWfId, nodeId);
      } catch (e) {
        console.error(`[WorkflowContext] deleteNode API failed: ${e.message}`);
        return;
      }
    }
    dispatch({ type: 'REMOVE_NODE', payload: nodeId });
    setTimeout(() => persistToLocal(), 0);
  }, [persistToLocal]);

  const deleteNodes = useCallback(async (nodeIds) => {
    console.log(`[WorkflowContext] deleteNodes count=${nodeIds.length}`);
    const currentWfId = stateRef.current.wfId;
    if (currentWfId) {
      const toDelete = nodeIds.filter(id => !isTempId(id));
      await Promise.all(toDelete.map(id =>
        api.deleteNode(currentWfId, id).catch(e => {
          console.warn(`[WorkflowContext] deleteNode API skipped: ${e.message}`);
        })
      ));
    }
    dispatch({ type: 'REMOVE_NODES', payload: nodeIds });
    setTimeout(() => persistToLocal(), 0);
  }, [persistToLocal]);

  const replaceNodes = useCallback((newNodes) => {
    console.log(`[WorkflowContext] replaceNodes count=${newNodes.length}`);
    dispatch({ type: 'REPLACE_NODES', payload: newNodes });
    setTimeout(() => persistToLocal(), 0);
  }, [persistToLocal]);

  // ─── Copy / Paste nodes ─────────────────────────────────────────

  const copyNodes = useCallback(async (nodeIds) => {
    const current = stateRef.current;
    if (!nodeIds || nodeIds.length === 0) return;

    // Collect each selected root plus its descendants, preserving order.
    const roots = new Set(nodeIds);
    const inSelection = new Set(nodeIds);
    const queue = Array.from(nodeIds);
    while (queue.length > 0) {
      const id = queue.shift();
      for (const n of current.nodes) {
        if (n.parent_id === id && !inSelection.has(n.id)) {
          inSelection.add(n.id);
          queue.push(n.id);
        }
      }
    }

    const copied = current.nodes
      .filter(n => inSelection.has(n.id))
      .map(n => ({ ...n }))
      .sort((a, b) => a.order - b.order);

    const rootsOrderMin = Math.min(...copied.filter(n => roots.has(n.id)).map(n => n.order));
    const payload = {
      version: 1,
      roots: Array.from(roots),
      nodes: copied,
      baseOrder: rootsOrderMin,
    };

    try {
      await navigator.clipboard.writeText(JSON.stringify(payload));
      console.log(`[WorkflowContext] copyNodes count=${copied.length}`);
    } catch (e) {
      console.error('[WorkflowContext] copyNodes failed:', e);
      dispatch({ type: 'SET_ERROR', payload: '复制失败：' + e.message });
    }
  }, []);

  const pasteNodes = useCallback(async (targetNodeId) => {
    const current = stateRef.current;
    try {
      const text = await navigator.clipboard.readText();
      const payload = JSON.parse(text);
      if (!payload || payload.version !== 1 || !Array.isArray(payload.nodes)) {
        console.warn('[WorkflowContext] pasteNodes: clipboard does not contain workflow nodes');
        return;
      }

      const copiedNodes = payload.nodes.map(n => ({ ...n }));
      const oldRootIds = new Set(payload.roots || []);

      // Determine target parent and insertion order.
      let targetParentId = null;
      let insertAfterOrder = 0;
      const targetNode = targetNodeId ? current.nodes.find(n => n.id === targetNodeId) : null;

      if (targetNode) {
        targetParentId = targetNode.parent_id;
        // Insert after the selected node's entire subtree.
        const tree = buildTree(current.nodes);
        const targetIdx = tree.findIndex(n => n.id === targetNode.id);
        if (targetIdx !== -1) {
          const targetDepth = tree[targetIdx].depth;
          let endIdx = targetIdx;
          for (let i = targetIdx + 1; i < tree.length; i++) {
            if (tree[i].depth <= targetDepth) break;
            endIdx = i;
          }
          insertAfterOrder = tree[endIdx].order;
        } else {
          insertAfterOrder = targetNode.order;
        }
      } else {
        const siblings = current.nodes.filter(n => n.parent_id === null);
        insertAfterOrder = siblings.length > 0 ? Math.max(...siblings.map(n => n.order)) : 0;
      }

      // Generate new IDs and remap parent IDs.
      const idMap = new Map();
      const pasted = copiedNodes.map(n => {
        const newId = crypto.randomUUID();
        idMap.set(n.id, newId);
        return { ...n, id: newId };
      });

      for (const n of pasted) {
        if (idMap.has(n.parent_id)) {
          n.parent_id = idMap.get(n.parent_id);
        } else if (oldRootIds.has(n.parent_id)) {
          n.parent_id = targetParentId;
        } else {
          n.parent_id = targetParentId;
        }
      }

      // Merge into existing nodes: shift later orders, assign new orders to pasted nodes.
      const pastedCount = pasted.length;
      const existing = current.nodes.map(n => ({ ...n }));
      for (const n of existing) {
        if (n.order > insertAfterOrder) {
          n.order += pastedCount;
        }
      }

      const sortedPasted = pasted.sort((a, b) => a.order - b.order);
      for (let i = 0; i < sortedPasted.length; i++) {
        sortedPasted[i].order = insertAfterOrder + i + 1;
      }

      const combined = [...existing, ...sortedPasted];
      combined.sort((a, b) => a.order - b.order);
      for (let i = 0; i < combined.length; i++) {
        combined[i].order = i + 1;
      }

      console.log(`[WorkflowContext] pasteNodes count=${pastedCount} after=${insertAfterOrder}`);
      dispatch({ type: 'REPLACE_NODES', payload: combined });
      setTimeout(() => persistToLocal(), 0);

      // Select the pasted root nodes.
      const pastedRootIds = pasted.filter(n => n.parent_id === targetParentId).map(n => n.id);
      if (pastedRootIds.length > 0) {
        dispatch({ type: 'SELECT_NODE', payload: pastedRootIds[0] });
      }
    } catch (e) {
      console.error('[WorkflowContext] pasteNodes failed:', e);
      dispatch({ type: 'SET_ERROR', payload: '粘贴失败：' + e.message });
    }
  }, [persistToLocal]);

  // ─── Commit: batch save to backend ──────────────────────────────

  const commit = useCallback(async () => {
    const current = stateRef.current;
    if (!current.wfId || !current.isDirty) return;
    console.log(`[WorkflowContext] commit saving ${current.nodes.length} nodes`);
    dispatch({ type: 'SET_SAVING', payload: true });
    try {
      const selectedNode = current.nodes.find(n => n.id === current.selectedNodeId);
      const selectedOrder = selectedNode?.order ?? null;
      const selectedType = selectedNode?.type ?? null;

      // 构建 payload：已有节点保留 id，新节点发送 temp_id
      const payload = current.nodes.map((n, idx) => {
        const node = { ...n, order: idx + 1 };
        delete node._insertIndex;
        if (isTempId(node.id)) {
          node.temp_id = node.id;
          delete node.id;
        }
        if (node.extra && typeof node.extra !== 'object') {
          try { node.extra = JSON.parse(node.extra); } catch { node.extra = {}; }
        }
        return node;
      });

      console.log(`[WorkflowContext] batchUpdateNodes payload:`, payload);
      const result = await api.batchUpdateNodes(current.wfId, payload);
      console.log(`[WorkflowContext] server returned ${result.length} nodes, dispatching SET_NODES`);
      dispatch({ type: 'SET_NODES', payload: result });
      dispatch({ type: 'SET_DIRTY', payload: false });
      setTimeout(() => persistToLocal(), 0);
      console.log(`[WorkflowContext] ✅ commit saved, ${result.length} nodes, localStorage will be cleared by effect`);

      // 恢复选中：按 order + type 匹配
      if (selectedOrder !== null) {
        const match = result.find(n => n.order === selectedOrder && n.type === selectedType);
        if (match) {
          console.log(`[WorkflowContext] restore selection id=${match.id} order=${selectedOrder}`);
          dispatch({ type: 'SELECT_NODE', payload: match.id });
        }
      }
    } catch (e) {
      console.error(`[WorkflowContext] commit failed: ${e.message}`);
      dispatch({ type: 'SET_ERROR', payload: e.message });
      throw e;
    } finally {
      dispatch({ type: 'SET_SAVING', payload: false });
    }
  }, []);

  const reorderNodes = useCallback(async (orders) => {
    const current = stateRef.current;
    if (!current.wfId) return;
    try {
      await request(`/api/workflows/${current.wfId}/nodes/reorder`, {
        method: 'POST',
        body: JSON.stringify(orders),
      });
      await loadWorkflow();
    } catch (e) {
      dispatch({ type: 'SET_ERROR', payload: e.message });
    }
  }, [loadWorkflow]);

  const updateWorkflowParameters = useCallback(async (parameters) => {
    const current = stateRef.current;
    if (!current.wfId || !current.workflow) return;
    try {
      const updated = await api.updateWorkflow(current.wfId, { parameters });
      dispatch({ type: 'SET_WORKFLOW', payload: updated });
    } catch (e) {
      console.error('[WorkflowContext] updateWorkflowParameters failed:', e);
      dispatch({ type: 'SET_ERROR', payload: e.message });
      throw e;
    }
  }, []);

  // Derived values
  const NODE_TYPES = getNodeTypes(state.commands);
  const CATEGORIES = getCategories(state.commands);
  const NODE_TYPE_MAP = getNodeTypeMap(NODE_TYPES);
  const selectedNode = state.nodes.find(n => n.id === state.selectedNodeId) || null;
  const containerTypes = getContainerTypes(state.commands);
  const containerNodes = state.nodes.filter(n => containerTypes.includes(n.type));

  const value = {
    ...state,
    NODE_TYPES,
    CATEGORIES,
    NODE_TYPE_MAP,
    selectedNode,
    containerNodes,
    containerTypes,
    findAncestorNodes,
    buildElementTree,
    getElementChain,
    loadWorkflow,
    loadElements,
    saveNode,
    updateNode,
    deleteNode,
    deleteNodes,
    replaceNodes,
    copyNodes,
    pasteNodes,
    commit,
    reorderNodes,
    updateWorkflowParameters,
    dispatch,
  };

  return (
    <WorkflowContext.Provider value={value}>
      {children}
    </WorkflowContext.Provider>
  );
}

export function useWorkflow() {
  const ctx = useContext(WorkflowContext);
  if (!ctx) throw new Error('useWorkflow must be used within WorkflowProvider');
  return ctx;
}

export { getNodeTypeMap };

async function request(url, options = {}) {
  function getCookie(name) {
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : null;
  }
  const token = getCookie('access_token');
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(url, { ...options, headers: { ...headers, ...(options.headers || {}) } });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}
