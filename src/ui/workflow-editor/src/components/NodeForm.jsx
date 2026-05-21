import { useState, useEffect, useMemo, useRef } from 'react';
import { useWorkflow } from '../store/WorkflowContext';

// Top-level DB columns that are shared across many element commands
const TOP_LEVEL_FIELDS = new Set(['locator', 'locator_type', 'method']);

function getCandidateValue(cand) {
  if (typeof cand === 'string') return cand;
  if (cand && typeof cand === 'object') {
    return cand.syntax || cand.locator || cand.selector || JSON.stringify(cand);
  }
  return String(cand);
}

function getCandidateLabel(cand) {
  if (typeof cand === 'string') return cand;
  if (cand && typeof cand === 'object') {
    return cand.label || cand.syntax || cand.locator || cand.selector || JSON.stringify(cand);
  }
  return String(cand);
}

export default function NodeForm() {
  const { selectedNode, updateNode, elements, NODE_TYPE_MAP, containerNodes } = useWorkflow();
  const [form, setForm] = useState({});
  const [extra, setExtra] = useState({});
  const [selectedElementId, setSelectedElementId] = useState(null);
  const [elementId, setElementId] = useState(null);

  const command = selectedNode ? NODE_TYPE_MAP[selectedNode.type] : null;

  const selectedElement = useMemo(() => {
    return elements.find(e => e.id === selectedElementId) || null;
  }, [selectedElementId, elements]);

  // Separate schema fields into top-level vs extra
  const { topFields, extraFields } = useMemo(() => {
    if (!command?.fields) return { topFields: [], extraFields: [] };
    const top = [];
    const ext = [];
    for (const f of command.fields) {
      if (TOP_LEVEL_FIELDS.has(f.name)) {
        top.push(f);
      } else {
        ext.push(f);
      }
    }
    return { topFields: top, extraFields: ext };
  }, [command]);

  const hasLocator = topFields.some(f => f.name === 'locator');

  // 构建保存用的 payload
  const buildPayload = (nextForm, nextExtra, nextElementId) => {
    const f = nextForm || form;
    const e = nextExtra || extra;
    const elId = nextElementId !== undefined ? nextElementId : elementId;
    return {
      id: selectedNode.id,
      type: f.type,
      parent_id: f.parent_id ? (parseInt(f.parent_id, 10) || null) : null,
      locator: f.locator || null,
      locator_type: f.locator_type || null,
      method: f.method || null,
      action: f.type,
      element_id: elId,
      extra: e,
    };
  };

  // 自动保存到本地
  const commit = (nextForm, nextExtra, nextElementId) => {
    if (!selectedNode) return;
    const payload = buildPayload(nextForm, nextExtra, nextElementId);
    console.log(`[NodeForm] autoSave id=${selectedNode.id} type=${payload.type}`, payload);
    updateNode(payload);
  };

  useEffect(() => {
    if (selectedNode) {
      setForm({
        type: selectedNode.type || '',
        parent_id: selectedNode.parent_id || '',
        locator: selectedNode.locator || '',
        locator_type: selectedNode.locator_type || 'css',
        method: selectedNode.method || 'ele',
      });
      setExtra(selectedNode.extra && typeof selectedNode.extra === 'object'
        ? selectedNode.extra
        : (selectedNode.extra ? JSON.parse(selectedNode.extra) : {}));
      // 用 element_id 恢复选中的元素库元素
      const elId = selectedNode.element_id || null;
      setElementId(elId);
      setSelectedElementId(elId);
    } else {
      setForm({});
      setExtra({});
      setElementId(null);
      setSelectedElementId(null);
    }
  }, [selectedNode?.id]);

  const handleChange = (field, value) => {
    const newForm = { ...form, [field]: value };
    setForm(newForm);
    commit(newForm, extra);
  };

  const handleExtraChange = (field, value) => {
    const newExtra = { ...extra, [field]: value };
    setExtra(newExtra);
    commit(form, newExtra);
  };

  const handleElementSelect = (elId) => {
    const id = parseInt(elId, 10);
    if (!id) {
      // 切回手动输入，清空 element_id
      setSelectedElementId(null);
      setElementId(null);
      commit(form, extra, null);
      return;
    }
    const el = elements.find(e => e.id === id);
    if (!el) return;

    const candidates = el.candidates || [];
    const firstLocator = candidates.length > 0
      ? getCandidateValue(candidates[0])
      : (el.locator || '');

    console.log(`[NodeForm] elementSelected id=${id} candidates=${candidates.length}`);
    setSelectedElementId(id);
    setElementId(id);
    const newForm = {
      ...form,
      locator: firstLocator,
      locator_type: el.locator_type || 'css',
      method: el.method || 'ele',
    };
    setForm(newForm);
    commit(newForm, extra, id);
  };

  if (!selectedNode) {
    return (
      <aside className="w-[280px] bg-white border-l border-[#e8e8e8] flex items-center justify-center text-gray-400 text-sm shrink-0">
        选择一个节点以编辑属性
      </aside>
    );
  }

  return (
    <aside className="w-[280px] bg-white border-l border-[#e8e8e8] flex flex-col shrink-0 select-none overflow-hidden">
      <div className="px-4 py-3 border-b border-[#e8e8e8]">
        <h2 className="text-sm font-medium text-gray-700">节点属性</h2>
        <p className="text-xs text-gray-500">#{selectedNode.order} {command?.label || selectedNode.type}</p>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {/* Element selector */}
        {hasLocator && (
          <div>
            <label className="block text-xs text-gray-500 mb-1">从元素库选择</label>
            <select
              value={selectedElementId || ''}
              onChange={(e) => handleElementSelect(e.target.value)}
              className="w-full px-2 py-1.5 bg-[#fafafa] border border-[#d9d9d9] rounded text-sm text-gray-700 outline-none focus:border-[#1677ff]"
            >
              <option value="">-- 手动输入 --</option>
              {elements.map(el => (
                <option key={el.id} value={el.id}>
                  {el.name} ({el.locator_type})
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Parent selector */}
        {containerNodes.length > 0 && (
          <div>
            <label className="block text-xs text-gray-500 mb-1">父节点 (嵌套)</label>
            <select
              value={form.parent_id || ''}
              onChange={(e) => handleChange('parent_id', e.target.value)}
              className="w-full px-2 py-1.5 bg-[#fafafa] border border-[#d9d9d9] rounded text-sm text-gray-700 outline-none focus:border-[#1677ff]"
            >
              <option value="">无 (顶层)</option>
              {containerNodes.map(n => (
                <option key={n.id} value={n.id}>
                  #{n.order} {NODE_TYPE_MAP[n.type]?.label || n.type} - {(n.locator || '').slice(0, 25)}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Top-level shared fields (locator, locator_type, method) */}
        {hasLocator && (
          <>
            {/* Locator: 选择了元素库元素且有 candidates → 自定义下拉; 否则文本输入 */}
            {selectedElement && selectedElement.candidates && selectedElement.candidates.length > 0 ? (
              <LocatorDropdown
                candidates={selectedElement.candidates}
                value={form.locator || ''}
                onChange={(val) => handleChange('locator', val)}
              />
            ) : (
              <div>
                <label className="block text-xs text-gray-500 mb-1">定位器 locator</label>
                <input
                  type="text"
                  value={form.locator || ''}
                  onChange={(e) => handleChange('locator', e.target.value)}
                  placeholder="@data-testid=search-btn"
                  className="w-full px-2 py-1.5 bg-[#fafafa] border border-[#d9d9d9] rounded text-sm text-gray-700 font-mono outline-none focus:border-[#1677ff]"
                />
              </div>
            )}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs text-gray-500 mb-1">定位类型</label>
                <select
                  value={form.locator_type || 'css'}
                  onChange={(e) => handleChange('locator_type', e.target.value)}
                  className="w-full px-2 py-1.5 bg-[#fafafa] border border-[#d9d9d9] rounded text-sm text-gray-700 outline-none focus:border-[#1677ff]"
                >
                  <option value="css">css</option>
                  <option value="id">id</option>
                  <option value="class">class</option>
                  <option value="xpath">xpath</option>
                  <option value="text">text</option>
                  <option value="data-attr">data-attr</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">method</label>
                <select
                  value={form.method || 'ele'}
                  onChange={(e) => handleChange('method', e.target.value)}
                  className="w-full px-2 py-1.5 bg-[#fafafa] border border-[#d9d9d9] rounded text-sm text-gray-700 outline-none focus:border-[#1677ff]"
                >
                  <option value="ele">ele()</option>
                  <option value="eles">eles()</option>
                  <option value="s_ele">s_ele()</option>
                  <option value="s_eles">s_eles()</option>
                </select>
              </div>
            </div>
          </>
        )}

        {/* Dynamic extra fields from command schema */}
        {extraFields.map(field => (
          <SchemaField
            key={field.name}
            field={field}
            value={extra[field.name]}
            onChange={(v) => handleExtraChange(field.name, v)}
          />
        ))}
      </div>
    </aside>
  );
}

/**
 * Schema-driven field renderer.
 * Supports: text, number, select, bool, textarea, varName
 */
function SchemaField({ field, value, onChange }) {
  const inputClass = "w-full px-2 py-1.5 bg-[#fafafa] border border-[#d9d9d9] rounded text-sm text-gray-700 outline-none focus:border-[#1677ff]";
  const label = field.label || field.name;
  const currentValue = value !== undefined ? value : (field.default ?? '');

  switch (field.type) {
    case 'bool':
      return (
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={!!currentValue}
            onChange={(e) => onChange(e.target.checked)}
            className="w-4 h-4 accent-[#1677ff]"
          />
          <span className="text-sm text-gray-700">{label}</span>
        </label>
      );

    case 'select':
      return (
        <div>
          <label className="block text-xs text-gray-500 mb-1">{label}</label>
          <select
            value={currentValue}
            onChange={(e) => onChange(e.target.value)}
            className={inputClass}
          >
            {(field.options || []).map(opt => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        </div>
      );

    case 'number':
      return (
        <div>
          <label className="block text-xs text-gray-500 mb-1">{label}</label>
          <input
            type="number"
            value={currentValue}
            onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
            placeholder={field.placeholder || ''}
            className={inputClass}
            step={field.step || 'any'}
          />
        </div>
      );

    case 'textarea':
      return (
        <div>
          <label className="block text-xs text-gray-500 mb-1">{label}</label>
          <textarea
            value={currentValue}
            onChange={(e) => onChange(e.target.value)}
            rows={field.rows || 3}
            placeholder={field.placeholder || ''}
            className={`${inputClass} font-mono resize-none`}
          />
        </div>
      );

    case 'locator':
    case 'varName':
    case 'text':
    default:
      return (
        <div>
          <label className="block text-xs text-gray-500 mb-1">{label}</label>
          <input
            type="text"
            value={currentValue}
            onChange={(e) => onChange(e.target.value)}
            placeholder={field.placeholder || ''}
            className={inputClass}
          />
        </div>
      );
  }
}

/**
 * 自定义定位器下拉选择组件
 * 展示 label、matchCount、syntax，matchCount === 1 标绿色
 */
function LocatorDropdown({ candidates, value, onChange }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const selectedCand = candidates.find(c => getCandidateValue(c) === value) || candidates[0];

  return (
    <div ref={containerRef} className="relative">
      <label className="block text-xs text-gray-500 mb-1">定位器</label>
      {/* 触发区域 */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full px-2 py-1.5 bg-[#fafafa] border border-[#d9d9d9] rounded text-sm text-left outline-none focus:border-[#1677ff] hover:border-[#b3b3b3] transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-gray-700 truncate flex-1">
            {selectedCand && typeof selectedCand === 'object' ? (selectedCand.label || selectedCand.syntax || '') : (selectedCand || '')}
          </span>
          <i className={`fas fa-chevron-down text-[10px] text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}></i>
        </div>
      </button>

      {/* 下拉列表 */}
      {open && (
        <div className="absolute z-50 w-full mt-1 bg-white border border-[#d9d9d9] rounded shadow-lg max-h-60 overflow-y-auto">
          {candidates.map((cand, idx) => {
            const val = getCandidateValue(cand);
            const isSelected = val === value;
            const isObj = cand && typeof cand === 'object';
            const label = isObj ? (cand.label || '-') : '-';
            const matchCount = isObj ? (cand.matchCount ?? '-') : '-';
            const syntax = isObj ? (cand.syntax || val) : val;
            const isUnique = isObj && cand.matchCount === 1;

            return (
              <div
                key={idx}
                onClick={() => {
                  onChange(val);
                  setOpen(false);
                }}
                className={`px-3 py-2 cursor-pointer border-b border-gray-100 last:border-0 hover:bg-blue-50 ${
                  isSelected ? 'bg-blue-50' : ''
                }`}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-xs font-medium text-gray-700 truncate">{label}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                    isUnique ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                  }`}>
                    匹配: {matchCount}
                  </span>
                </div>
                <div className="text-[10px] text-gray-400 font-mono truncate">{syntax}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

