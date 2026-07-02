import { useState, useMemo, useRef, useEffect } from 'react';
import { useWorkflow } from '../store/WorkflowContext';

function TreeNode({ node, depth, selectedName, expandedNames, onToggle, onSelect }) {
  const hasChildren = (node.children || []).length > 0;
  const isExpanded = expandedNames.has(node.name);
  const paddingLeft = 6 + depth * 16;
  const guideLeft = paddingLeft + 8;

  return (
    <div className="relative">
      {depth > 0 && (
        <div
          className="absolute border-t border-gray-200"
          style={{ left: guideLeft - 8, top: 11, width: 8 }}
        />
      )}
      {isExpanded && hasChildren && (
        <div
          className="absolute border-l border-gray-200"
          style={{ left: guideLeft, top: 24, bottom: 0 }}
        />
      )}
      <div
        style={{ paddingLeft }}
        className={`group relative z-10 flex items-center gap-1 py-1 pr-2 cursor-pointer ${
          selectedName === node.name ? 'bg-blue-50' : 'hover:bg-gray-100'
        }`}
        onClick={() => onSelect(node.name)}
      >
        {hasChildren ? (
          <button
            onClick={(e) => { e.stopPropagation(); onToggle(node.name); }}
            className="w-4 h-4 flex items-center justify-center text-gray-400 hover:text-gray-600 shrink-0"
          >
            <i className={`fas fa-chevron-${isExpanded ? 'down' : 'right'} text-[9px]`}></i>
          </button>
        ) : (
          <span className="w-4 shrink-0"></span>
        )}
        <span className={`text-xs truncate flex-1 min-w-0 ${
          selectedName === node.name ? 'text-blue-700 font-medium' : 'text-gray-700'
        }`}>
          {node.name}
        </span>
      </div>
      {isExpanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedName={selectedName}
              expandedNames={expandedNames}
              onToggle={onToggle}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function ElementTreeSelect({ label, value, onChange, elements, placeholder = '-- 选择元素 --', disabled = false, disabledPlaceholder = '-- 已禁用 --' }) {
  const { buildElementTree } = useWorkflow();
  const [open, setOpen] = useState(false);
  const [expandedNames, setExpandedNames] = useState(new Set());
  const ref = useRef(null);

  const tree = useMemo(() => buildElementTree(elements), [elements, buildElementTree]);

  useEffect(() => {
    setExpandedNames(new Set(elements.map((e) => e.name)));
  }, [elements]);

  useEffect(() => {
    if (!open) return;
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  function toggleExpandedName(name) {
    const next = new Set(expandedNames);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setExpandedNames(next);
  }

  function handleSelect(name) {
    onChange(name);
    setOpen(false);
  }

  const selectedElement = elements.find((e) => e.name === value);

  return (
    <div className="relative" ref={ref}>
      {label && (
        <label className="block text-[10px] text-gray-400 mb-1">{label}</label>
      )}
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen(!open)}
        className={`w-full px-2 py-1.5 border border-[#d9d9d9] rounded text-sm text-left outline-none focus:border-[#1677ff] flex items-center justify-between ${
          disabled
            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
            : 'bg-white text-gray-700'
        }`}
      >
        <span className="truncate">{disabled ? disabledPlaceholder : (selectedElement ? selectedElement.name : placeholder)}</span>
        {!disabled && <i className={`fas fa-chevron-${open ? 'up' : 'down'} text-[10px] text-gray-400`}></i>}
      </button>
      {open && (
        <div className="absolute z-50 left-0 right-0 mt-1 max-h-64 overflow-y-auto bg-white border border-[#d9d9d9] rounded shadow-lg py-1">
          {elements.length === 0 ? (
            <div className="px-2 py-1.5 text-xs text-gray-400">暂无元素</div>
          ) : (
            tree.map((root) => (
              <TreeNode
                key={root.id}
                node={root}
                depth={0}
                selectedName={value}
                expandedNames={expandedNames}
                onToggle={toggleExpandedName}
                onSelect={handleSelect}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}
