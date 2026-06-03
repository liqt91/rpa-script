import { useState, useEffect, useMemo, useRef, useCallback, Fragment } from 'react';
import { createPortal } from 'react-dom';
import { useWorkflow } from '../store/WorkflowContext';

// ─── Variable extraction helpers ─────────────────────────────────

function formatLocatorLabel(locator) {
  if (Array.isArray(locator)) {
    const first = typeof locator[0] === 'string' ? locator[0] : (locator[0].locator || locator[0].selector || '');
    return `[${locator.length}个备选] ${first}`.slice(0, 25);
  }
  return String(locator || '').slice(0, 25);
}

const VAR_FIELD_NAMES = ['varName', 'itemVar', 'indexVar', 'listVar', 'dataVar', 'errorVar', 'name', 'targetVar'];

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

function useAvailableVars(selectedNode, nodes) {
  return useMemo(() => {
    if (!selectedNode) return [];
    const currentOrder = selectedNode.order ?? Infinity;
    const seen = new Set();
    const result = [];
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
  }, [selectedNode, nodes]);
}

// Top-level DB columns that are shared across many element commands
const TOP_LEVEL_FIELDS = new Set(['locator', 'locator_type', 'method']);

function getCandidateValue(cand) {
  if (typeof cand === 'string') return cand;
  if (cand && typeof cand === 'object') {
    return cand.syntax || cand.locator || cand.selector || JSON.stringify(cand);
  }
  return String(cand);
}

function findElementByLocator(locatorValue, elements) {
  if (!locatorValue) return null;
  const str = String(locatorValue).trim();
  for (const el of elements) {
    if (el.locator && String(el.locator).trim() === str) {
      return el;
    }
    if (el.candidates && Array.isArray(el.candidates)) {
      for (const cand of el.candidates) {
        if (getCandidateValue(cand) === str) {
          return el;
        }
      }
    }
  }
  return null;
}

