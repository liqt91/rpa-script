import { useState, useEffect } from 'react';
import { useWorkflow } from '../store/WorkflowContext';

const PARAM_TYPES = [
  { value: 'text', label: '文本' },
  { value: 'number', label: '数字' },
  { value: 'bool', label: '布尔' },
  { value: 'list', label: '列表' },
  { value: 'dict', label: '字典' },
];

const PARAM_DIRECTIONS = [
  { value: 'in', label: '输入' },
  { value: 'out', label: '输出' },
];

function defaultValueForType(type) {
  switch (type) {
    case 'number': return 0;
    case 'bool': return false;
    case 'list': return [];
    case 'dict': return {};
    default: return '';
  }
}

function defaultDisplay(val, type) {
  if (val === undefined || val === null) return '';
  if (type === 'list' || type === 'dict') return typeof val === 'string' ? val : JSON.stringify(val);
  if (type === 'bool') return val ? '是' : '否';
  return String(val);
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
    setParams(prev => [...prev, { name: '', label: '', type: 'text', direction: 'in', default: '' }]);
  };

  const removeParam = (idx) => {
    setParams(prev => prev.filter((_, i) => i !== idx));
  };

  const validate = () => {
    const keys = new Set();
    for (const p of params) {
      if (!p.name || !p.name.trim()) return '参数名不能为空';
      if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(p.name)) {
        return `参数名 "${p.name}" 只能包含字母、数字和下划线，且不能以数字开头`;
      }
      const key = `${p.name.trim()}:${p.direction || 'in'}`;
      if (keys.has(key)) return `参数 "${p.name}" (${p.direction || 'in'}) 重复`;
      keys.add(key);
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
        direction: p.direction || 'in',
        default: p.default === undefined ? defaultValueForType(p.type) : p.default,
      }));
      await updateWorkflowParameters(cleaned);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const isBottom = variant === 'bottom';
  const Tag = isBottom ? 'div' : 'aside';
  const outerClass = isBottom
    ? 'flex-1 bg-white flex flex-col select-none overflow-hidden min-h-0'
    : 'w-[520px] bg-white border-l border-[#e8e8e8] flex flex-col shrink-0 select-none overflow-hidden';

  const inputClass = 'w-full px-1.5 py-1 border border-[#d9d9d9] rounded text-[11px] text-gray-700 outline-none focus:border-[#1677ff]';
  const selectClass = 'w-full px-1.5 py-1 border border-[#d9d9d9] rounded text-[11px] text-gray-700 outline-none focus:border-[#1677ff] bg-white';

  return (
    <Tag className={outerClass}>
      <div className="px-3 py-2 border-b border-[#e8e8e8] flex items-center justify-between shrink-0">
        <div>
          <h2 className="text-sm font-medium text-gray-700">流程参数</h2>
          <p className="text-[10px] text-gray-500">支持 ${'{name}'} 插值，输出参数运行时自动取值</p>
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

      <div className="flex-1 overflow-auto">
        {params.length === 0 ? (
          <div className="text-xs text-gray-400 py-10 text-center">
            暂无参数，点击"+ 添加"创建
          </div>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-[#fafafa] z-10">
              <tr className="border-b border-[#e8e8e8]">
                <th className="text-left px-2 py-1.5 font-medium text-gray-500 w-[80px]">变量名</th>
                <th className="text-left px-2 py-1.5 font-medium text-gray-500 w-[80px]">显示名</th>
                <th className="text-left px-2 py-1.5 font-medium text-gray-500 w-[80px]">输入/输出</th>
                <th className="text-left px-2 py-1.5 font-medium text-gray-500 w-[68px]">类型</th>
                <th className="text-left px-2 py-1.5 font-medium text-gray-500">默认值</th>
                <th className="text-center px-2 py-1.5 font-medium text-gray-500 w-[36px]"></th>
              </tr>
            </thead>
            <tbody>
              {params.map((p, idx) => (
                <tr key={idx} className="border-b border-[#f0f0f0] hover:bg-[#fafafa]">
                  <td className="px-2 py-1">
                    <input
                      value={p.name || ''}
                      onChange={(e) => updateParam(idx, 'name', e.target.value)}
                      placeholder="varName"
                      className={inputClass}
                    />
                  </td>
                  <td className="px-2 py-1">
                    <input
                      value={p.label || ''}
                      onChange={(e) => updateParam(idx, 'label', e.target.value)}
                      placeholder="显示名"
                      className={inputClass}
                    />
                  </td>
                  <td className="px-2 py-1">
                    <select
                      value={p.direction || 'in'}
                      onChange={(e) => updateParam(idx, 'direction', e.target.value)}
                      className={selectClass}
                    >
                      {PARAM_DIRECTIONS.map(d => (
                        <option key={d.value} value={d.value}>{d.label}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-2 py-1">
                    <select
                      value={p.type || 'text'}
                      onChange={(e) => updateParam(idx, 'type', e.target.value)}
                      className={selectClass}
                    >
                      {PARAM_TYPES.map(t => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-2 py-1">
                    {(p.direction || 'in') === 'out' ? (
                      <span className="text-[10px] text-gray-300 italic">运行时输出</span>
                    ) : p.type === 'bool' ? (
                      <select
                        value={p.default === true ? 'true' : 'false'}
                        onChange={(e) => updateParam(idx, 'default', e.target.value === 'true')}
                        className={selectClass}
                      >
                        <option value="true">是</option>
                        <option value="false">否</option>
                      </select>
                    ) : p.type === 'list' || p.type === 'dict' ? (
                      <input
                        value={defaultDisplay(p.default, p.type)}
                        onChange={(e) => updateParam(idx, 'default', e.target.value)}
                        placeholder={p.type === 'list' ? '[1,2,3]' : '{"k":"v"}'}
                        className={`${inputClass} font-mono`}
                      />
                    ) : (
                      <input
                        type={p.type === 'number' ? 'number' : 'text'}
                        value={p.default === undefined || p.default === null ? '' : p.default}
                        onChange={(e) => updateParam(idx, 'default', p.type === 'number' ? Number(e.target.value) : e.target.value)}
                        className={inputClass}
                      />
                    )}
                  </td>
                  <td className="px-2 py-1 text-center">
                    <button
                      onClick={() => removeParam(idx)}
                      className="text-red-400 hover:text-red-600 text-xs"
                      title="删除"
                    >
                      <i className="fas fa-trash-alt"></i>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Tag>
  );
}
