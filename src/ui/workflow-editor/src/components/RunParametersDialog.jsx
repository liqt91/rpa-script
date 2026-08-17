import { useState, useEffect } from 'react';

function defaultInputValue(param) {
  if (param.default !== undefined && param.default !== null) return param.default;
  if (param.type === 'bool') return false;
  if (param.type === 'list') return '[]';
  if (param.type === 'dict') return '{}';
  return '';
}

export default function RunParametersDialog({ parameters, onConfirm, onCancel }) {
  // Only show input params (direction === 'in' or no direction specified)
  const inputParams = (parameters || []).filter(p => (p.direction || 'in') === 'in');
  const [values, setValues] = useState({});

  useEffect(() => {
    const init = {};
    for (const p of inputParams) {
      const def = defaultInputValue(p);
      // Serialize list/dict defaults to JSON string for textarea
      if ((p.type === 'list' || p.type === 'dict') && typeof def !== 'string') {
        init[p.name] = JSON.stringify(def);
      } else {
        init[p.name] = def;
      }
    }
    setValues(init);
  }, [parameters]);

  const setValue = (name, value) => {
    setValues(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const parsed = {};
    for (const p of inputParams) {
      const raw = values[p.name];
      if (p.type === 'number') {
        parsed[p.name] = raw === '' ? null : Number(raw);
      } else if (p.type === 'list' || p.type === 'dict') {
        try {
          parsed[p.name] = JSON.parse(raw);
        } catch {
          parsed[p.name] = p.type === 'list' ? [] : {};
        }
      } else {
        parsed[p.name] = raw;
      }
    }
    onConfirm(parsed);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <form
        onSubmit={handleSubmit}
        className="bg-surface rounded-lg shadow-xl w-[420px] max-w-[90vw] max-h-[80vh] flex flex-col"
      >
        <div className="px-4 py-3 border-b border-border">
          <h3 className="text-sm font-medium text-inverse">运行参数</h3>
          <p className="text-xs text-muted">请填写本次运行所需的参数</p>
        </div>
        <div className="p-4 space-y-3 overflow-y-auto">
          {inputParams.length === 0 ? (
            <p className="text-xs text-faint text-center py-4">此流程无需运行参数</p>
          ) : (
            inputParams.map((p) => (
              <div key={p.name}>
                <label className="block text-xs text-muted mb-1">
                  {p.label || p.name}
                  <span className="ml-1 text-[10px] text-faint">(${p.name})</span>
                </label>
                {p.type === 'bool' ? (
                  <select
                    value={values[p.name] ? 'true' : 'false'}
                    onChange={(e) => setValue(p.name, e.target.value === 'true')}
                    className="w-full px-2 py-1.5 border border-border-strong rounded text-sm text-body outline-none focus:border-accent"
                  >
                    <option value="true">是</option>
                    <option value="false">否</option>
                  </select>
                ) : p.type === 'list' || p.type === 'dict' ? (
                  <textarea
                    value={values[p.name] ?? ''}
                    onChange={(e) => setValue(p.name, e.target.value)}
                    placeholder={p.type === 'list' ? '[1, 2, 3]' : '{"key": "value"}'}
                    rows={3}
                    className="w-full px-2 py-1.5 border border-border-strong rounded text-sm text-body outline-none focus:border-accent font-mono"
                  />
                ) : (
                  <input
                    type={p.type === 'number' ? 'number' : 'text'}
                    value={values[p.name] ?? ''}
                    onChange={(e) => setValue(p.name, e.target.value)}
                    placeholder={p.default !== undefined ? String(p.default) : ''}
                    className="w-full px-2 py-1.5 border border-border-strong rounded text-sm text-body outline-none focus:border-accent"
                  />
                )}
              </div>
            ))
          )}
        </div>
        <div className="px-4 py-3 border-t border-border flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 text-xs text-muted border border-border-strong rounded hover:bg-surface-2"
          >
            取消
          </button>
          <button
            type="submit"
            className="px-3 py-1.5 text-xs text-white bg-accent rounded hover:bg-accent-strong"
          >
            开始运行
          </button>
        </div>
      </form>
    </div>
  );
}
