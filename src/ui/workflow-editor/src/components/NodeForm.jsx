import { useState, useEffect, useMemo, useRef, useCallback, Fragment } from 'react';
import { createPortal } from 'react-dom';
import { useWorkflow } from '../store/WorkflowContext';

// ─── Variable extraction helpers ─────────────────────────────────

const VAR_FIELD_NAMES = ['varName', 'itemVar', 'indexVar', 'listVar', 'dataVar', 'errorVar', 'name', 'targetVar', 'saveToVar', 'resultVar'];

function extractVarsFromNode(node) {
  const extra = node?.extra || {};
  const vars = [];
  for (const key of VAR_FIELD_NAMES) {
    const val = extra[key];
    if (val && typeof val === 'string' && val.trim()) {
      vars.push({ name: val.trim(), field: key, node });
    }
  }
  return vars;
}

function useAvailableVars(selectedNode, nodes, parameters = []) {
  return useMemo(() => {
    if (!selectedNode) return [];
    const currentOrder = selectedNode.order ?? Infinity;
    const seen = new Set();
    const result = [];
    // Workflow-level parameters are always available
    for (const p of parameters || []) {
      if (p.name && !seen.has(p.name)) {
        seen.add(p.name);
        result.push({ name: p.name, source: '流程参数' });
      }
    }
    for (const node of nodes) {
      if ((node.order ?? 0) >= currentOrder) continue;
      for (const v of extractVarsFromNode(node)) {
        if (!seen.has(v.name)) {
          seen.add(v.name);
          result.push(v);
        }
      }
    }
    return result;
  }, [selectedNode, nodes, parameters]);
}

// Primary element field is marked by the schema (replaces hard-coded element_name special case)
function findPrimaryElementField(fields) {
  return fields?.find(f => f.isPrimaryElement) || null;
}

