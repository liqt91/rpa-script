const API_BASE = '';

function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : null;
}

function authHeaders() {
  const token = getCookie('access_token');
  const h = { 'Content-Type': 'application/json' };
  if (token) h['Authorization'] = `Bearer ${token}`;
  return h;
}

async function request(url, options = {}) {
  const method = options.method || 'GET';
  console.log(`[api] ${method} ${url}`, options.body ? JSON.parse(options.body) : '');
  const start = performance.now();
  const res = await fetch(url, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  const elapsed = (performance.now() - start).toFixed(1);
  console.log(`[api] ${method} ${url} -> ${res.status} (${elapsed}ms)`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    console.error(`[api] ${method} ${url} error:`, err.detail || `HTTP ${res.status}`);
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  const data = await res.json();
  console.log(`[api] ${method} ${url} response:`, data);
  return data;
}

export const api = {
  // Workflow
  listWorkflows: () => request('/api/workflows'),
  createWorkflow: (payload) => request('/api/workflows', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  deleteWorkflow: (id) => request(`/api/workflows/${id}`, { method: 'DELETE' }),
  getWorkflow: (id) => request(`/api/workflows/${id}`),
  getWorkflowNodes: (id) => request(`/api/workflows/${id}/nodes`),
  createNode: (wfId, payload) => request(`/api/workflows/${wfId}/nodes`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  updateNode: (wfId, nodeId, payload) => request(`/api/workflows/${wfId}/nodes/${nodeId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  }),
  deleteNode: (wfId, nodeId) => request(`/api/workflows/${wfId}/nodes/${nodeId}`, {
    method: 'DELETE',
  }),
  batchUpdateNodes: (wfId, payload) => request(`/api/workflows/${wfId}/nodes/batch`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  }),
  exportPython: (wfId) => request(`/api/workflows/${wfId}/export/python`),
  runWorkflow: (wfId, parameters = null) => request(`/api/workflows/${wfId}/run`, {
    method: 'POST',
    body: JSON.stringify(parameters ? { parameters } : {}),
  }),
  runWorkflowExtension: (wfId, runId, tableData, parameters = null) => request(`/api/workflows/${wfId}/run/extension?run_id=${encodeURIComponent(runId)}`, {
    method: 'POST',
    body: JSON.stringify({
      initialTableData: tableData,
      ...(parameters ? { parameters } : {}),
    }),
  }),
  pauseRun: (wfId, runId) => request(`/api/workflows/${wfId}/run/${encodeURIComponent(runId)}/pause`, { method: 'POST' }),
  resumeRun: (wfId, runId) => request(`/api/workflows/${wfId}/run/${encodeURIComponent(runId)}/resume`, { method: 'POST' }),
  stopRun: (wfId, runId) => request(`/api/workflows/${wfId}/run/${encodeURIComponent(runId)}/stop`, { method: 'POST' }),
  getCommands: () => request('/api/workflows/commands'),

  // Workflow Elements (per-workflow element library)
  getWorkflowElements: (wfId) => request(`/api/workflows/${wfId}/elements`),
  createWorkflowElement: (wfId, payload) => request(`/api/workflows/${wfId}/elements`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  updateWorkflowElement: (wfId, elId, payload) => request(`/api/workflows/${wfId}/elements/${elId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  }),
  deleteWorkflowElement: (wfId, elId) => request(`/api/workflows/${wfId}/elements/${elId}`, {
    method: 'DELETE',
  }),

  // AI
  invokeAI: (capability, payload) => request('/api/ai/invoke', {
    method: 'POST',
    body: JSON.stringify({ capability, payload }),
  }),
  getAICapabilities: () => request('/api/ai/capabilities'),

  // Data Table (每个流程唯一)
  getDataTable: (wfId) => request(`/api/workflows/${wfId}/data-table`),
  updateDataTable: (wfId, payload) => request(`/api/workflows/${wfId}/data-table`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  }),
  importDataTable: (wfId, csvText) => request(`/api/workflows/${wfId}/data-table/import`, {
    method: 'POST',
    body: JSON.stringify({ csv: csvText }),
  }),
  exportDataTable: (wfId) => fetch(`/api/workflows/${wfId}/data-table/export`, {
    headers: authHeaders(),
  }),
  clearDataTable: (wfId) => request(`/api/workflows/${wfId}/data-table/clear`, { method: 'POST' }),
  getLastRunTable: (wfId) => request(`/api/workflows/${wfId}/data-table/last-run`),

  // System
  getBrowserPaths: () => request('/api/workflows/system/browser-paths'),
  getUpdateInfo: () => request('/api/system/update'),
  openExtensionsPage: (browser) => request(`/api/system/open-extensions-page?browser=${encodeURIComponent(browser || 'chrome')}`, { method: 'POST' }),
  openDbFolder: () => request('/api/system/open-db-folder', { method: 'POST' }),

  // Admin
  getAdminDashboard: () => request('/api/admin/dashboard'),
  changePassword: (payload) => request('/api/auth/password', { method: 'POST', body: JSON.stringify(payload) }),

  // Run logs
  listAllRuns: () => request('/api/workflows/runs'),
  getActiveRuns: () => request('/api/workflows/runs/active'),
  stopActiveRun: () => request('/api/workflows/runs/active/stop', { method: 'POST' }),
  getWorkflowRuns: (wfId) => request(`/api/workflows/${wfId}/runs`),
  getRunLog: (wfId, runId) => request(`/api/workflows/${wfId}/runs/${encodeURIComponent(runId)}/log`),
  getRunTable: (wfId, runId) => request(`/api/workflows/${wfId}/runs/${encodeURIComponent(runId)}/table`),
  openRunFolder: (wfId, runId) => request(`/api/workflows/${wfId}/runs/${encodeURIComponent(runId)}/open-folder`, { method: 'POST' }),

  // Workflow update
  updateWorkflow: (id, payload) => request(`/api/workflows/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  }),

  // Extension (浏览器扩展通信)
  getExtensionStatus: () => request('/api/extension/status'),
  sendExtensionCommand: (action, payload, browserType) => {
    let url = `/api/extension/command?action=${encodeURIComponent(action)}`;
    if (browserType) url += `&browser_type=${encodeURIComponent(browserType)}`;
    return request(url, {
      method: 'POST',
      body: JSON.stringify(payload || {}),
    });
  },
};
