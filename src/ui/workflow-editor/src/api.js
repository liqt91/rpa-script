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
  runWorkflow: (wfId) => request(`/api/workflows/${wfId}/run`, { method: 'POST' }),
  runWorkflowExtension: (wfId, runId) => request(`/api/workflows/${wfId}/run/extension?run_id=${encodeURIComponent(runId)}`, { method: 'POST' }),
  getCommands: () => request('/api/workflows/commands'),

  // Elements
  getElements: (hostname) => request(`/api/elements${hostname ? `?hostname=${encodeURIComponent(hostname)}` : ''}`),
  getElementHosts: () => request('/api/elements/hosts'),
  deleteElement: (id) => request(`/api/elements/${id}`, { method: 'DELETE' }),
  updateElement: (id, payload) => request(`/api/elements/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  }),

  // AI
  invokeAI: (capability, payload) => request('/api/ai/invoke', {
    method: 'POST',
    body: JSON.stringify({ capability, payload }),
  }),
  getAICapabilities: () => request('/api/ai/capabilities'),

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
