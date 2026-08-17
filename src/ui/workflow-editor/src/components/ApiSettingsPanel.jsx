import { useState } from 'react';
import { useWorkflow } from '../store/WorkflowContext';
import { api } from '../api';

function buildDocs(wfId, apiKey) {
  const origin = (typeof window !== 'undefined' && window.location && window.location.origin) || 'http://localhost:8100';
  const base = `${origin}/api/public`;
  return {
    triggerUrl: `${base}/trigger/${wfId}`,
    streamUrl: `${base}/stream/{run_id}`,
    resultUrl: `${base}/result/{run_id}`,
    apiKey,
    curlTrigger: [
      `curl -X POST \\`,
      `  ${base}/trigger/${wfId} \\`,
      `  -H "X-API-Key: ${apiKey}" \\`,
      `  -H "Content-Type: application/json" \\`,
      `  -d '{"parameters": {"key": "value"}}'`,
    ].join('\n'),
    psTrigger: [
      `Invoke-RestMethod -Uri '${base}/trigger/${wfId}' \``,
      `  -Method Post \``,
      `  -Headers @{'X-API-Key'='${apiKey}';'Content-Type'='application/json'} \``,
      `  -Body '{"parameters":{"key":"value"}}'`,
    ].join('\n'),
    curlStream: [
      `curl -N \\`,
      `  ${base}/stream/{run_id} \\`,
      `  -H "X-API-Key: ${apiKey}"`,
    ].join('\n'),
    psStream: [
      `Invoke-WebRequest -Uri '${base}/stream/{run_id}' \\`,
      `  -Headers @{'X-API-Key'='${apiKey}'}`,
    ].join('\n'),
    curlResult: [
      `curl \\`,
      `  ${base}/result/{run_id} \\`,
      `  -H "X-API-Key: ${apiKey}"`,
    ].join('\n'),
    psResult: [
      `Invoke-RestMethod -Uri '${base}/result/{run_id}' \\`,
      `  -Headers @{'X-API-Key'='${apiKey}'}`,
    ].join('\n'),
  };
}

function CodeBlock({ code }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative group">
      <pre className="bg-surface-2 rounded p-1.5 text-muted text-[10px] overflow-x-auto whitespace-pre-wrap">{code}</pre>
      <button
        onClick={() => {
          copyTextToClipboard(code).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          });
        }}
        className="absolute top-1 right-1 text-[10px] text-faint hover:text-accent opacity-0 group-hover:opacity-100 transition-opacity"
        title="复制"
      ><i className={`fas ${copied ? 'fa-check' : 'fa-copy'}`}></i></button>
    </div>
  );
}

function JsonBlock({ data }) {
  const code = JSON.stringify(data, null, 2);
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative group">
      <pre className="bg-surface-2 rounded p-1.5 text-muted text-[10px] overflow-x-auto">{code}</pre>
      <button
        onClick={() => {
          copyTextToClipboard(code).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          });
        }}
        className="absolute top-1 right-1 text-[10px] text-faint hover:text-accent opacity-0 group-hover:opacity-100 transition-opacity"
        title="复制"
      ><i className={`fas ${copied ? 'fa-check' : 'fa-copy'}`}></i></button>
    </div>
  );
}

