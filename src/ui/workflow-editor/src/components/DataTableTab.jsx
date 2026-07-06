import { useState, useEffect, useRef, useCallback } from 'react';

const DEFAULT_COLUMNS = [
  { name: 'A', type: 'text' },
  { name: 'B', type: 'text' },
  { name: 'C', type: 'text' },
  { name: 'D', type: 'text' },
  { name: 'E', type: 'text' },
];

function padTable(t) {
  if (!t) return { name: 'default', columns: [...DEFAULT_COLUMNS], rows: Array(30).fill({}) };
  const columns = [...(t.columns || [])];
  while (columns.length < 5) {
    const maxCode = columns.reduce((max, c) => {
      const code = c.name.charCodeAt(0);
      return code > max ? code : max;
    }, 64);
    columns.push({ name: String.fromCharCode(maxCode + 1), type: 'text' });
  }
  const rows = [...(t.rows || [])];
  while (rows.length < 30) {
    rows.push({});
  }
  return { ...t, columns, rows };
}

function parseCSV(text) {
  const lines = text.trim().split('\n');
  if (lines.length === 0) return { columns: [], rows: [] };
  const headers = lines[0].split(',').map(h => h.trim());
  const columns = headers.map(h => ({ name: h, type: 'text' }));
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const values = lines[i].split(',').map(v => v.trim());
    const row = {};
    headers.forEach((h, idx) => {
      row[h] = values[idx] ?? '';
    });
    rows.push(row);
  }
  return { columns, rows };
}

function toCSV(table) {
  const headers = (table.columns || []).map(c => c.name);
  const lines = [headers.join(',')];
  for (const row of (table.rows || [])) {
    lines.push(headers.map(h => row[h] ?? '').join(','));
  }
  return lines.join('\n');
}

/** Copy selected cells as TSV (tab-separated) — pastes naturally into Excel/Sheets */
function copyCellsAsTSV(rows, columns, selected) {
  if (selected.size === 0) return;
  const coords = Array.from(selected).map(k => {
    const [r, c] = k.split(',').map(Number);
    return { r, c };
  });
  const minR = Math.min(...coords.map(x => x.r));
  const maxR = Math.max(...coords.map(x => x.r));
  const minC = Math.min(...coords.map(x => x.c));
  const maxC = Math.max(...coords.map(x => x.c));
  const lines = [];
  for (let r = minR; r <= maxR; r++) {
    const line = [];
    for (let c = minC; c <= maxC; c++) {
      if (selected.has(`${r},${c}`)) {
        const colName = columns[c]?.name;
        const val = (rows[r] && colName) ? (rows[r][colName] ?? '') : '';
        // Escape tabs/newlines within cell values
        line.push(String(val).replace(/\t/g, ' ').replace(/\n/g, ' '));
      } else {
        line.push('');
      }
    }
    lines.push(line.join('\t'));
  }
  const text = lines.join('\n');
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).catch(() => {});
  } else {
    const el = document.createElement('textarea');
    el.value = text;
    el.style.position = 'fixed';
    el.style.left = '-9999px';
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    document.body.removeChild(el);
  }
}

