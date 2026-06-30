import { useState, useEffect } from 'react';
import { useWorkflow } from '../store/WorkflowContext';

const PARAM_TYPES = [
  { value: 'text', label: '文本' },
  { value: 'number', label: '数字' },
  { value: 'bool', label: '布尔' },
  { value: 'select', label: '下拉选项' },
];

function defaultValueForType(type) {
  switch (type) {
    case 'number': return 0;
    case 'bool': return false;
    default: return '';
  }
}

function parseOptions(raw) {
  if (!raw) return [];
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed;
    } catch {
      // fall through to comma split
    }
    return raw.split(',').map(v => v.trim()).filter(Boolean).map(v => ({ label: v, value: v }));
  }
  if (Array.isArray(raw)) return raw;
  return [];
}

function Field({ label, children, compact = false }) {
  return (
    <div>
      <label className={`block text-gray-400 mb-1 ${compact ? 'text-[10px]' : 'text-[10px]'}`}>{label}</label>
      {children}
    </div>
  );
}

export default function WorkflowParametersPanel({ variant = 'sidebar' }) {
  const { workflow, updateWorkflowParameters } = useWorkflow();
  const [params, setParams] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const list = Array.isArray(workflow?.parameters) ? workflow.parameters : [];
    setParams(list.map(p => ({ ...p })));
    setError(null);
  }, [workflow?.parameters]);

  const updateParam = (idx, field, value) => {
    setParams(prev => prev.map((p, i) => (i === idx ? { ...p, [field]: value } : p)));
  };

  const addParam = () => {
    setParams(prev => [...prev, { name: '', label: '', type: 'text', default: '' }]);
  };

  const removeParam = (idx) => {
    setParams(prev => prev.filter((_, i) => i !== idx));
  };

  const validate = () => {
    const names = new Set();
    for (const p of params) {
      if (!p.name || !p.name.trim()) return '参数名不能为空';
      if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(p.name)) {
        return `参数名 "${p.name}" 只能包含字母、数字和下划线，且不能以数字开头`;
      }
      if (names.has(p.name)) return `参数名 "${p.name}" 重复`;
      names.add(p.name);
    }
    return null;
  };

  const handleSave = async () => {
    const err = validate();
    if (err) {
      setError(err);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const cleaned = params.map(p => ({
        name: p.name.trim(),
        label: (p.label || p.name).trim(),
        type: p.type || 'text',
        default: p.default === undefined ? defaultValueForType(p.type) : p.default,
        ...(p.type === 'select' ? { options: parseOptions(p.options) } : {}),
      }));
      await updateWorkflowParameters(cleaned);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const renderParamCard = (p, idx, compact) => (
    <div
      key={idx}
      className={`border border-[#e8e8e8] rounded bg-white ${
        compact ? 'w-[260px] shrink-0 p-2.5 space-y-1.5' : 'p-3 space-y-2'
      }`}
    >
      <div className="flex justify-between items-center">
        <span className={`font-medium text-gray-500 ${compact ? 'text-[11px]' : 'text-xs'}`}>
          参数 #{idx + 1}
        </span>
        <button
          onClick={() => removeParam(idx)}
          className="text-[11px] text-red-500 hover:text-red-600"
        >
          删除
        </button>
      </div>
      <Field label="变量名（插值）" compact={compact}>
        <input
          value={p.name || ''}
          onChange={(e) => updateParam(idx, 'name', e.target.value)}
          placeholder="如 postUrl"
          className="w-full px-2 py-1 border border-[#d9d9d9] rounded text-xs text-gray-700 outline-none focus:border-[#1677ff]"
        />
      </Field>
      <Field label="显示名称" compact={compact}>
        <input
          value={p.label || ''}
          onChange={(e) => updateParam(idx, 'label', e.target.value)}
          placeholder="如 帖子链接"
          className="w-full px-2 py-1 border border-[#d9d9d9] rounded text-xs text-gray-700 outline-none focus:border-[#1677ff]"
        />
      </Field>
      <div className={compact ? 'grid grid-cols-2 gap-2' : 'space-y-2'}>
        <Field label="类型" compact={compact}>
          <select
            value={p.type || 'text'}
            onChange={(e) => updateParam(idx, 'type', e.target.value)}
            className="w-full px-2 py-1 border border-[#d9d9d9] rounded text-xs text-gray-700 outline-none focus:border-[#1677ff]"
          >
            {PARAM_TYPES.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </Field>
        <Field label="默认值" compact={compact}>
          {p.type === 'bool' ? (
            <select
              value={p.default === true ? 'true' : 'false'}
              onChange={(e) => updateParam(idx, 'default', e.target.value === 'true')}
              className="w-full px-2 py-1 border border-[#d9d9d9] rounded text-xs text-gray-700 outline-none focus:border-[#1677ff]"
            >
              <option value="true">是</option>
              <option value="false">否</option>
            </select>
          ) : p.type === 'select' ? (
            <input
              value={p.default || ''}
              onChange={(e) => updateParam(idx, 'default', e.target.value)}
              className="w-full px-2 py-1 border border-[#d9d9d9] rounded text-xs text-gray-700 outline-none focus:border-[#1677ff]"
            />
          ) : (
            <input
              type={p.type === 'number' ? 'number' : 'text'}
              value={p.default === undefined || p.default === null ? '' : p.default}
              onChange={(e) => updateParam(idx, 'default', p.type === 'number' ? Number(e.target.value) : e.target.value)}
              className="w-full px-2 py-1 border border-[#d9d9d9] rounded text-xs text-gray-700 outline-none focus:border-[#1677ff]"
            />
          )}
        </Field>
      </div>
      {p.type === 'select' && (
        <Field label="选项（JSON 或逗号分隔）" compact={compact}>
          <input
            value={typeof p.options === 'string' ? p.options : JSON.stringify(p.options || [])}
            onChange={(e) => updateParam(idx, 'options', e.target.value)}
            placeholder='["a","b"] 或 a,b'
            className="w-full px-2 py-1 border border-[#d9d9d9] rounded text-xs text-gray-700 outline-none focus:border-[#1677ff]"
          />
        </Field>
      )}
    </div>
  );

  const isBottom = variant === 'bottom';
  const Tag = isBottom ? 'div' : 'aside';
  const outerClass = isBottom
    ? 'flex-1 bg-white flex flex-col select-none overflow-hidden min-h-0'
    : 'w-[280px] bg-white border-l border-[#e8e8e8] flex flex-col shrink-0 select-none overflow-hidden';

  return (
    <Tag className={outerClass}>
      {isBottom ? (
        <>
          <div className="px-4 py-2 border-b border-[#e8e8e8] flex items-center justify-between shrink-0">
            <div>
              <h2 className="text-sm font-medium text-gray-700">流程参数</h2>
              <p className="text-[10px] text-gray-500">运行时通过弹窗输入，支持 ${name} 插值</p>
            </div>
            <div className="flex items-center gap-2">
              {error && (
                <span className="text-xs text-red-500 bg-red-50 rounded px-2 py-1">{error}</span>
              )}
              <button
                onClick={addParam}
                className="px-2.5 py-1 text-xs text-[#1677ff] border border-dashed border-[#1677ff] rounded hover:bg-blue-50"
              >
                + 添加
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-3 py-1 text-xs text-white bg-[#1677ff] rounded hover:bg-[#4096ff] disabled:opacity-50"
              >
                {saving ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-x-auto overflow-y-hidden">
            {params.length > 0 && (
              <div className="flex items-start gap-3 px-4 py-2 h-full">
                {params.map((p, idx) => renderParamCard(p, idx, true))}
              </div>
            )}
          </div>
        </>
      ) : (
        <>
          <div className="px-4 py-3 border-b border-[#e8e8e8]">
            <h2 className="text-sm font-medium text-gray-700">流程参数</h2>
            <p className="text-xs text-gray-500">运行时通过弹窗输入，支持 ${name} 插值</p>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {params.length === 0 && (
              <div className="text-xs text-gray-400 py-6 text-center">暂无流程参数</div>
            )}
            {params.map((p, idx) => renderParamCard(p, idx, false))}
            <button
              onClick={addParam}
              className="w-full py-1.5 text-xs text-[#1677ff] border border-dashed border-[#1677ff] rounded hover:bg-blue-50"
            >
              + 添加参数
            </button>
            {error && (
              <div className="text-xs text-red-500 bg-red-50 rounded px-2 py-1.5">{error}</div>
            )}
            <button
              onClick={handleSave}
              disabled={saving}
              className="w-full py-1.5 text-xs text-white bg-[#1677ff] rounded hover:bg-[#4096ff] disabled:opacity-50"
            >
              {saving ? '保存中...' : '保存参数'}
            </button>
          </div>
        </>
      )}
    </Tag>
  );
}
