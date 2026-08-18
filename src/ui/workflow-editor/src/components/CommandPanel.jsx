import { useState, useEffect } from 'react';
import { useWorkflow, deriveParentId } from '../store/WorkflowContext';

const CATEGORY_ICONS = {
  '页面导航': 'fa-globe',
  '元素点击': 'fa-mouse-pointer',
  '文本输入': 'fa-keyboard',
  '数据提取': 'fa-font',
  '滚动': 'fa-arrows-up-down',
  '等待': 'fa-clock',
  '条件判断': 'fa-code-branch',
  '循环': 'fa-sync',
  '变量与数据': 'fa-database',
  '输出与日志': 'fa-terminal',
  '鼠标键盘': 'fa-mouse',
  '网络请求': 'fa-network-wired',
  'AI集成': 'fa-brain',
  '子流程': 'fa-sitemap',
  '异常处理': 'fa-shield-halved',
  '自定义': 'fa-code',
  // 新指令分类
  '浏览器操作': 'fa-chrome',
  '浏览器元素操作': 'fa-mouse-pointer',
  '变量及日志': 'fa-code',
  '桌面操作': 'fa-desktop',
  'Electron 应用': 'fa-window-restore',
};

const CATEGORY_COLORS = {
  '页面导航': 'text-accent',
  '元素点击': 'text-accent',
  '文本输入': 'text-accent',
  '数据提取': 'text-ok',
  '滚动': 'text-cyan-500',
  '等待': 'text-muted',
  '条件判断': 'text-orange-500',
  '循环': 'text-purple-500',
  '变量与数据': 'text-indigo-500',
  '输出与日志': 'text-muted',
  '鼠标键盘': 'text-muted',
  '网络请求': 'text-accent',
  'AI集成': 'text-indigo-500',
  '子流程': 'text-vision',
  '异常处理': 'text-danger',
  '自定义': 'text-muted',
  // 新指令分类
  '浏览器操作': 'text-accent',
  '浏览器元素操作': 'text-accent',
  '变量及日志': 'text-indigo-500',
  '桌面操作': 'text-purple-500',
  'Electron 应用': 'text-indigo-500',
};