export default function DataTableTab({ wfId }) {
  const [table, setTable] = useState(null);
  const [toast, setToast] = useState(null);
  const [selectedCells, setSelectedCells] = useState(new Set());
  const [editingCell, setEditingCell] = useState(null); // "ri,ci" or null
  const selectionAnchor = useRef(null); // "ri,ci" for shift+click range
  const editingInitialRef = useRef(''); // value before edit started
  const debounceRef = useRef(null);
  const skipNextSaveRef = useRef(false);
  const fileInputRef = useRef(null);
  const gridRef = useRef(null);

  const STORAGE_KEY = `workflow_table_${wfId}`;

  // Auto-scroll to bottom when rows grow
  useEffect(() => {
    if (!gridRef.current || !table) return;
    const el = gridRef.current;
    const isAtBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
    if (isAtBottom) {
      el.scrollTop = el.scrollHeight;
    }
  }, [table?.rows?.length]);

  // Load from localStorage
  useEffect(() => {
    if (!wfId) return;
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        setTable(padTable(JSON.parse(raw)));
      } else {
        setTable(padTable({ name: 'default', columns: [...DEFAULT_COLUMNS], rows: [] }));
      }
    } catch {
      setTable(padTable({ name: 'default', columns: [...DEFAULT_COLUMNS], rows: [] }));
    }
  }, [wfId]);

  // Listen for runtime table updates
  useEffect(() => {
    if (!wfId) return;
    const handler = (e) => {
      if (e.detail?.wfId === wfId && e.detail?.tableData) {
        skipNextSaveRef.current = true;
        setTable(padTable(e.detail.tableData));
      }
    };
    window.addEventListener('runtime-table-update', handler);
    return () => window.removeEventListener('runtime-table-update', handler);
  }, [wfId]);

  // Save to localStorage (debounced)
  useEffect(() => {
    if (!table || !wfId) return;
    if (skipNextSaveRef.current) {
      skipNextSaveRef.current = false;
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        name: table.name,
        columns: table.columns,
        rows: (table.rows || []).filter(r => Object.keys(r).length > 0),
      }));
    }, 500);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [table, wfId]);

  // Global keyboard: Ctrl+C, Escape
  useEffect(() => {
    const onKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'c') {
        if (selectedCells.size > 0 && !editingCell) {
          e.preventDefault();
          copyCellsAsTSV(table?.rows || [], table?.columns || [], selectedCells);
          showToast(`已复制 ${selectedCells.size} 个单元格`);
        }
      }
      if (e.key === 'Escape') {
        setSelectedCells(new Set());
        selectionAnchor.current = null;
        setEditingCell(null);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [selectedCells, editingCell, table]);

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 2000);
  };

  const updateTable = (updater) => {
    if (!table) return;
    const updated = { ...table };
    updater(updated);
    setTable(updated);
  };

  const addColumn = () => {
    updateTable(table => {
      const cols = [...(table.columns || [])];
      const maxCharCode = cols.reduce((max, c) => {
        const code = c.name.charCodeAt(0);
        return code > max ? code : max;
      }, 64);
      const nextName = String.fromCharCode(maxCharCode + 1);
      cols.push({ name: nextName, type: 'text' });
      table.columns = cols;
    });
  };

  const removeColumn = (colIndex) => {
    if (!confirm('确定删除该列？列内数据将一并删除。')) return;
    updateTable(table => {
      const cols = [...(table.columns || [])];
      const removedName = cols[colIndex]?.name;
      cols.splice(colIndex, 1);
      table.columns = cols;
      table.rows = (table.rows || []).map(row => {
        const copy = { ...row };
        delete copy[removedName];
        return copy;
      });
    });
    setSelectedCells(new Set());
  };

  const renameColumn = (colIndex, newName) => {
    const oldName = table.columns[colIndex]?.name;
    if (!oldName || oldName === newName) return;
    updateTable(table => {
      const cols = [...table.columns];
      cols[colIndex] = { ...cols[colIndex], name: newName };
      table.columns = cols;
      table.rows = (table.rows || []).map(row => {
        const copy = { ...row };
        if (oldName in copy) {
          copy[newName] = copy[oldName];
          delete copy[oldName];
        }
        return copy;
      });
    });
  };

  const addRow = () => {
    updateTable(table => {
      table.rows = [...(table.rows || []), {}];
    });
  };

  const removeRow = (rowIndex) => {
    updateTable(table => {
      const rows = [...(table.rows || [])];
      rows.splice(rowIndex, 1);
      table.rows = rows;
    });
    setSelectedCells(new Set());
  };

  const updateCell = (rowIndex, colName, value) => {
    updateTable(table => {
      const rows = [...(table.rows || [])];
      while (rows.length <= rowIndex) rows.push({});
      rows[rowIndex] = { ...rows[rowIndex], [colName]: value };
      table.rows = rows;
    });
  };

  const handleImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = parseCSV(text);
      setTable(padTable(parsed));
      showToast('导入成功');
    } catch {
      showToast('导入失败', 'error');
    } finally {
      e.target.value = '';
    }
  };

  const handleExport = () => {
    try {
      const csv = toCSV(table || { columns: [], rows: [] });
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${table?.name || 'data'}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      showToast('导出成功');
    } catch {
      showToast('导出失败', 'error');
    }
  };

  const handleClear = () => {
    if (!confirm('确定清空所有行数据？列结构将保留。')) return;
    setTable(padTable({ ...table, rows: [] }));
    showToast('已清空');
  };

  const handleRefresh = () => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        setTable(padTable(JSON.parse(raw)));
      } else {
        setTable(padTable({ name: 'default', columns: [...DEFAULT_COLUMNS], rows: [] }));
      }
      showToast('已刷新');
    } catch {
      showToast('刷新失败', 'error');
    }
  };

  // ─── Cell selection & editing ───────────────────────────────────────

  const handleCellClick = useCallback((ri, ci, e) => {
    e.preventDefault();
    const key = `${ri},${ci}`;

    if (e.shiftKey && selectionAnchor.current) {
      // Range select
      const [ar, ac] = selectionAnchor.current.split(',').map(Number);
      const rMin = Math.min(ar, ri), rMax = Math.max(ar, ri);
      const cMin = Math.min(ac, ci), cMax = Math.max(ac, ci);
      const next = new Set();
      const cols = table?.columns || [];
      for (let r = rMin; r <= rMax; r++) {
        for (let c = cMin; c <= cMax; c++) {
          if (c < cols.length) next.add(`${r},${c}`);
        }
      }
      setSelectedCells(next);
      setEditingCell(null);
    } else if (e.ctrlKey || e.metaKey) {
      // Toggle single cell — functional update avoids stale closure
      setSelectedCells(prev => {
        const next = new Set(prev);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        return next;
      });
      selectionAnchor.current = key;
      setEditingCell(null);
    } else {
      // Single select
      setSelectedCells(new Set([key]));
      selectionAnchor.current = key;
      setEditingCell(null);
    }
  }, [table]);

  const handleCellDoubleClick = useCallback((ri, ci) => {
    const colName = table?.columns?.[ci]?.name;
    const val = colName ? (table?.rows?.[ri]?.[colName] ?? '') : '';
    setEditingCell(`${ri},${ci}`);
    // Store initial value for comparison on blur
    editingInitialRef.current = String(val);
  }, [table]);

  if (!table) return <div className="p-4 text-sm text-slate-400">加载中...</div>;

  const columns = table.columns || [];
  const rows = table.rows || [];
  const isSelected = (ri, ci) => selectedCells.has(`${ri},${ci}`);

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-slate-200 bg-white shrink-0">
        <span className="text-xs text-slate-400 font-medium mr-1">数据表格</span>
        <div className="w-px h-4 bg-slate-200"></div>
        <button onClick={addColumn} className="text-[11px] px-2.5 py-1.5 border border-slate-200 rounded-md hover:border-blue-300 hover:text-blue-600 hover:bg-blue-50/50 transition-colors">+ 列</button>
        <button onClick={addRow} className="text-[11px] px-2.5 py-1.5 border border-slate-200 rounded-md hover:border-blue-300 hover:text-blue-600 hover:bg-blue-50/50 transition-colors">+ 行</button>
        <div className="w-px h-4 bg-slate-200"></div>
        <button onClick={() => fileInputRef.current?.click()} className="text-[11px] px-2.5 py-1.5 border border-slate-200 rounded-md hover:border-slate-300 hover:bg-slate-50 transition-colors">导入</button>
        <input ref={fileInputRef} type="file" accept=".csv" className="hidden" onChange={handleImport} />
        <button onClick={handleExport} className="text-[11px] px-2.5 py-1.5 border border-slate-200 rounded-md hover:border-slate-300 hover:bg-slate-50 transition-colors">导出</button>
        <button onClick={handleRefresh} className="text-[11px] px-2.5 py-1.5 border border-slate-200 rounded-md hover:border-slate-300 hover:bg-slate-50 transition-colors" title="从本地存储重新加载">
          <i className="fas fa-sync-alt text-[10px] mr-1"></i>刷新
        </button>
        <div className="flex-1"></div>
        {selectedCells.size > 0 && (
          <span className="text-[11px] text-blue-500">{selectedCells.size} 个单元格已选中</span>
        )}
        <button onClick={handleClear} className="text-[11px] px-2.5 py-1.5 border border-red-200 rounded-md text-red-500 hover:bg-red-50 hover:border-red-300 transition-colors">清空</button>
      </div>

      {/* Grid */}
      <div
        ref={gridRef}
        className="flex-1 overflow-auto"
        onMouseDown={(e) => {
          // Click on empty area clears selection
          if (e.target === e.currentTarget) {
            setSelectedCells(new Set());
            selectionAnchor.current = null;
            setEditingCell(null);
          }
        }}
      >
        {!columns.length ? (
          <div className="text-xs text-slate-400 p-4 text-center">无数据</div>
        ) : (
          <table className="w-full border-collapse text-xs">
            <thead className="sticky top-0 z-10">
              <tr>
                <th className="w-10 h-9 bg-slate-700 text-slate-300 font-medium text-center border-r border-slate-600 text-[11px]">#</th>
                {columns.map((col, ci) => (
                  <th key={ci} className="bg-slate-700 text-white font-medium border-r border-slate-600 min-w-[88px] relative group last:border-r-0">
                    <div className="flex items-center">
                      <input
                        className="w-full px-3 py-2 bg-transparent text-center outline-none font-medium text-[11px] placeholder-slate-400"
                        value={col.name}
                        onChange={(e) => renameColumn(ci, e.target.value)}
                      />
                      <button
                        onClick={() => removeColumn(ci)}
                        className="opacity-0 group-hover:opacity-100 shrink-0 w-6 h-6 flex items-center justify-center text-slate-300 hover:text-red-400 transition-colors"
                        title="删除列"
                      >
                        <i className="fas fa-times text-[9px]"></i>
                      </button>
                    </div>
                  </th>
                ))}
                <th className="w-8 bg-slate-700 border-l border-slate-600">
                  <button onClick={addColumn} className="w-full h-full flex items-center justify-center text-slate-300 hover:text-white hover:bg-slate-600 transition-colors" title="添加列">
                    <i className="fas fa-plus text-[10px]"></i>
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr
                  key={ri}
                  className={`group transition-colors ${ri % 2 === 0 ? 'bg-white' : 'bg-slate-50/70'}`}
                >
                  <td className="border-t border-slate-100 bg-slate-50 text-center text-slate-400 text-[11px] font-mono relative w-10">
                    {ri + 1}
                    <button
                      onClick={() => removeRow(ri)}
                      className="absolute left-0.5 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 w-5 h-5 flex items-center justify-center text-slate-300 hover:text-red-500 transition-all rounded"
                      title="删除行"
                    >
                      <i className="fas fa-times text-[9px]"></i>
                    </button>
                  </td>
                  {columns.map((col, ci) => {
                    const sel = isSelected(ri, ci);
                    const editing = editingCell === `${ri},${ci}`;
                    const val = row[col.name] ?? '';
                    return (
                      <td
                        key={ci}
                        className={`border-t border-slate-100 min-w-[88px] select-none cursor-cell ${sel ? 'bg-blue-100' : ''}`}
                        onClick={(e) => handleCellClick(ri, ci, e)}
                        onDoubleClick={() => handleCellDoubleClick(ri, ci)}
                      >
                        {editing ? (
                          <input
                            autoFocus
                            className="w-full px-3 py-2 min-h-[30px] text-slate-700 bg-white ring-2 ring-inset ring-blue-400 outline-none text-xs"
                            defaultValue={String(val)}
                            onBlur={(e) => {
                              const newVal = e.target.value;
                              const colName = table?.columns?.[ci]?.name;
                              if (colName && newVal !== editingInitialRef.current) {
                                updateCell(ri, colName, newVal);
                              }
                              setEditingCell(null);
                            }}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') { e.preventDefault(); e.target.blur(); }
                              if (e.key === 'Escape') { editingInitialRef.current = String(val); e.target.blur(); }
                              if (e.key === 'Tab') { e.preventDefault(); e.target.blur(); }
                            }}
                          />
                        ) : (
                          <div className={`px-3 py-2 min-h-[30px] text-slate-700 ${sel ? 'font-medium' : ''}`}>
                            {val || '\u00A0'}
                          </div>
                        )}
                      </td>
                    );
                  })}
                  <td className="border-t border-slate-100 w-8" />
                </tr>
              ))}
              <tr>
                <td
                  className="border-t-2 border-slate-200 bg-slate-50/80 text-center text-slate-400 cursor-pointer hover:bg-blue-50 hover:text-blue-500 transition-colors"
                  onClick={addRow}
                  colSpan={columns.length + 2}
                >
                  <div className="py-2 flex items-center justify-center gap-1">
                    <i className="fas fa-plus text-[10px]"></i>
                    <span className="text-[11px]">添加行</span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        )}
      </div>

      {/* Toast */}
      {toast && (
        <div className={`absolute bottom-3 right-3 px-3 py-1.5 rounded text-xs shadow ${toast.type === 'error' ? 'bg-red-100 text-red-600' : 'bg-green-100 text-green-600'}`}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}