export default function NodeForm() {
  const { selectedNode, updateNode, elements, NODE_TYPE_MAP, containerNodes, nodes, workflow } = useWorkflow();
  const [form, setForm] = useState({});
  const [extra, setExtra] = useState({});
  const [activeTab, setActiveTab] = useState('params');

  const command = selectedNode ? NODE_TYPE_MAP[selectedNode.type] : null;
  const availableVars = useAvailableVars(selectedNode, nodes, workflow?.parameters);

  // Schema-driven field buckets
  const primaryElementField = useMemo(() => findPrimaryElementField(command?.fields), [command]);
  const hasElementName = !!primaryElementField;
  const elementExtraFields = useMemo(
    () => (command?.fields || []).filter(f => (f.type === 'elementName' || f.type === 'elementNameList') && !f.isPrimaryElement),
    [command]
  );
  const elementListExtraFields = useMemo(
    () => elementExtraFields.filter(f => f.type === 'elementNameList'),
    [elementExtraFields]
  );
  const singleElementExtraFields = useMemo(
    () => elementExtraFields.filter(f => f.type === 'elementName'),
    [elementExtraFields]
  );
  const nonElementExtraFields = useMemo(
    () => (command?.fields || []).filter(f => f.type !== 'elementName' && f.type !== 'elementNameList'),
    [command]
  );

  // 构建保存用的 payload
  const buildPayload = (nextForm, nextExtra) => {
    const f = nextForm || form;
    const e = nextExtra || extra;
    return {
      id: selectedNode.id,
      type: f.type,
      parent_id: (f.parent_id !== undefined && f.parent_id !== '') ? f.parent_id : null,
      element_name: primaryElementField ? (f[primaryElementField.name] || null) : null,
      action: f.type,
      extra: e,
    };
  };

  // 自动保存到本地
  const commit = (nextForm, nextExtra) => {
    if (!selectedNode) return;
    const payload = buildPayload(nextForm, nextExtra);
    console.log(`[NodeForm] autoSave id=${selectedNode.id} type=${payload.type}`, payload);
    updateNode(payload);
  };

  const prevNodeIdRef = useRef(null);

  useEffect(() => {
    if (selectedNode) {
      queueMicrotask(() => {
        const initialForm = {
          type: selectedNode.type || '',
          parent_id: selectedNode.parent_id || '',
        };
        if (primaryElementField) {
          initialForm[primaryElementField.name] = selectedNode.element_name || '';
        }
        setForm(initialForm);
        setExtra(selectedNode.extra && typeof selectedNode.extra === 'object'
          ? selectedNode.extra
          : (selectedNode.extra ? JSON.parse(selectedNode.extra) : {}));
      });
      // 仅在真正切换节点时重置标签页，避免元素库刷新或节点更新导致当前标签丢失
      if (selectedNode.id !== prevNodeIdRef.current) {
        queueMicrotask(() => setActiveTab('params'));
        prevNodeIdRef.current = selectedNode.id;
      }
    } else {
      queueMicrotask(() => {
        setForm({});
        setExtra({});
      });
      prevNodeIdRef.current = null;
    }
  }, [selectedNode]);

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
        {command?.description && (
          <p className="text-[11px] text-gray-400 mt-1.5 leading-relaxed bg-gray-50 rounded px-2 py-1.5 border border-gray-100">
            {command.description}
          </p>
        )}
      </div>
      <div className="flex-1 overflow-y-auto">
        {/* Tab 导航 */}
        <div className="flex border-b border-[#e8e8e8]">
          {[
            { key: 'element', label: '元素' },
            { key: 'params', label: '参数' },
            { key: 'other', label: '其他' },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex-1 py-2 text-xs font-medium transition-colors ${
                activeTab === tab.key
                  ? 'text-[#1677ff] border-b-2 border-[#1677ff]'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-4 space-y-3">
          {activeTab === 'element' && (
            <div className="space-y-3">
              {hasElementName ? (
                <>
                  <div>
                    <label className="block text-[10px] text-gray-400 mb-1">{primaryElementField?.label || '选择元素'}</label>
                    <select
                      value={form[primaryElementField?.name] || ''}
                      onChange={(e) => handleChange(primaryElementField?.name, e.target.value || null)}
                      className="w-full px-2 py-1.5 bg-white border border-[#d9d9d9] rounded text-sm text-gray-700 outline-none focus:border-[#1677ff]"
                    >
                      <option value="">-- 选择元素 --</option>
                      {elements.map(el => (
                        <option key={el.name} value={el.name}>
                          {el.name}
                        </option>
                      ))}
                    </select>
                    {form[primaryElementField?.name] && (
                      <div className="mt-2 text-[11px] text-gray-500 bg-gray-50 rounded px-2 py-1.5 space-y-0.5">
                        <div>目标模式: {elements.find(e => e.name === form[primaryElementField?.name])?.target_mode || 'single'}</div>
                        <div className="font-mono truncate">
                          Web: {elements.find(e => e.name === form[primaryElementField?.name])?.web_selector || '-'}
                        </div>
                        <div className="font-mono truncate">
                          Drission: {elements.find(e => e.name === form[primaryElementField?.name])?.drission_selector || '-'}
                        </div>
                      </div>
                    )}
                  </div>
                  {singleElementExtraFields.map(field => (
                    <div key={field.name}>
                      <label className="block text-[10px] text-gray-400 mb-1">{field.label || field.name}</label>
                      <SchemaControl
                        field={field}
                        value={extra[field.name]}
                        onChange={(v) => handleExtraChange(field.name, v)}
                        availableVars={availableVars}
                        elements={elements}
                      />
                      {field.description && (
                        <p className="text-[11px] text-gray-400 mt-1 leading-relaxed">
                          {field.description}
                        </p>
                      )}
                    </div>
                  ))}
                  {elementListExtraFields.map(field => (
                    <ElementNameListField
                      key={field.name}
                      field={field}
                      value={extra[field.name]}
                      onChange={(v) => handleExtraChange(field.name, v)}
                      elements={elements}
                    />
                  ))}
                </>
              ) : (
                <div className="text-xs text-gray-400 py-6 text-center">该指令不涉及元素操作</div>
              )}
            </div>
          )}

          {activeTab === 'params' && (
            <div className="space-y-3">
              {nonElementExtraFields.length > 0 ? (
                <div className="border border-[#d9d9d9] rounded overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-[#fafafa]">
                      <tr>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 border-b border-[#e8e8e8] w-28">参数</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 border-b border-[#e8e8e8]">值</th>
                      </tr>
                    </thead>
                    <tbody>
                      {['input', 'output', 'advanced'].map(group => {
                        const groupFields = nonElementExtraFields.filter(f => (f.group || 'input') === group);
                        if (groupFields.length === 0) return null;
                        const groupLabel = group === 'input' ? '输入参数' : group === 'output' ? '输出参数' : '高级参数';
                        return (
                          <Fragment key={`group-${group}`}>
                            <tr className="bg-gray-50">
                              <td colSpan={2} className="px-3 py-1.5 text-[11px] font-medium text-gray-400 uppercase tracking-wide">
                                {groupLabel}
                              </td>
                            </tr>
                            {groupFields.map(field => (
                              <tr key={field.name} className="border-b border-[#f0f0f0] last:border-0 hover:bg-[#fafafa]">
                                <td className="px-3 py-2 text-xs text-gray-600 align-middle">{field.label || field.name}</td>
                                <td className="px-3 py-2 align-middle">
                                  <SchemaControl
                                    field={field}
                                    value={extra[field.name]}
                                    onChange={(v) => handleExtraChange(field.name, v)}
                                    availableVars={availableVars}
                                    elements={elements}
                                  />
                                  {field.description && (
                                    <p className="text-[11px] text-gray-400 mt-1 leading-relaxed">
                                      {field.description}
                                    </p>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-xs text-gray-400 py-6 text-center">该指令无参数</div>
              )}
            </div>
          )}

          {activeTab === 'other' && (
            <div className="space-y-3">
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
                        #{n.order} {NODE_TYPE_MAP[n.type]?.label || n.type}{n.element_name ? ` - ${n.element_name}` : ''}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <div>
                <label className="block text-xs text-gray-500 mb-1">节点类型</label>
                <div className="px-2 py-1.5 bg-gray-50 border border-[#d9d9d9] rounded text-sm text-gray-500">
                  {command?.label || selectedNode.type}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

/**
 * Detect if cursor is inside an unfinished variable reference.
 * Returns { start, end, prefix, hasBrace } or null.
 */
function findVarContext(value, cursorPos) {
  let i = cursorPos - 1;
  // skip variable-name chars left of cursor
  while (i >= 0 && /[a-zA-Z0-9_]/.test(value[i])) i--;
  // case: $name
  if (i >= 0 && value[i] === '$') {
    return { start: i, end: cursorPos, prefix: value.slice(i + 1, cursorPos), hasBrace: false };
  }
  // case: ${name
  if (i >= 0 && value[i] === '{' && i - 1 >= 0 && value[i - 1] === '$') {
    return { start: i - 1, end: cursorPos, prefix: value.slice(i + 1, cursorPos), hasBrace: true };
  }
  return null;
}

/**
 * Variable-aware input / textarea.
 * Typing '$' shows a dropdown of variables defined earlier in the workflow.
 */
function VarInput({ value, onChange, placeholder, className, vars, multiline = false, enableFullscreen = false }) {
  const inputRef = useRef(null);
  const [ctx, setCtx] = useState(null); // { start, end, prefix, hasBrace }
  const ctxRef = useRef(ctx);
  useEffect(() => { ctxRef.current = ctx; }, [ctx]);
  const [highlighted, setHighlighted] = useState(0);
  const containerRef = useRef(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [fullscreenValue, setFullscreenValue] = useState('');
  const fullscreenRef = useRef(null);

  const filtered = useMemo(() => {
    if (!ctx) return [];
    const p = ctx.prefix.toLowerCase();
    return vars.filter(v => v.name.toLowerCase().includes(p));
  }, [ctx, vars]);

  const close = useCallback(() => {
    setCtx(null);
    setHighlighted(0);
  }, []);

  const insertVar = useCallback((varName) => {
    if (!ctx || !inputRef.current) return;
    const val = String(value ?? '');
    const replacement = ctx.hasBrace ? varName : `{${varName}}`;
    const before = val.slice(0, ctx.start) + '$' + replacement;
    const after = val.slice(ctx.end);
    const newVal = before + after;
    const cursorPos = before.length;
    onChange(newVal);
    close();
    requestAnimationFrame(() => {
      inputRef.current.focus();
      inputRef.current.setSelectionRange(cursorPos, cursorPos);
    });
  }, [ctx, value, onChange, close]);

  const handleInput = useCallback(() => {
    const el = inputRef.current;
    if (!el) return;
    const cursorPos = el.selectionStart;
    const val = el.value;
    const found = findVarContext(val, cursorPos);
    if (found && vars.length > 0) {
      const current = ctxRef.current;
      if (
        current &&
        current.start === found.start &&
        current.end === found.end &&
        current.prefix === found.prefix &&
        current.hasBrace === found.hasBrace
      ) {
        // Same context (e.g. arrow keys) — keep current highlight.
        return;
      }
      setCtx(found);
      setHighlighted(0);
    } else {
      close();
    }
  }, [vars, close]);

  const handleKeyDown = useCallback((e) => {
    if (!ctx || filtered.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlighted(i => (i + 1) % filtered.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlighted(i => (i - 1 + filtered.length) % filtered.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      insertVar(filtered[highlighted].name);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      close();
    }
  }, [ctx, filtered, highlighted, insertVar, close]);

  // close dropdown on click outside
  useEffect(() => {
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        close();
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [close]);

  const commonProps = {
    ref: inputRef,
    value: value ?? '',
    onChange: (e) => {
      onChange(e.target.value);
      // after React updates the DOM, recheck variable context
      setTimeout(handleInput, 0);
    },
    onKeyDown: handleKeyDown,
    onClick: handleInput,
    onKeyUp: handleInput,
    placeholder,
    className,
  };

  const openFullscreen = () => {
    setFullscreenValue(value ?? '');
    setFullscreen(true);
  };

  const saveFullscreen = () => {
    onChange(fullscreenValue);
    setFullscreen(false);
  };

  const handleFullscreenKeyDown = (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const el = e.target;
      const start = el.selectionStart;
      const end = el.selectionEnd;
      const val = el.value;
      const newVal = val.substring(0, start) + '  ' + val.substring(end);
      setFullscreenValue(newVal);
      requestAnimationFrame(() => {
        el.selectionStart = el.selectionEnd = start + 2;
      });
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      saveFullscreen();
    }
  };

  useEffect(() => {
    if (fullscreen && fullscreenRef.current) {
      fullscreenRef.current.focus();
    }
  }, [fullscreen]);

  return (
    <div ref={containerRef} className="relative">
      {multiline ? (
        <div className="relative">
          <textarea {...commonProps} rows={3} />
          {enableFullscreen && (
            <button
              type="button"
              onClick={openFullscreen}
              className="absolute top-1 right-1 w-6 h-6 flex items-center justify-center text-gray-400 hover:text-gray-600 bg-white/80 border border-gray-200 rounded text-[10px]"
              title="全屏编辑"
            >
              <i className="fas fa-expand"></i>
            </button>
          )}
        </div>
      ) : (
        <input type="text" {...commonProps} />
      )}
      {ctx && filtered.length > 0 && (
        <div className="absolute z-50 left-0 right-0 mt-1 bg-white border border-[#d9d9d9] rounded shadow-lg max-h-48 overflow-y-auto">
          {filtered.map((v, idx) => (
            <div
              key={v.name}
              onClick={() => insertVar(v.name)}
              className={`px-3 py-2 cursor-pointer border-b border-gray-100 last:border-0 text-sm flex items-center justify-between ${
                idx === highlighted ? 'bg-blue-50 text-blue-700' : 'hover:bg-gray-50 text-gray-700'
              }`}
            >
              <span className="font-mono">${v.name}</span>
              <span className="text-[11px] text-gray-400 ml-2">
                {v.node ? `#${v.node.order} ${v.node.type}` : (v.source || '流程参数')}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Fullscreen editor modal */}
      {fullscreen && createPortal(
        <div
          className="fixed inset-0 z-[100] bg-black/60 flex items-center justify-center p-4"
          onMouseDown={(e) => e.stopPropagation()}
        >
          <div className="bg-[#1e1e1e] rounded-lg shadow-2xl w-full max-w-5xl h-[90vh] flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#333]">
              <span className="text-sm font-medium text-[#cccccc]">代码编辑器</span>
              <div className="flex items-center gap-2">
                <button type="button" onClick={saveFullscreen} className="text-xs px-3 py-1.5 bg-[#0e639c] text-white rounded hover:bg-[#1177bb]">保存</button>
                <button type="button" onClick={() => setFullscreen(false)} className="text-xs px-3 py-1.5 border border-[#555] text-[#cccccc] rounded hover:bg-[#333]">取消</button>
                <button type="button" onClick={() => setFullscreen(false)} className="ml-1 w-6 h-6 flex items-center justify-center text-[#858585] hover:text-[#cccccc]" title="关闭">
                  <i className="fas fa-times"></i>
                </button>
              </div>
            </div>
            {/* Context hint panel */}
            <div className="px-4 py-2 bg-[#252526] border-b border-[#333] text-[#858585] text-xs font-mono select-text">
              <div className="text-[#6a9955]"># 可用变量: {vars.map(v => v.name).join(', ') || '无'}</div>
              <div className="text-[#6a9955]">{'# _table[0][0]  第1行第1列;  _table[0]["A"]  第1行A列;  _table[0][1] = "x"  写入'}</div>
              <div className="text-[#6a9955]">{'# _table.dirty 自动标记，无需手动 _table_dirty; 也可用 _table_data["rows"][0]["A"]'}</div>
              <div className="text-[#6a9955]"># 返回值: _result = xxx</div>
            </div>
            <div className="flex-1 flex overflow-hidden">
              {/* Line numbers */}
              <div className="w-10 bg-[#1e1e1e] border-r border-[#333] py-3 text-right pr-2 text-[#858585] text-xs font-mono leading-6 select-none">
                {fullscreenValue.split('\n').map((_, i) => (
                  <div key={i}>{i + 1}</div>
                ))}
              </div>
              <textarea
                ref={fullscreenRef}
                value={fullscreenValue}
                onChange={(e) => setFullscreenValue(e.target.value)}
                onKeyDown={handleFullscreenKeyDown}
                className="flex-1 p-3 font-mono text-sm bg-[#1e1e1e] text-[#d4d4d4] border-0 outline-none resize-none leading-6"
                spellCheck={false}
              />
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}

/**
 * List of element names with add/remove buttons (minimum 1 item).
 */
function ElementNameListField({ field, value, onChange, elements = [] }) {
  const list = Array.isArray(value) ? value : [];

  const add = () => {
    onChange([...list, '']);
  };

  const remove = (idx) => {
    const next = list.filter((_, i) => i !== idx);
    onChange(next);
  };

  const update = (idx, val) => {
    const next = list.map((v, i) => (i === idx ? val : v));
    onChange(next);
  };

  return (
    <div className="space-y-2">
      <label className="block text-[10px] text-gray-400 mb-1">{field.label || field.name}</label>
      {list.map((name, idx) => (
        <div key={idx} className="flex items-center gap-2">
          <select
            value={name || ''}
            onChange={(e) => update(idx, e.target.value || '')}
            className="flex-1 px-2 py-1.5 bg-white border border-[#d9d9d9] rounded text-sm text-gray-700 outline-none focus:border-[#1677ff]"
          >
            <option value="">-- 选择元素 --</option>
            {elements.map(el => (
              <option key={el.name} value={el.name}>{el.name}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => remove(idx)}
            className="px-2 py-1 bg-red-50 text-red-500 rounded text-xs hover:bg-red-100"
            title="删除"
          >
            -
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={add}
        className="w-full px-2 py-1.5 bg-[#fafafa] border border-dashed border-[#d9d9d9] rounded text-xs text-gray-600 hover:border-[#1677ff] hover:text-[#1677ff]"
      >
        + 添加元素
      </button>
    </div>
  );
}

/**
 * Schema-driven control renderer (no label wrapper).
 * Supports: text, number, select, bool, textarea, varName, elementName
 */
function SchemaControl({ field, value, onChange, availableVars = [], elements = [] }) {
  const inputClass = "w-full px-2 py-1.5 bg-[#fafafa] border border-[#d9d9d9] rounded text-sm text-gray-700 outline-none focus:border-[#1677ff]";
  const currentValue = value !== undefined ? value : (field.default ?? '');

  switch (field.type) {
    case 'bool':
      return (
        <input
          type="checkbox"
          checked={!!currentValue}
          onChange={(e) => onChange(e.target.checked)}
          className="w-4 h-4 accent-[#1677ff]"
        />
      );

    case 'select':
      return (
        <select
          value={currentValue}
          onChange={(e) => onChange(e.target.value)}
          className={inputClass}
        >
          {(field.options || []).map(opt => {
            const isObj = opt && typeof opt === 'object';
            const val = isObj ? opt.value : opt;
            const label = isObj ? opt.label : opt;
            return <option key={val} value={val}>{label}</option>;
          })}
        </select>
      );

    case 'number':
      return (
        <input
          type="number"
          value={currentValue}
          onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
          placeholder={field.placeholder || ''}
          className={inputClass}
          step={field.step || 'any'}
        />
      );

    case 'textarea':
      return (
        <VarInput
          value={currentValue}
          onChange={onChange}
          placeholder={field.placeholder || ''}
          className={`${inputClass} font-mono resize-none`}
          vars={availableVars}
          multiline
          enableFullscreen={field.rows >= 4 || field.name === 'code'}
        />
      );

    case 'elementName':
      return (
        <select
          value={currentValue || ''}
          onChange={(e) => onChange(e.target.value || null)}
          className={inputClass}
        >
          <option value="">-- 选择元素 --</option>
          {elements.map(el => (
            <option key={el.name} value={el.name}>
              {el.name}
            </option>
          ))}
        </select>
      );

    case 'varName':
    case 'text':
    default:
      return (
        <VarInput
          value={currentValue}
          onChange={onChange}
          placeholder={field.placeholder || ''}
          className={inputClass}
          vars={availableVars}
        />
      );
  }
}
