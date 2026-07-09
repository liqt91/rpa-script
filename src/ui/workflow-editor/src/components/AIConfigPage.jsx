import { useState, useEffect } from 'react';
import { api } from '../api';

const DEFAULT_COMMAND_CODE_GEN_PROMPT = `你是一名 RPA 开发专家。请根据下面的指令 JSON 定义，生成一个后端 Python handler 实现。

项目中的 handler 注册和运行方式如下，请严格遵循：

\`\`\`python
from ..registry import register_handler, Param

@register_handler(
    type="{{type}}",
    label="{{label}}",
    category="{{category}}",
    runtime="backend",
    icon="fa-circle",
    icon_color="text-gray-500",
    bg_color="bg-gray-50",
)
class {{ClassName}}Handler:
    params = [
        # 每个 Param(name, label, type, required=False, default=None, group="主属性", options=None)
        # type 可选：str-input, str-textarea, str-var, str-dropdown, str-element, int-number, bool-check, list-input, dict-input, any-expr, any-input
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
        # 读取参数：value = extra.get("paramName", default)

        # 执行业务逻辑...

        # 成功后必须更新 runner 状态
        runner.completed += 1
        runner.results.append({
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "status": "success",
            "result": {"{{type}}": value_or_summary},
        })
        await runner._emit({
            "type": "stepComplete",
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "result": {"{{type}}": value_or_summary},
        })
        return True
\`\`\`

可用上下文：
- runner.vars: dict，可读/写流程变量
- runner.results: list，已完成的步骤结果
- runner._emit(dict): 发送步骤事件
- instr.get("nodeId"): 当前节点 ID
- instr.get("extra"): dict，用户填写的参数值
- 如需浏览器通信，使用 await runner._send_and_wait(step_id, instr, timeout=10.0)

要求：
1. 使用 \`from ..registry import register_handler, Param\` 注册，不要使用虚构模块。
2. \`@register_handler\` 的 type、label、category 必须和 JSON 定义一致。
3. \`class\` 名使用大驼峰（如 OpenBrowserHandler）。
4. \`params\` 列表必须与 JSON 定义中的 params 完全一致（name、label、type、required、default、options）。
5. \`execute\` 必须是 \`@staticmethod async def execute(runner, cmd_type, step_id, instr)\`。
6. 从 \`instr.get("extra")\` 读取参数，不要用 instr.get("paramName") 直接读。
7. 代码只包含类定义和必要的 import，不要输出 markdown 代码块标记，不要额外说明文字。
8. 业务逻辑不要写占位代码，要根据指令用途写出真实可执行的逻辑。

JSON 定义：
{{definition}}
`;

const DEFAULT_SCENARIOS = [
  {
    id: 'command_code_gen',
    name: '指令代码生成',
    prompt: DEFAULT_COMMAND_CODE_GEN_PROMPT,
    enabled: true,
  },
];

