import { createContext, useContext, useReducer, useCallback, useEffect, useRef } from 'react';
import { api } from '../api';

const initialState = {
  wfId: null,
  workflow: null,
  nodes: [],
  treeNodes: [],
  selectedNodeId: null,
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
  return result;
}

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
    case 'SELECT_NODE':
      console.log(`[reducer] SELECT_NODE id=${action.payload}`);
      return { ...state, selectedNodeId: action.payload };
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
      return { ...state, nodes, treeNodes: buildTree(nodes), selectedNodeId: null, isDirty: true };
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
      return { ...state, runningStepId: action.payload.nodeId ?? null };
    case 'RUN_STEP_ERROR':
      return {
        ...state,
        runStatus: 'error',
        runningStepId: action.payload.nodeId ?? null,
        stepErrors: { ...state.stepErrors, [action.payload.nodeId]: action.payload.error },
      };
    case 'RUN_DONE':
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
  for (const cat of Object.values(commands.commands)) {
    for (const cmd of cat) {
      result.push(cmd);
    }
  }
  return result.sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'));
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

export function deriveParentId(nodes, newNodeType, typeMap, insertIndex) {
  /* 基于列表位置推导 parent_id。
     规则：按 order 扫描所有节点，维护容器栈；
     - 遇到容器(isContainer) → push
     - 遇到分支(isBranch, 如 else/catch) → 先 pop（关闭前一分支）再 push（开启新分支）
     - 遇到结束标记(isStructural, 如 endIf/endFor) → pop
     - 新节点的 parent_id = 栈顶节点 id（栈空则为 null）
     insertIndex: 按 order 排序后的插入位置（可选，缺省=末尾） */
  const sorted = [...nodes].sort((a, b) => a.order - b.order);
  const stack = [];

  for (let i = 0; i < sorted.length; i++) {
    if (insertIndex !== undefined && i === insertIndex) {
      break;
    }
    const node = sorted[i];
    const info = typeMap[node.type];
    if (info?.isBranch) {
      stack.pop();
      stack.push(node.id);
    } else if (info?.isContainer) {
      stack.push(node.id);
    } else if (info?.isStructural) {
      stack.pop();
    }
  }

  const newInfo = typeMap[newNodeType];
  if (newInfo?.isBranch) {
    const closed = stack.pop();
    return closed || null;
  } else if (newInfo?.isStructural) {
    const closed = stack.pop();
    return closed || null;
  }
  return stack.length > 0 ? stack[stack.length - 1] : null;
}

export function WorkflowProvider({ children, wfId }) {
  const [state, dispatch] = useReducer(reducer, { ...initialState, wfId });
  const stateRef = useRef(state);
  stateRef.current = state;

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
    try {
      const els = await api.getElements();
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

  const deleteNode = useCallback((nodeId) => {
    console.log(`[WorkflowContext] deleteNode id=${nodeId}`);
    dispatch({ type: 'REMOVE_NODE', payload: nodeId });
    setTimeout(() => persistToLocal(), 0);
  }, [persistToLocal]);

  const replaceNodes = useCallback((newNodes) => {
    console.log(`[WorkflowContext] replaceNodes count=${newNodes.length}`);
    dispatch({ type: 'REPLACE_NODES', payload: newNodes });
    setTimeout(() => persistToLocal(), 0);
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

      // 判断是否为临时 id（UUID 格式）
      const isTempId = (id) => id && typeof id === 'string' && id.includes('-');

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
    loadWorkflow,
    loadElements,
    saveNode,
    updateNode,
    deleteNode,
    replaceNodes,
    commit,
    reorderNodes,
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