export default function ApiSettingsPanel() {
  const { workflow, dispatch } = useWorkflow();
  const [showKeyConfirm, setShowKeyConfirm] = useState(false);

  const docs = workflow?.api_enabled && workflow?.api_key
    ? buildDocs(workflow.id, workflow.api_key)
    : null;

  const colClass = 'border border-border rounded bg-surface flex flex-col min-w-0';

  return (
    <div className="flex-1 bg-surface flex flex-col select-none overflow-hidden min-h-0">
      <div className="px-4 py-2 border-b border-border flex items-center justify-between shrink-0">
        <div>
          <h2 className="text-sm font-medium text-body">API 设置</h2>
          <p className="text-[10px] text-muted">启用后外部系统可通过 API 触发此流程</p>
        </div>
        <label className="flex items-center gap-1.5 cursor-pointer text-xs text-muted">
          <input
            type="checkbox"
            checked={workflow?.api_enabled === 1}
            onChange={async () => {
              const enabling = workflow?.api_enabled !== 1;
              const key = enabling
                ? (workflow?.api_key || crypto.randomUUID().replace(/-/g, '').slice(0, 16))
                : (workflow?.api_key || '');
              try {
                const updated = await api.updateWorkflow(workflow.id, { api_enabled: enabling ? 1 : 0, api_key: key });
                dispatch({ type: 'SET_WORKFLOW', payload: updated });
              } catch (e) { alert('更新失败: ' + e.message); }
            }}
            className="accent-accent"
          />
          <span className="font-medium">启用</span>
        </label>
      </div>

      <div className="flex-1 overflow-auto p-4">
        {!workflow?.api_enabled ? (
          <div className="text-center py-8 text-xs text-faint">
            <i className="fas fa-plug text-2xl mb-2 block"></i>
            开启上方开关以启用 API 调用
          </div>
        ) : docs ? (
          <div className="grid gap-3" style={{ gridTemplateColumns: '1fr 2.2fr 2fr 2.2fr' }}>
            {/* ① API Key */}
            <div className={colClass}>
              <div className="px-3 py-2 border-b border-border shrink-0">
                <div className="flex items-center gap-1.5">
                  <span className="w-4 h-4 rounded-full bg-accent-soft text-accent text-[10px] font-bold flex items-center justify-center shrink-0">1</span>
                  <span className="text-xs font-medium text-body">API Key</span>
                </div>
              </div>
              <div className="flex-1 p-3 space-y-2 text-[11px]">
                <div className="flex items-center gap-1.5">
                  <code className="text-[11px] bg-surface-2 px-2 py-1 rounded text-muted font-mono select-all break-all">{workflow.api_key}</code>
                  <button
                    onClick={(e) => { const btn = e.currentTarget; copyTextToClipboard(workflow.api_key).then(() => { btn.innerHTML = '<i class="fas fa-check"></i>'; setTimeout(() => { btn.innerHTML = '<i class="fas fa-copy"></i>'; }, 1500); }); }}
                    className="text-[10px] text-accent hover:text-accent shrink-0"
                  ><i className="fas fa-copy"></i></button>
                  <button
                    onClick={() => setShowKeyConfirm(true)}
                    className="text-[10px] text-faint hover:text-muted shrink-0"
                  ><i className="fas fa-sync-alt"></i></button>
                </div>
                <p className="text-[10px] text-faint">所有接口通过 X-API-Key 请求头鉴权</p>
                <CodeBlock code={`X-API-Key: ${workflow.api_key}`} />
              </div>
            </div>

            {/* ② 触发执行 */}
            <div className={colClass}>
              <div className="px-3 py-2 border-b border-border shrink-0">
                <div className="flex items-center gap-1.5">
                  <span className="w-4 h-4 rounded-full bg-ok-soft text-ok text-[10px] font-bold flex items-center justify-center shrink-0">2</span>
                  <span className="text-xs font-medium text-body">触发执行</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-ok-soft text-ok ml-auto">POST</span>
                </div>
              </div>
              <div className="flex-1 p-3 space-y-2 text-[11px] overflow-auto">
                <div>
                  <span className="text-faint block text-[10px]">URL</span>
                  <code className="text-[10px] text-muted font-mono bg-surface-2 px-1 py-0.5 rounded block mt-0.5 break-all">{docs.triggerUrl}</code>
                </div>
                <div>
                  <span className="text-faint block text-[10px]">Response</span>
                  <JsonBlock data={{ run_id: 'api_xxx', workflow_id: workflow.id, status: 'started', sse_url: '/api/public/stream/api_xxx', result_url: '/api/public/result/api_xxx' }} />
                </div>
                <div>
                  <span className="text-faint block text-[10px]">Bash</span>
                  <CodeBlock code={docs.curlTrigger} />
                </div>
                <div>
                  <span className="text-faint block text-[10px]">PowerShell</span>
                  <CodeBlock code={docs.psTrigger} />
                </div>
              </div>
            </div>

            {/* ③ 查询结果 */}
            <div className={colClass}>
              <div className="px-3 py-2 border-b border-border shrink-0">
                <div className="flex items-center gap-1.5">
                  <span className="w-4 h-4 rounded-full bg-purple-100 text-purple-600 text-[10px] font-bold flex items-center justify-center shrink-0">3</span>
                  <span className="text-xs font-medium text-body">查询结果</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-accent-soft text-accent ml-auto">GET</span>
                </div>
              </div>
              <div className="flex-1 p-3 space-y-2 text-[11px] overflow-auto">
                <div>
                  <span className="text-faint block text-[10px]">URL</span>
                  <code className="text-[10px] text-muted font-mono bg-surface-2 px-1 py-0.5 rounded block mt-0.5 break-all">{docs.resultUrl}</code>
                </div>
                <div>
                  <span className="text-faint block text-[10px]">Response (成功)</span>
                  <JsonBlock data={{ run_id: 'api_xxx', success: true, outputs: { totalCount: 42 }, error: null, started_at: '...', completed_at: '...' }} />
                </div>
                <div>
                  <span className="text-faint block text-[10px]">Response (运行中)</span>
                  <JsonBlock data={{ status: 'running' }} />
                </div>
                <div>
                  <span className="text-faint block text-[10px]">Bash</span>
                  <CodeBlock code={docs.curlResult} />
                </div>
                <div>
                  <span className="text-faint block text-[10px]">PowerShell</span>
                  <CodeBlock code={docs.psResult} />
                </div>
              </div>
            </div>

            {/* ④ SSE 进度流 */}
            <div className={colClass}>
              <div className="px-3 py-2 border-b border-border shrink-0">
                <div className="flex items-center gap-1.5">
                  <span className="w-4 h-4 rounded-full bg-orange-100 text-orange-600 text-[10px] font-bold flex items-center justify-center shrink-0">4</span>
                  <span className="text-xs font-medium text-body">SSE 进度流</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-accent-soft text-accent ml-auto">GET</span>
                </div>
              </div>
              <div className="flex-1 p-3 space-y-2 text-[11px] overflow-auto">
                <div>
                  <span className="text-faint block text-[10px]">URL</span>
                  <code className="text-[10px] text-muted font-mono bg-surface-2 px-1 py-0.5 rounded block mt-0.5 break-all">{docs.streamUrl}</code>
                </div>
                <div>
                  <span className="text-faint block text-[10px]">SSE 事件类型</span>
                  <CodeBlock code={`stepStart  — 步骤开始
stepResult — 步骤完成
done       — 执行完毕，含 outputs
stepError  — 步骤失败
heartbeat  — 心跳`} />
                </div>
                <div>
                  <span className="text-faint block text-[10px]">done 事件示例</span>
                  <JsonBlock data={{ type: 'done', success: true, outputs: { totalCount: 42 }, completedSteps: 5, totalSteps: 5 }} />
                </div>
                <div>
                  <span className="text-faint block text-[10px]">Bash</span>
                  <CodeBlock code={docs.curlStream} />
                </div>
                <div>
                  <span className="text-faint block text-[10px]">PowerShell</span>
                  <CodeBlock code={docs.psStream} />
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </div>

      {showKeyConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setShowKeyConfirm(false)}>
          <div className="bg-surface rounded-lg shadow-lg p-5 w-[360px] max-w-[90vw]" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-3">
              <i className="fas fa-exclamation-triangle text-yellow-500"></i>
              <span className="text-sm font-medium text-inverse">确认刷新 API Key</span>
            </div>
            <p className="text-xs text-muted mb-4">仅刷新当前流程的 API Key，刷新后原 API Key 失效。确认是否刷新？</p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowKeyConfirm(false)} className="px-3 py-1.5 text-xs text-muted border border-border-strong rounded hover:bg-surface-2">取消</button>
              <button
                onClick={async () => {
                  setShowKeyConfirm(false);
                  const key = crypto.randomUUID().replace(/-/g, '').slice(0, 16);
                  try {
                    const updated = await api.updateWorkflow(workflow.id, { api_key: key });
                    dispatch({ type: 'SET_WORKFLOW', payload: updated });
                  } catch (e) { alert('重新生成失败: ' + e.message); }
                }}
                className="px-3 py-1.5 text-xs text-white bg-accent rounded hover:bg-accent-strong"
              >确认刷新</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function copyTextToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text);
  }
  return new Promise((resolve, reject) => {
    const el = document.createElement('textarea');
    el.value = text;
    el.style.position = 'fixed'; el.style.left = '-9999px'; el.style.top = '-9999px';
    document.body.appendChild(el);
    el.focus(); el.select();
    try { document.execCommand('copy') ? resolve() : reject(new Error('execCommand failed')); }
    catch (e) { reject(e); }
    finally { document.body.removeChild(el); }
  });
}