export default function CommandPanel() {
  const {
    newCommands,
    newCommandsLoading,
    NEW_NODE_TYPES,
    NEW_CATEGORIES,
    NEW_NODE_TYPE_MAP,
    saveNode,
    nodes,
    NODE_TYPE_MAP,
  } = useWorkflow();

  // 指令类型查找表（全部来自新指令体系 commands-new）
  const unifiedTypeMap = NODE_TYPE_MAP;
  const allCommandsByCat = newCommands?.commands || {};

  // 阻止浏览器默认 drop 行为，避免拖拽到非画布区域时打开页面
  useEffect(() => {
    const preventDefault = (e) => e.preventDefault();
    window.addEventListener('dragover', preventDefault);
    window.addEventListener('drop', preventDefault);
    return () => {
      window.removeEventListener('dragover', preventDefault);
      window.removeEventListener('drop', preventDefault);
    };
  }, []);

  const createDragImage = (cmd) => {
    const typeInfo = unifiedTypeMap[cmd.cmd] || {};
    const el = document.createElement('div');
    el.style.cssText = 'position:fixed;left:-9999px;top:0;display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:6px;background:#fff;box-shadow:0 4px 12px rgba(0,0,0,0.15);border:1px solid #1677ff;width:240px;font-size:12px;pointer-events:none;z-index:99999;';
    const iconHtml = `<span style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:4px;background:${typeInfo.bgColor ? '' : '#f5f5f5'};color:${typeInfo.iconColor || '#9ca3af'};font-size:10px;"><i class="fas ${typeInfo.icon || 'fa-circle'}"></i></span>`;
    const labelHtml = `<span style="color:#374151;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;">${typeInfo.label || cmd.label || cmd.cmd}</span>`;
    el.innerHTML = iconHtml + labelHtml;
    document.body.appendChild(el);
    return el;
  };

  const [search, setSearch] = useState('');
  const [expandedCats, setExpandedCats] = useState(() =>
    Object.fromEntries(NEW_CATEGORIES.map(c => [c, true]))
  );

  const toggleCategory = (cat) => {
    setExpandedCats(prev => ({ ...prev, [cat]: !prev[cat] }));
  };

  const handleAdd = async (nodeType) => {
    console.log(`[CommandPanel] add nodeType=${nodeType.cmd}`);
    try {
      // Build default extra from command schema
      const cmd = allCommandsByCat[nodeType.category]?.find(c => c.cmd === nodeType.cmd);
      const defaultExtra = {};
      if (cmd?.fields) {
        for (const f of cmd.fields) {
          if (f.default !== undefined) {
            defaultExtra[f.name] = f.default;
          }
        }
      }

      // Auto derive parent_id based on list position
      const parentId = deriveParentId(nodes, nodeType.cmd, unifiedTypeMap);

      await saveNode({
        cmd: nodeType.cmd,
        parent_id: parentId,
        extra: defaultExtra,
      });
    } catch (e) {
      alert('添加失败: ' + e.message);
    }
  };

  const filteredNewTypes = search
    ? NEW_NODE_TYPES.filter(n => (n.label || '').includes(search) || (n.type || '').includes(search))
    : NEW_NODE_TYPES;

  if (newCommandsLoading) {
    return (
      <aside className="w-[250px] bg-surface border-r border-border flex flex-col shrink-0 select-none items-center justify-center text-faint text-xs">
        加载指令库...
      </aside>
    );
  }

  if (!newCommands) {
    return (
      <aside className="w-[250px] bg-surface border-r border-border flex flex-col shrink-0 select-none items-center justify-center text-danger text-xs px-4 text-center">
        指令库加载失败
      </aside>
    );
  }

  const renderCommandItem = (cmd) => (
    <div
      key={cmd.cmd}
      className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-surface-3 cursor-grab text-xs text-muted draggable-item"
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', JSON.stringify({ cmd: cmd.cmd, category: cmd.category }));
        e.target.classList.add('dragging');
        const img = createDragImage(cmd);
        e.dataTransfer.setDragImage(img, 10, 18);
        requestAnimationFrame(() => document.body.removeChild(img));
        document.body.classList.add('dragging-node');
      }}
      onDragEnd={(e) => {
        e.target.classList.remove('dragging');
        document.body.classList.remove('dragging-node');
      }}
      title={cmd.description || cmd.label}
    >
      <i className="fas fa-grip-vertical text-muted text-[10px] mr-1"></i>
      <span className="truncate flex-1">{cmd.label}</span>
      {cmd.hasRuntime && (
        <span
          className={`shrink-0 text-[10px] px-1 py-0 rounded ${cmd.local ? 'bg-surface-3 text-muted' : 'bg-accent-soft text-accent'}`}
          title={cmd.local ? '本地执行（后端）' : '扩展执行（浏览器）'}
        >
          {cmd.local ? '本地' : '扩展'}
        </span>
      )}
    </div>
  );

  const renderCategory = (cat, types, isSearch) => {
    const catTypes = isSearch
      ? types
      : types.filter(n => n.category === cat);
    if (catTypes.length === 0) return null;
    const isExpanded = isSearch ? true : expandedCats[cat];

    return (
      <div key={cat} className="category-group mb-0.5">
        {!isSearch && (
          <div
            className="category-item flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer"
            onClick={() => toggleCategory(cat)}
          >
            <i className={`fas fa-chevron-right text-faint text-[10px] w-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`}></i>
            <i className={`fas ${CATEGORY_ICONS[cat] || 'fa-folder'} ${CATEGORY_COLORS[cat] || 'text-muted'} text-xs w-4 text-center`}></i>
            <span className="text-xs text-body flex-1 truncate">{cat}</span>
          </div>
        )}
        <div className={`ml-4 space-y-0.5 ${isExpanded ? '' : 'hidden'}`}>
          {catTypes.map(renderCommandItem)}
        </div>
      </div>
    );
  };

  return (
    <aside className="w-[250px] bg-surface border-r border-border flex flex-col shrink-0 select-none">
      {/* 头部 */}
      <div className="px-3 py-2 border-b border-border">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-body">指令</span>
        </div>
      </div>

      {/* 搜索框 */}
      <div className="px-3 py-2">
        <div className="flex items-center gap-2 bg-surface-2 rounded px-2.5 py-1.5">
          <i className="fas fa-search text-faint text-xs"></i>
          <input
            type="text"
            placeholder="搜索指令"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-transparent text-xs outline-none w-full placeholder-gray-400"
          />
        </div>
      </div>

      {/* 指令分类列表（全部来自新指令体系 commands-new） */}
      <div className="flex-1 overflow-y-auto px-1 pb-2">
        {newCommands && (search ? filteredNewTypes.length > 0 : NEW_CATEGORIES.length > 0) && (
          <div>
            {search
              ? filteredNewTypes.map(renderCommandItem)
              : NEW_CATEGORIES.map(cat => renderCategory(cat, filteredNewTypes, false))}
          </div>
        )}
        {newCommandsLoading && (
          <div className="px-3 py-2 text-[10px] text-faint">
            <i className="fas fa-circle-notch fa-spin mr-1"></i>加载指令库...
          </div>
        )}
      </div>
    </aside>
  );
}