export default function NodeForm() {
  const { selectedNode, updateNode, elements, NODE_TYPE_MAP, containerNodes, nodes } = useWorkflow();
  const [form, setForm] = useState({});
  const [extra, setExtra] = useState({});
  const [entries, setEntries] = useState([{ host: '', elementId: null, locator: '', locatorType: 'css' }]);
  const [activeTab, setActiveTab] = useState('params');

  const command = selectedNode ? NODE_TYPE_MAP[selectedNode.type] : null;
  const availableVars = useAvailableVars(selectedNode, nodes);

  const hosts = useMemo(() => {
    const set = new Set();
    for (const e of elements) {
      if (e.hostname) set.add(e.hostname);
    }
    return Array.from(set).sort();
  }, [elements]);

  const getElementById = useCallback((id) => elements.find(e => e.id === id) || null, [elements]);
  const getElementsByHost = (host) => host ? elements.filter(e => e.hostname === host) : elements;

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

  // 构建保存用的 payload（统一为对象数组格式）
  const buildPayload = (nextForm, nextExtra, nextEntries) => {
    const f = nextForm || form;
    const e = nextExtra || extra;
    const ents = nextEntries || entries;

    const nonEmpty = (ents || []).filter(en => en.locator && String(en.locator).trim());
    const locatorPayload = nonEmpty.length > 0
      ? nonEmpty.map(en => ({
          locator: en.locator,
          locatorType: en.locatorType || 'css',
          elementId: en.elementId,
          host: en.host,
        }))
      : null;
    const locatorTypePayload = nonEmpty.length > 0 ? (nonEmpty[0].locatorType || 'css') : null;
    const firstElementId = nonEmpty.find(en => en.elementId)?.elementId || null;

    return {
      id: selectedNode.id,
      type: f.type,
      parent_id: (f.parent_id !== undefined && f.parent_id !== '') ? f.parent_id : null,
      locator: locatorPayload,
      locator_type: locatorTypePayload,
      method: null,
      action: f.type,
      element_id: firstElementId,
      extra: e,
    };
  };

  // 自动保存到本地
  const commit = (nextForm, nextExtra, nextEntries) => {
    if (!selectedNode) return;
    const payload = buildPayload(nextForm, nextExtra, nextEntries);
    console.log(`[NodeForm] autoSave id=${selectedNode.id} type=${payload.type}`, payload);
    updateNode(payload);
  };

  const prevNodeIdRef = useRef(null);

  useEffect(() => {
    if (selectedNode) {
      const nodeLoc = selectedNode.locator;
      let baseEntries;
      if (Array.isArray(nodeLoc)) {
        baseEntries = nodeLoc.map(item => {
          if (typeof item === 'string') {
            const matched = findElementByLocator(item, elements);
            return {
              host: matched?.hostname || '',
              elementId: matched?.id || null,
              locator: item,
              locatorType: selectedNode.locator_type || 'css',
            };
          }
          const locator = item.locator || item.selector || '';
          const locatorType = item.locatorType || item.type || selectedNode.locator_type || 'css';
          if (item.elementId) {
            const el = getElementById(item.elementId);
            return {
              host: item.host || el?.hostname || '',
              elementId: item.elementId,
              locator,
              locatorType,
            };
          }
          const matched = findElementByLocator(locator, elements);
          return {
            host: matched?.hostname || '',
            elementId: matched?.id || null,
            locator,
            locatorType,
          };
        });
      } else if (nodeLoc && typeof nodeLoc === 'string') {
        const matched = findElementByLocator(nodeLoc, elements);
        baseEntries = [{
          host: matched?.hostname || '',
          elementId: matched?.id || null,
          locator: nodeLoc,
          locatorType: selectedNode.locator_type || 'css',
        }];
      } else {
        baseEntries = [{ host: '', elementId: null, locator: '', locatorType: 'css' }];
      }
      queueMicrotask(() => {
        setEntries(baseEntries);
        setForm({
          type: selectedNode.type || '',
          parent_id: selectedNode.parent_id || '',
        });
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
        setEntries([{ host: '', elementId: null, locator: '', locatorType: 'css' }]);
      });
      prevNodeIdRef.current = null;
    }
  }, [selectedNode, elements, getElementById]);

  // 元素库加载后，为已有 locator 但尚未匹配到元素的 entry 做反向查找
  useEffect(() => {
    if (!elements.length) return;
    queueMicrotask(() => {
      setEntries(prev => {
        let changed = false;
        const next = prev.map(en => {
          if (en.elementId || !en.locator) return en;
          const matched = findElementByLocator(en.locator, elements);
          if (matched) {
            changed = true;
            return { ...en, elementId: matched.id, host: matched.hostname || '' };
          }
          return en;
        });
        return changed ? next : prev;
      });
    });
  }, [elements]);

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

  const addEntry = () => {
    const newEntries = [...entries, { host: '', elementId: null, locator: '', locatorType: 'css' }];
    setEntries(newEntries);
    commit(undefined, undefined, newEntries);
  };

  const removeEntry = (idx) => {
    const newEntries = entries.filter((_, i) => i !== idx);
    setEntries(newEntries);
    commit(undefined, undefined, newEntries);
  };

  const updateEntry = (idx, patch) => {
    const newEntries = entries.map((en, i) => i === idx ? { ...en, ...patch } : en);
    setEntries(newEntries);
    commit(undefined, undefined, newEntries);
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
              {hasLocator ? (
                <>
                  {entries.map((entry, idx) => {
                    const filteredEls = getElementsByHost(entry.host);
                    const selectedEl = getElementById(entry.elementId);
                    const candidates = selectedEl?.candidates || [];
                    return (
                      <div key={idx} className="bg-gray-50 border border-[#d9d9d9] rounded p-2.5 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-gray-600">元素 {idx + 1}</span>
                          {entries.length > 1 && (
                            <button
                              type="button"
                              onClick={() => removeEntry(idx)}
                              className="px-2 py-0.5 bg-red-50 text-red-500 rounded text-[10px] hover:bg-red-100"
                            >
                              删除
                            </button>
                          )}
                        </div>

                        {/* 站点筛选 */}
                        {hosts.length > 0 && (
                          <div>
                            <label className="block text-[10px] text-gray-400 mb-1">站点</label>
                            <select
                              value={entry.host}
                              onChange={(e) => updateEntry(idx, { host: e.target.value, elementId: null, locator: '' })}
                              className="w-full px-2 py-1.5 bg-white border border-[#d9d9d9] rounded text-sm text-gray-700 outline-none focus:border-[#1677ff]"
                            >
                              <option value="">全部站点</option>
                              {hosts.map(h => (
                                <option key={h} value={h}>{h}</option>
                              ))}
                            </select>
                          </div>
                        )}

                        {/* 元素库选择 */}
                        <div>
                          <label className="block text-[10px] text-gray-400 mb-1">元素库</label>
                          <select
                            value={entry.elementId || ''}
                            onChange={(e) => {
                              const elId = e.target.value ? parseInt(e.target.value, 10) : null;
                              const el = getElementById(elId);
                              const firstCand = el?.candidates?.[0];
                              const firstVal = firstCand ? getCandidateValue(firstCand) : '';
                              updateEntry(idx, { elementId: elId, locator: firstVal });
                            }}
                            className="w-full px-2 py-1.5 bg-white border border-[#d9d9d9] rounded text-sm text-gray-700 outline-none focus:border-[#1677ff]"
                          >
                            <option value="">-- 选择元素 --</option>
                            {filteredEls.map(el => (
                              <option key={el.id} value={el.id}>
                                {el.name} ({el.locator_type})
                              </option>
                            ))}
                          </select>
                        </div>

                        {/* 定位器下拉框（候选方案） */}
                        {selectedEl ? (
                          <LocatorDropdown
                            candidates={candidates}
                            value={entry.locator}
                            onChange={(val) => updateEntry(idx, { locator: val })}
                          />
                        ) : (
                          <div>
                            <label className="block text-[10px] text-gray-400 mb-1">定位器</label>
                            <input
                              type="text"
                              value={entry.locator}
                              onChange={(e) => updateEntry(idx, { locator: e.target.value })}
                              placeholder="输入定位器或选择元素"
                              className="w-full px-2 py-1.5 bg-white border border-[#d9d9d9] rounded text-sm text-gray-700 font-mono outline-none focus:border-[#1677ff]"
                            />
                          </div>
                        )}
                      </div>
                    );
                  })}

                  <button
                    type="button"
                    onClick={addEntry}
                    className="w-full px-3 py-2 bg-gray-100 text-gray-600 rounded text-xs hover:bg-gray-200 border border-dashed border-gray-300"
                  >
                    + 新增元素
                  </button>
                </>
              ) : (
                <div className="text-xs text-gray-400 py-6 text-center">该指令不涉及元素操作</div>
              )}
            </div>
          )}

          {activeTab === 'params' && (
            <div className="space-y-3">
              {extraFields.length > 0 ? (
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
                        const groupFields = extraFields.filter(f => (f.group || 'input') === group);
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
                                  />
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
                        #{n.order} {NODE_TYPE_MAP[n.type]?.label || n.type} - {formatLocatorLabel(n.locator)}
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
                #{v.node.order} {v.node.type}
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
 * Schema-driven control renderer (no label wrapper).
 * Supports: text, number, select, bool, textarea, varName
 */
function SchemaControl({ field, value, onChange, availableVars = [] }) {
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

    case 'locator':
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