export default function AIConfigPage() {
  const PROVIDER_MODELS = {
    deepseek: ['deepseek-v4-flash', 'deepseek-v4-pro'],
  };

  const [config, setConfig] = useState({
    provider: 'deepseek',
    model: 'deepseek-v4-flash',
    apiKey: '',
    enabled: true,
    scenarios: DEFAULT_SCENARIOS,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [testType, setTestType] = useState('inputElement');
  const [testResult, setTestResult] = useState('');
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    loadConfig();
  }, []);

  async function loadConfig() {
    try {
      setLoading(true);
      const data = await api.getLLMConfig();
      setConfig({
        provider: data.provider || 'deepseek',
        model: data.model || 'deepseek-v4-flash',
        apiKey: data.apiKey || '',
        enabled: data.enabled !== false,
        scenarios: data.scenarios?.length ? data.scenarios : DEFAULT_SCENARIOS,
      });
      setMessage('');
    } catch (e) {
      setMessage('加载失败: ' + e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setMessage('');
    try {
      await api.updateLLMConfig({
        provider: config.provider,
        model: config.model,
        apiKey: config.apiKey,
        enabled: config.enabled,
        scenarios: config.scenarios,
      });
      setMessage('已保存');
    } catch (e) {
      setMessage('保存失败: ' + e.message);
    } finally {
      setSaving(false);
    }
  }

  function updateScenario(id, field, value) {
    setConfig(prev => ({
      ...prev,
      scenarios: prev.scenarios.map(s => s.id === id ? { ...s, [field]: value } : s),
    }));
  }

  function addScenario() {
    const newId = `scenario_${Date.now()}`;
    setConfig(prev => ({
      ...prev,
      scenarios: [...prev.scenarios, { id: newId, name: '新场景', prompt: '', enabled: true }],
    }));
  }

  function removeScenario(id) {
    setConfig(prev => ({
      ...prev,
      scenarios: prev.scenarios.filter(s => s.id !== id),
    }));
  }

  async function handleTest(scenarioId) {
    setTesting(true);
    setTestResult('');
    try {
      const definition = {
        type: testType,
        label: '测试指令',
        category: '测试',
        runtime: 'backend',
        description: '用于测试 AI 生成的示例指令',
        params: [
          { name: 'url', label: 'URL', type: 'str-input', required: true },
          { name: 'timeout', label: '超时', type: 'int-number', default: 10 },
        ],
      };
      const res = await api.generateWithScenario(scenarioId, { definition });
      setTestResult(res.code || '（无返回代码）');
    } catch (e) {
      setTestResult('生成失败: ' + e.message);
    } finally {
      setTesting(false);
    }
  }

  if (loading) {
    return (
      <div className="p-6 text-gray-400">
        <i className="fas fa-circle-notch fa-spin mr-2"></i>加载中...
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl">
      <h1 className="text-xl font-semibold text-white mb-1">AI 配置</h1>
      <p className="text-gray-400 text-sm mb-6">配置直连 LLM（当前支持 DeepSeek）用于指令代码生成等场景。</p>

      {message && (
        <div className={`mb-4 p-3 rounded text-sm ${message.includes('失败') ? 'bg-red-900/30 text-red-300 border border-red-700' : 'bg-green-900/30 text-green-300 border border-green-700'}`}>
          {message}
        </div>
      )}

      <div className="space-y-6">
        {/* Provider & API Key */}
        <div className="bg-[#1e293b] border border-gray-700 rounded-xl p-5">
          <h2 className="text-sm font-medium text-gray-200 mb-4">模型配置</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1.5">服务商</label>
              <select
                value={config.provider}
                onChange={e => setConfig(prev => ({ ...prev, provider: e.target.value, model: PROVIDER_MODELS[e.target.value]?.[0] || prev.model }))}
                className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded text-sm text-white outline-none focus:border-blue-500"
              >
                <option value="deepseek">DeepSeek</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1.5">模型</label>
              <select
                value={config.model}
                onChange={e => setConfig(prev => ({ ...prev, model: e.target.value }))}
                className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded text-sm text-white outline-none focus:border-blue-500"
              >
                {PROVIDER_MODELS[config.provider]?.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1.5">API Key</label>
              <input
                type="password"
                value={config.apiKey}
                onChange={e => setConfig(prev => ({ ...prev, apiKey: e.target.value }))}
                placeholder="sk-..."
                className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded text-sm text-white outline-none focus:border-blue-500"
              />
            </div>
          </div>
          <div className="mt-4 flex items-center gap-2">
            <input
              type="checkbox"
              id="enabled"
              checked={config.enabled}
              onChange={e => setConfig(prev => ({ ...prev, enabled: e.target.checked }))}
              className="w-4 h-4 accent-blue-500"
            />
            <label htmlFor="enabled" className="text-sm text-gray-300">启用 AI 功能</label>
          </div>
        </div>

        {/* Scenarios */}
        <div className="bg-[#1e293b] border border-gray-700 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-medium text-gray-200">使用场景 & Prompt</h2>
            <button
              onClick={addScenario}
              className="text-xs px-2.5 py-1.5 rounded bg-blue-600 text-white hover:bg-blue-500 transition-colors"
            >
              + 新增场景
            </button>
          </div>

          <div className="space-y-4">
            {config.scenarios.map((s, idx) => (
              <div key={s.id} className="border border-gray-700 rounded-lg p-4 bg-[#0f172a]/50">
                <div className="flex items-center gap-3 mb-3">
                  <input
                    type="text"
                    value={s.name}
                    onChange={e => updateScenario(s.id, 'name', e.target.value)}
                    className="flex-1 px-2.5 py-1.5 bg-[#0f172a] border border-gray-600 rounded text-sm text-white outline-none focus:border-blue-500"
                    placeholder="场景名称"
                  />
                  <label className="flex items-center gap-1.5 text-xs text-gray-400">
                    <input
                      type="checkbox"
                      checked={s.enabled}
                      onChange={e => updateScenario(s.id, 'enabled', e.target.checked)}
                      className="accent-blue-500"
                    />
                    启用
                  </label>
                  {config.scenarios.length > 1 && (
                    <button
                      onClick={() => removeScenario(s.id)}
                      className="text-red-400 hover:text-red-300 text-xs px-2"
                    >
                      删除
                    </button>
                  )}
                </div>
                <div className="mb-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-gray-500">Prompt（可用 {'{{definition}}'} 等占位符）</span>
                    <span className="text-[10px] text-gray-600">ID: {s.id}</span>
                  </div>
                  <textarea
                    value={s.prompt}
                    onChange={e => updateScenario(s.id, 'prompt', e.target.value)}
                    rows={6}
                    className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded text-xs text-gray-200 font-mono outline-none focus:border-blue-500 resize-none"
                    placeholder="输入 prompt..."
                  />
                </div>
                {s.id === 'command_code_gen' && (
                  <div className="mt-3 pt-3 border-t border-gray-700/50">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs text-gray-500">测试指令类型:</span>
                      <input
                        type="text"
                        value={testType}
                        onChange={e => setTestType(e.target.value)}
                        className="w-32 px-2 py-1 bg-[#0f172a] border border-gray-600 rounded text-xs text-white outline-none focus:border-blue-500"
                      />
                      <button
                        onClick={() => handleTest(s.id)}
                        disabled={testing || !config.apiKey}
                        className="text-xs px-2.5 py-1.5 rounded bg-green-700/40 text-green-300 hover:bg-green-700/60 disabled:opacity-50 transition-colors"
                      >
                        {testing ? <i className="fas fa-circle-notch fa-spin"></i> : '测试生成'}
                      </button>
                    </div>
                    {testResult && (
                      <pre className="mt-2 p-3 bg-[#0a0f1a] rounded text-[11px] text-gray-300 font-mono overflow-auto max-h-64">
                        {testResult}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2 rounded bg-blue-600 text-white text-sm hover:bg-blue-500 disabled:opacity-50 transition-colors"
          >
            {saving ? <i className="fas fa-circle-notch fa-spin mr-2"></i> : null}
            {saving ? '保存中...' : '保存配置'}
          </button>
        </div>
      </div>
    </div>
  );
}
