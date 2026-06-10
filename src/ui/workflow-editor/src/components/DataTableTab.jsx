import { useState, useEffect, useRef, memo } from 'react';

// 可编辑单元格：contentEditable 无法被 React 受控，需手动同步外部数据更新
const EditableCell = memo(function EditableCell({ value, onChange }) {
  const ref = useRef(null);
  const isEditingRef = useRef(false);

  useEffect(() => {
    const text = value ?? '';
    if (!isEditingRef.current && ref.current && ref.current.innerText !== String(text)) {
      ref.current.innerText = text;
    }
  }, [value]);

  return (
    <div
      ref={ref}
      className="px-2 py-1 outline-none min-h-[28px] focus:bg-blue-50/30"
      contentEditable
      suppressContentEditableWarning
      onFocus={() => { isEditingRef.current = true; }}
      onBlur={(e) => {
        isEditingRef.current = false;
        const val = e.target.innerText;
        if (val !== String(value ?? '')) {
          onChange(val);
        }
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          e.target.blur();
        }
      }}
    >
      {value ?? ''}
    </div>
  );
});

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

export default function DataTableTab({ wfId }) {
  const [table, setTable] = useState(null);
  const [toast, setToast] = useState(null);
  const debounceRef = useRef(null);
  const skipNextSaveRef = useRef(false);
  const fileInputRef = useRef(null);
  const gridRef = useRef(null);

  // 数据表格自动滚底：行数变化时若之前在底部则保持底部
  useEffect(() => {
    if (!gridRef.current || !table) return;
    const el = gridRef.current;
    const isAtBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
    if (isAtBottom) {
      el.scrollTop = el.scrollHeight;
    }
  }, [table?.rows?.length]);

  const STORAGE_KEY = `workflow_table_${wfId}`;

  // Load from localStorage on mount
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

  // Listen for runtime table updates from Toolbar SSE
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

  // Save to localStorage whenever table changes (debounced)
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
    } catch (err) {
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
    } catch (err) {
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

  const renderGrid = (data, editable = false) => {
    const columns = data.columns || [];
    const rows = data.rows || [];
    if (!columns.length) return <div className="text-xs text-gray-400 p-2">无数据</div>;
    return (
      <table className="w-auto border-collapse text-xs">
        <thead>
          <tr>
            <th className="w-8 h-8 border bg-gray-50 text-center text-gray-400"></th>
            {columns.map((col, ci) => (
              <th key={ci} className="border bg-gray-50 min-w-[80px] relative group">
                {editable ? (
                  <div className="flex items-center">
                    <input
                      className="w-full px-2 py-1 bg-transparent text-center outline-none font-medium"
                      value={col.name}
                      onChange={(e) => renameColumn(ci, e.target.value)}
                    />
                    <button
                      onClick={() => removeColumn(ci)}
                      className="opacity-0 group-hover:opacity-100 w-5 h-5 flex items-center justify-center text-red-400 hover:text-red-600"
                      title="删除列"
                    >
                      <i className="fas fa-times text-[8px]"></i>
                    </button>
                  </div>
                ) : (
                  <div className="px-2 py-1 text-center font-medium">{col.name}</div>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri}>
              <td className="border bg-gray-50 text-center text-gray-400 relative group w-8">
                {ri + 1}
                {editable && (
                  <button
                    onClick={() => removeRow(ri)}
                    className="absolute left-0 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 w-4 h-4 flex items-center justify-center text-red-400 hover:text-red-600"
                    title="删除行"
                  >
                    <i className="fas fa-times text-[8px]"></i>
                  </button>
                )}
              </td>
              {columns.map((col, ci) => (
                <td key={ci} className="border min-w-[80px]">
                  {editable ? (
                    <EditableCell
                      value={row[col.name] ?? ''}
                      onChange={(val) => updateCell(ri, col.name, val)}
                    />
                  ) : (
                    <div className="px-2 py-1 min-h-[28px]">{row[col.name] ?? ''}</div>
                  )}
                </td>
              ))}
            </tr>
          ))}
          {editable && (
            <tr>
              <td className="border bg-gray-50 text-center text-gray-400 cursor-pointer hover:bg-gray-100"
                onClick={addRow}
                colSpan={columns.length + 1}
              >
                <i className="fas fa-plus text-[10px]"></i> 添加行
              </td>
            </tr>
          )}
        </tbody>
      </table>
    );
  };

  if (!table) return <div className="p-4 text-sm text-gray-400">加载中...</div>;

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-3 py-2 border-b bg-white">
        <span className="text-xs text-gray-500 font-medium">数据表格</span>
        <button onClick={addColumn} className="text-xs px-2 py-1 border rounded hover:bg-gray-50">+ 列</button>
        <button onClick={addRow} className="text-xs px-2 py-1 border rounded hover:bg-gray-50">+ 行</button>
        <button onClick={() => fileInputRef.current?.click()} className="text-xs px-2 py-1 border rounded hover:bg-gray-50">导入</button>
        <input ref={fileInputRef} type="file" accept=".csv" className="hidden" onChange={handleImport} />
        <button onClick={handleExport} className="text-xs px-2 py-1 border rounded hover:bg-gray-50">导出</button>
        <button onClick={handleRefresh} className="text-xs px-2 py-1 border rounded hover:bg-gray-50" title="从本地存储重新加载">
          <i className="fas fa-sync-alt text-[10px]"></i> 刷新
        </button>
        <button onClick={handleClear} className="text-xs px-2 py-1 border rounded hover:bg-red-50 text-red-500">清空</button>
      </div>
      <div ref={gridRef} className="flex-1 overflow-auto p-3">
        {renderGrid(table, true)}
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
