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
};

const CATEGORY_COLORS = {
  '页面导航': 'text-blue-500',
  '元素点击': 'text-blue-500',
  '文本输入': 'text-blue-500',
  '数据提取': 'text-green-500',
  '滚动': 'text-cyan-500',
  '等待': 'text-gray-500',
  '条件判断': 'text-orange-500',
  '循环': 'text-purple-500',
  '变量与数据': 'text-indigo-500',
  '输出与日志': 'text-gray-600',
  '鼠标键盘': 'text-gray-600',
  '网络请求': 'text-blue-700',
  'AI集成': 'text-indigo-500',
  '子流程': 'text-pink-500',
  '异常处理': 'text-red-500',
  '自定义': 'text-gray-500',
};

export default function CommandPanel() {
  const { commands, commandsLoading, NODE_TYPES, CATEGORIES, saveNode, wfId, nodes, NODE_TYPE_MAP } = useWorkflow();

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
    const typeInfo = NODE_TYPE_MAP[cmd.type] || {};
    const el = document.createElement('div');
    el.style.cssText = 'position:fixed;left:-9999px;top:0;display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:6px;background:#fff;box-shadow:0 4px 12px rgba(0,0,0,0.15);border:1px solid #1677ff;width:240px;font-size:12px;pointer-events:none;z-index:99999;';
    const iconHtml = `<span style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:4px;background:${typeInfo.bgColor ? '' : '#f5f5f5'};color:${typeInfo.iconColor || '#9ca3af'};font-size:10px;"><i class="fas ${typeInfo.icon || 'fa-circle'}"></i></span>`;
    const labelHtml = `<span style="color:#374151;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;">${typeInfo.label || cmd.label || cmd.type}</span>`;
    el.innerHTML = iconHtml + labelHtml;
    document.body.appendChild(el);
    return el;
  };
  const [search, setSearch] = useState('');
  const [expandedCats, setExpandedCats] = useState(() =>
    Object.fromEntries(CATEGORIES.map(c => [c, true]))
  );

  const toggleCategory = (cat) => {
    setExpandedCats(prev => ({ ...prev, [cat]: !prev[cat] }));
  };

  const handleAdd = async (nodeType) => {
    console.log(`[CommandPanel] add nodeType=${nodeType.type}`);
    try {
      // Build default extra from command schema
      const cmd = commands?.commands?.[nodeType.category]?.find(c => c.type === nodeType.type);
      const defaultExtra = {};
      if (cmd?.fields) {
        for (const f of cmd.fields) {
          if (f.default !== undefined) {
            defaultExtra[f.name] = f.default;
          }
        }
      }

      // Auto derive parent_id based on list position
      const parentId = deriveParentId(nodes, nodeType.type, NODE_TYPE_MAP);

      await saveNode({
        type: nodeType.type,
        parent_id: parentId,
        extra: defaultExtra,
      });
    } catch (e) {
      alert('添加失败: ' + e.message);
    }
  };

  const filteredTypes = search
    ? NODE_TYPES.filter(n => (n.label || '').includes(search) || (n.type || '').includes(search))
    : NODE_TYPES;

  if (commandsLoading) {
    return (
      <aside className="w-[250px] bg-white border-r border-[#e8e8e8] flex flex-col shrink-0 select-none items-center justify-center text-gray-400 text-xs">
        加载指令库...
      </aside>
    );
  }

  if (!commands) {
    return (
      <aside className="w-[250px] bg-white border-r border-[#e8e8e8] flex flex-col shrink-0 select-none items-center justify-center text-red-400 text-xs px-4 text-center">
        指令库加载失败
      </aside>
    );
  }

  return (
    <aside className="w-[250px] bg-white border-r border-[#e8e8e8] flex flex-col shrink-0 select-none">
      {/* 头部 */}
      <div className="px-3 py-2 border-b border-[#e8e8e8]">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-700">指令</span>
        </div>
      </div>

      {/* 搜索框 */}
      <div className="px-3 py-2">
        <div className="flex items-center gap-2 bg-[#f5f5f5] rounded px-2.5 py-1.5">
          <i className="fas fa-search text-gray-400 text-xs"></i>
          <input
            type="text"
            placeholder="搜索指令"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-transparent text-xs outline-none w-full placeholder-gray-400"
          />
        </div>
      </div>

      {/* 指令分类列表 */}
      <div className="flex-1 overflow-y-auto px-1 pb-2">
        {(search ? ['搜索结果'] : CATEGORIES).map(cat => {
          const catTypes = search
            ? filteredTypes
            : filteredTypes.filter(n => n.category === cat);
          if (catTypes.length === 0) return null;
          const isExpanded = search ? true : expandedCats[cat];

          return (
            <div key={cat} className="category-group mb-0.5">
              {!search && (
                <div
                  className="category-item flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer"
                  onClick={() => toggleCategory(cat)}
                >
                  <i className={`fas fa-chevron-right text-gray-400 text-[10px] w-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`}></i>
                  <i className={`fas ${CATEGORY_ICONS[cat] || 'fa-folder'} ${CATEGORY_COLORS[cat] || 'text-gray-500'} text-xs w-4 text-center`}></i>
                  <span className="text-xs text-gray-700 flex-1 truncate">{cat}</span>
                </div>
              )}
              <div className={`ml-4 space-y-0.5 ${isExpanded ? '' : 'hidden'}`}>
                {catTypes.map(cmd => (
                  <div
                    key={cmd.type}
                    className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-gray-100 cursor-grab text-xs text-gray-600 draggable-item"
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData('text/plain', JSON.stringify({ type: cmd.type, category: cmd.category }));
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
                  >
                    <i className="fas fa-grip-vertical text-gray-300 text-[10px] mr-1"></i>
                    <span className="truncate flex-1">{cmd.label}</span>
                    {cmd.hasRuntime && (
                      <span
                        className={`shrink-0 text-[10px] px-1 py-0 rounded ${cmd.local ? 'bg-gray-100 text-gray-500' : 'bg-blue-50 text-blue-600'}`}
                        title={cmd.local ? '本地执行（后端）' : '扩展执行（浏览器）'}
                      >
                        {cmd.local ? '本地' : '扩展'}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
