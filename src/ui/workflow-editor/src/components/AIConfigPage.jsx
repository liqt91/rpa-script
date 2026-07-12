import { useState, useEffect } from 'react';
import { api } from '../api';

const PROVIDER_MODELS = { deepseek: ['deepseek-v4-flash', 'deepseek-v4-pro'] };

const SCENARIO_META = {
  command_backend: {
    label: 'backend — Python handler', icon: 'fa-python',
    vars: [
      { v: '{{scaffold}}', d: 'Python handler 骨架代码 — 包含 @register_handler、params、参数读取、结果上报。AI 只需填充 # TODO 区域' },
    ],
  },
  command_extension_js: {
    label: 'extension — JS handler', icon: 'fa-js',
    vars: [
      { v: '{{definition_json}}', d: '指令的 JSON 定义（含 type、label、params 等）' },
      { v: '{{context}}', d: 'Handler 上下文 — "DOM handler" 或 "background handler"，决定 AI 使用 registerHandler 还是 registerBackgroundHandler' },
    ],
  },
  command_control: {
    label: 'control — 控制流 handler', icon: 'fa-code-branch',
    vars: [
      { v: '{{scaffold}}', d: '控制流 Python handler 骨架 — AI 需填充控制流逻辑' },
    ],
  },
};

export default function AIConfigPage() {
  const [config, setConfig] = useState({
    provider: 'deepseek', model: 'deepseek-v4-flash',
    apiKey: '', enabled: true, scenarios: [],
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [nav, setNav] = useState('model');

  useEffect(() => { loadConfig(); }, []);

  async function loadConfig() {
    try { setLoading(true);
      const data = await api.getLLMConfig();
      setConfig({ provider: data.provider || 'deepseek', model: data.model || 'deepseek-v4-flash', apiKey: data.apiKey || '', enabled: data.enabled !== false, scenarios: data.scenarios?.length ? data.scenarios : [] });
    } catch (e) { setMessage('加载失败: ' + e.message); }
    finally { setLoading(false); }
  }

  async function handleSave() {
    setSaving(true); setMessage('');
    try { await api.updateLLMConfig({ provider: config.provider, model: config.model, apiKey: config.apiKey, enabled: config.enabled, scenarios: config.scenarios }); setMessage('已保存'); }
    catch (e) { setMessage('保存失败: ' + e.message); }
    finally { setSaving(false); }
  }

  function updateScenario(id, field, value) {
    setConfig(prev => ({ ...prev, scenarios: prev.scenarios.map(s => s.id === id ? { ...s, [field]: value } : s) }));
  }

  if (loading) return <div className="p-6 text-gray-400"><i className="fas fa-circle-notch fa-spin mr-2" />加载中...</div>;

  const scenario = config.scenarios.find(s => s.id === nav);
  const meta = SCENARIO_META[nav];

  return (
    <div className="flex h-full max-h-full overflow-hidden">
      {/* Sidebar nav */}
      <div className="w-52 bg-[#0f172a] border-r border-gray-700 flex flex-col shrink-0">
        <div className="px-4 py-3 border-b border-gray-700">
          <h2 className="text-sm font-semibold text-white">AI 配置</h2>
        </div>
        <nav className="flex-1 py-1 overflow-y-auto">
          <NavItem icon="fa-cog" label="模型配置" active={nav === 'model'} onClick={() => setNav('model')} />
          <div className="px-4 pt-3 pb-1 text-[10px] text-gray-600 uppercase tracking-wider">场景 Prompt</div>
          {config.scenarios.map(s => (
            <NavItem key={s.id} icon={SCENARIO_META[s.id]?.icon || 'fa-circle'} label={SCENARIO_META[s.id]?.label || s.name} active={nav === s.id} onClick={() => setNav(s.id)} />
          ))}
        </nav>
        <div className="p-3 border-t border-gray-700">
          <button onClick={handleSave} disabled={saving}
            className="w-full py-1.5 rounded bg-blue-600 text-white text-sm hover:bg-blue-500 disabled:opacity-50">
            {saving ? <i className="fas fa-circle-notch fa-spin mr-1" /> : null}{saving ? '保存中' : '保存'}
          </button>
        </div>
      </div>

      {/* Content area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {message && (
          <div className={`mx-5 mt-3 p-3 rounded text-sm shrink-0 ${message.includes('失败') ? 'bg-red-900/30 text-red-300 border border-red-700' : 'bg-green-900/30 text-green-300 border border-green-700'}`}>{message}</div>
        )}
        {nav === 'model' ? <ModelConfig config={config} setConfig={setConfig} />
          : scenario ? <ScenarioEdit scenario={scenario} meta={meta} updateScenario={updateScenario} />
          : <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">未找到场景配置</div>}
      </div>
    </div>
  );
}

function NavItem({ icon, label, active, onClick }) {
  return (
    <button onClick={onClick}
      className={`w-full text-left px-4 py-2 flex items-center gap-2.5 text-sm transition-colors ${active ? 'bg-blue-600/20 text-blue-300 border-r-2 border-blue-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'}`}>
      <i className={`fas ${icon} w-4 text-center text-xs`} />
      <span className="truncate text-xs">{label}</span>
    </button>
  );
}

function ModelConfig({ config, setConfig }) {
  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-xl">
        <h3 className="text-base font-medium text-white mb-5">模型配置</h3>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1.5">服务商</label>
              <select value={config.provider}
                onChange={e => setConfig(prev => ({ ...prev, provider: e.target.value, model: PROVIDER_MODELS[e.target.value]?.[0] || prev.model }))}
                className="w-full px-3 py-2 bg-[#1e293b] border border-gray-600 rounded text-sm text-white outline-none focus:border-blue-500">
                <option value="deepseek">DeepSeek</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1.5">模型</label>
              <select value={config.model}
                onChange={e => setConfig(prev => ({ ...prev, model: e.target.value }))}
                className="w-full px-3 py-2 bg-[#1e293b] border border-gray-600 rounded text-sm text-white outline-none focus:border-blue-500">
                {PROVIDER_MODELS[config.provider]?.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1.5">API Key</label>
            <input type="password" value={config.apiKey}
              onChange={e => setConfig(prev => ({ ...prev, apiKey: e.target.value }))}
              placeholder="sk-..." className="w-full max-w-md px-3 py-2 bg-[#1e293b] border border-gray-600 rounded text-sm text-white outline-none focus:border-blue-500" />
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
            <input type="checkbox" checked={config.enabled}
              onChange={e => setConfig(prev => ({ ...prev, enabled: e.target.checked }))}
              className="w-4 h-4 accent-blue-500" />
            启用 AI 功能
          </label>
        </div>
      </div>
    </div>
  );
}

function ScenarioEdit({ scenario, meta, updateScenario }) {
  const [defs, setDefs] = useState([]);
  const [testType, setTestType] = useState('');
  const [testResult, setTestResult] = useState('');
  const [testPrompt, setTestPrompt] = useState('');
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    api.request('/api/commands/definitions').then(d => {
      setDefs(d || []);
      if (d?.length) setTestType(d[0].cmd);
    }).catch(() => {});
  }, []);

  async function handleTest() {
    const def = defs.find(d => d.cmd === testType);
    if (!def) return;
    setTesting(true); setTestResult(''); setTestPrompt('');
    try {
      const res = await api.generateWithScenario(scenario.id, { definition: def });
      setTestResult(res.code || '(empty)');
      setTestPrompt(res.prompt || '');
    } catch (e) { setTestResult('Error: ' + e.message); }
    finally { setTesting(false); }
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      {/* Top bar */}
      <div className="px-5 py-2.5 border-b border-gray-700 bg-[#0f172a] shrink-0 flex items-center gap-3">
        <h3 className="text-sm font-medium text-white flex items-center gap-2">
          <i className={`fas ${meta?.icon || 'fa-circle'} text-blue-400 text-xs`} />
          {meta?.label || scenario.name}
        </h3>
        <code className="text-[10px] text-gray-600 bg-[#1e293b] px-1.5 py-0.5 rounded">{scenario.id}</code>
        <label className="flex items-center gap-1.5 text-xs text-gray-400 ml-auto">
          <input type="checkbox" checked={scenario.enabled}
            onChange={e => updateScenario(scenario.id, 'enabled', e.target.checked)}
            className="accent-blue-500" />
          启用
        </label>
      </div>

      {/* Main content: prompt fills available space */}
      <div className="flex-1 overflow-y-auto p-5">
        <div className="flex flex-col gap-4" style={{ minHeight: 'calc(100vh - 180px)' }}>

          {/* Prompt — flex-1 fills remaining space */}
          <div className="flex-1 flex flex-col min-h-[300px]">
            <span className="text-xs text-gray-500 mb-1.5">Prompt 模板</span>
            <textarea value={scenario.prompt}
              onChange={e => updateScenario(scenario.id, 'prompt', e.target.value)}
              className="flex-1 w-full px-4 py-3 bg-[#1e293b] border border-gray-600 rounded text-sm text-gray-200 font-mono outline-none focus:border-blue-500 resize-none"
              placeholder="输入 prompt 模板..." />
          </div>

          {/* Placeholder docs */}
          {meta?.vars?.length > 0 && (
            <div className="bg-[#1e293b] border border-gray-700/50 rounded-lg p-4 shrink-0">
              <span className="text-xs font-medium text-gray-400">占位符说明</span>
              <div className="mt-2.5 space-y-2">
                {meta.vars.map(v => (
                  <div key={v.v} className="flex gap-3">
                    <code className="text-xs text-green-400 bg-[#0f172a] px-2 py-0.5 rounded shrink-0 font-mono">{v.v}</code>
                    <span className="text-xs text-gray-400 leading-relaxed">{v.d}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Test */}
          <div className="border-t border-gray-700 pt-4 shrink-0">
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-500">测试指令</span>
              <select value={testType} onChange={e => setTestType(e.target.value)}
                className="w-48 px-2.5 py-1.5 bg-[#1e293b] border border-gray-600 rounded text-xs text-white outline-none focus:border-blue-500">
                {defs.map(d => <option key={d.type} value={d.type}>{d.type} ({d.label})</option>)}
              </select>
              <button onClick={handleTest} disabled={testing || !scenario.enabled}
                className="text-xs px-3 py-1.5 rounded bg-green-700/40 text-green-300 hover:bg-green-700/60 disabled:opacity-50">
                {testing ? <i className="fas fa-circle-notch fa-spin mr-1" /> : <i className="fas fa-play mr-1 text-[9px]" />}
                {testing ? '生成中' : '测试'}
              </button>
            </div>
            {(testPrompt || testResult) && (
              <div className="mt-3 grid grid-cols-2 gap-3" style={{ height: '350px' }}>
                <div className="flex flex-col min-h-0">
                  <span className="text-[10px] text-gray-500 mb-1 shrink-0">填充后的 Prompt</span>
                  <pre className="flex-1 p-3 bg-[#0f172a] rounded text-[10px] text-gray-400 font-mono overflow-auto whitespace-pre-wrap">{testPrompt || '(empty)'}</pre>
                </div>
                <div className="flex flex-col min-h-0">
                  <span className="text-[10px] text-gray-500 mb-1 shrink-0">AI 返回结果</span>
                  <pre className="flex-1 p-3 bg-[#0f172a] rounded text-[10px] text-green-300 font-mono overflow-auto whitespace-pre-wrap">{testResult || '(empty)'}</pre>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
