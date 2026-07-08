import { useState, useEffect } from 'react';
import { api } from '../api';

export default function CommandEditor() {
  const [defs, setDefs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [editorText, setEditorText] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [buildResult, setBuildResult] = useState(null);

  useEffect(() => {
    loadDefinitions();
  }, []);

  async function loadDefinitions() {
    try {
      const res = await api.request('/api/commands/definitions');
      setDefs(res);
    } catch (e) {
      setError('加载失败: ' + e.message);
    }
  }

  function selectDef(d) {
    setSelected(d);
    setEditorText(JSON.stringify(d, null, 2));
    setStatus('');
    setError('');
    setBuildResult(null);
  }

  function createNew() {
    const type = prompt('指令类型名（英文）:');
    if (!type) return;
    const template = {
      type,
      label: type,
      category: '其他',
      runtime: 'extension',
      icon: 'fa-circle',
      iconColor: 'text-gray-500',
      bgColor: 'bg-gray-50',
      categoryOrder: 0,
      commandOrder: 0,
      description: '',
      enabled: true,
      params: [],
      handler: { kind: 'delegate', function: 'doClick' },
    };
    setSelected(template);
    setEditorText(JSON.stringify(template, null, 2));
    setStatus('');
    setError('');
  }

  async function saveDef() {
    if (!selected) return;
    try {
      const parsed = JSON.parse(editorText);
      await api.request(`/api/commands/definitions/${parsed.type}`, {
        method: 'PUT',
        body: JSON.stringify(parsed),
      });
      setStatus('已保存');
      setError('');
    } catch (e) {
      if (e instanceof SyntaxError) {
        setError('JSON 格式错误: ' + e.message);
      } else {
        setError('保存失败: ' + (e.response?.data?.detail || e.message));
      }
    }
  }

  async function runBuild() {
    try {
      setStatus('构建中...');
      const res = await api.request('/api/commands/definitions/build', {
        method: 'POST',
      });
      setBuildResult(res);
      setStatus('构建完成');
      setError('');
    } catch (e) {
      setError('构建失败: ' + e.message);
    }
  }

  const navGroupStyle = 'text-[10px] text-gray-500 uppercase tracking-wider mb-1 mt-3 px-1';

  return (
    <div className="flex-1 flex min-h-0">
      {/* Left panel — list */}
      <div className="w-56 bg-[#0f172a] border-r border-gray-700 flex flex-col shrink-0">
        <div className="px-3 py-3 border-b border-gray-700 flex items-center justify-between">
          <span className="text-sm font-medium text-gray-200">指令定义</span>
          <button
            onClick={createNew}
            className="text-xs text-blue-400 hover:text-blue-300"
          >
            + 新建
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
          {defs.map((d) => {
            const isCur = selected && selected.type === d.type;
            const badge = d.runtime === 'backend' ? '⬡' : d.runtime === 'emitter' ? '🔀' : '🌐';
            return (
              <button
                key={d.type}
                onClick={() => selectDef(d)}
                className={`w-full text-left px-2 py-1.5 rounded text-xs transition-colors ${
                  isCur
                    ? 'bg-blue-600/30 text-blue-200'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                }`}
              >
                <span className="mr-1.5">{badge}</span>
                {d.label}
                <span className="text-gray-600 ml-1">{d.type}</span>
              </button>
            );
          })}
        </div>
        <div className="px-2 py-2 border-t border-gray-700">
          <button
            onClick={runBuild}
            className="w-full text-xs px-2 py-1.5 rounded bg-green-700/40 text-green-300 hover:bg-green-700/60 transition-colors"
          >
            <i className="fas fa-hammer mr-1"></i>
            构建生成
          </button>
          {buildResult && (
            <div className="mt-1 text-[10px] text-gray-500">
              {buildResult.results?.map((r, i) => (
                <div key={i} className={r.returncode === 0 ? 'text-green-400' : 'text-red-400'}>
                  {r.script.split('/').pop()}: {r.returncode === 0 ? '✓' : '✗'}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right panel — editor */}
      <div className="flex-1 flex flex-col min-w-0">
        {!selected ? (
          <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
            选择一个指令定义或新建
          </div>
        ) : (
          <>
            <div className="px-4 py-2 border-b border-gray-700 flex items-center justify-between bg-[#0f172a] shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-200">{selected.label}</span>
                <code className="text-[10px] text-gray-500 bg-gray-800 px-1.5 py-0.5 rounded">
                  {selected.type}
                </code>
              </div>
              <div className="flex items-center gap-2">
                {status && (
                  <span className={`text-xs ${status.includes('失败') || error ? 'text-red-400' : 'text-green-400'}`}>
                    {status}
                  </span>
                )}
                {error && <span className="text-xs text-red-400">{error}</span>}
                <button
                  onClick={saveDef}
                  className="text-xs px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-500 transition-colors"
                >
                  保存
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-hidden">
              <textarea
                value={editorText}
                onChange={(e) => {
                  setEditorText(e.target.value);
                  setStatus('');
                }}
                className="w-full h-full bg-[#1e293b] text-gray-200 p-4 font-mono text-xs resize-none outline-none border-none"
                spellCheck={false}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
