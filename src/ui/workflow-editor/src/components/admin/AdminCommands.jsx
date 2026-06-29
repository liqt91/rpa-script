import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api';

const FIELD_TYPE_LABELS = {
  text: '文本', number: '数字', bool: '开关', select: '下拉选择',
  textarea: '多行文本', locator: '选择器', varName: '变量名',
  elementName: '元素选择', elementNameList: '元素列表', hidden: '隐藏字段',
};

const FIELD_TYPE_ICONS = {
  text: 'fa-font', number: 'fa-hashtag', bool: 'fa-toggle-on', select: 'fa-list',
  textarea: 'fa-align-left', locator: 'fa-crosshairs', varName: 'fa-superscript',
  elementName: 'fa-mouse-pointer', elementNameList: 'fa-list-check', hidden: 'fa-eye-slash',
};

const ACTION_PRESETS = {
  extension: [
    { label: '点击元素', handler: 'elementAction', action: 'click', autoFields: ['windowVar','element_name','scope'] },
    { label: '双击元素', handler: 'elementAction', action: 'doubleClick', autoFields: ['windowVar','element_name','scope'] },
    { label: '右键点击', handler: 'elementAction', action: 'rightClick', autoFields: ['windowVar','element_name','scope'] },
    { label: '输入文本', handler: 'elementAction', action: 'input', autoFields: ['windowVar','element_name','scope','text','clearFirst'] },
    { label: '输入并回车', handler: 'elementAction', action: 'inputAndPressEnter', autoFields: ['windowVar','element_name','scope','text','clearFirst'] },
    { label: '清空输入框', handler: 'elementAction', action: 'clearInput', autoFields: ['windowVar','element_name'] },
    { label: '下拉框选择', handler: 'elementAction', action: 'selectOption', autoFields: ['windowVar','element_name','by','value'] },
    { label: '获取元素文本', handler: 'elementAction', action: 'extract', autoFields: ['windowVar','element_name','scope','varName'] },
    { label: '获取元素属性', handler: 'elementAction', action: 'extract', autoFields: ['windowVar','element_name','scope','attrName','varName'] },
    { label: '获取元素HTML', handler: 'elementAction', action: 'extract', autoFields: ['windowVar','element_name','mode','varName'] },
    { label: '获取输入框值', handler: 'elementAction', action: 'extract', autoFields: ['windowVar','element_name','varName'] },
    { label: '滚动到底部', handler: 'elementAction', action: 'scroll', autoFields: ['windowVar','scrollType','humanLike'] },
    { label: '滚动到顶部', handler: 'elementAction', action: 'scroll', autoFields: ['windowVar','scrollType','humanLike'] },
    { label: '滚动一屏', handler: 'elementAction', action: 'scroll', autoFields: ['windowVar','scrollType','humanLike'] },
    { label: '滚动指定距离', handler: 'elementAction', action: 'scroll', autoFields: ['windowVar','x','y','humanLike'] },
    { label: '悬停', handler: 'elementAction', action: 'hover', autoFields: ['element_name','scope'] },
    { label: '取消悬停', handler: 'elementAction', action: 'unhover', autoFields: ['windowVar','element_name','scope'] },
    { label: '打开网页', handler: 'navigate', autoFields: ['url','windowVar','waitLoad','timeout','saveToVar'] },
    { label: '新建标签页', handler: 'newTab', autoFields: ['windowVar','url'] },
    { label: '关闭浏览器', handler: 'closeBrowser', autoFields: ['windowVar'] },
    { label: '获取当前URL', handler: 'getCurrentUrl', autoFields: ['windowVar','varName'] },
    { label: '按键', handler: 'pressKey', autoFields: ['windowVar','key'] },
    { label: '等待固定时间', handler: 'wait', autoFields: ['windowVar','seconds'] },
    { label: '等待元素出现', handler: 'wait', autoFields: ['windowVar','element_name','scope','timeout'] },
    { label: '执行JS', handler: 'executeJs', autoFields: ['script','resultVar'] },
  ],
  local: [
    { label: '打开浏览器', handler: 'openBrowser', autoFields: ['browserType','urlOptional','windowState','saveToVar'] },
    { label: '设置变量', handler: 'setVar', autoFields: ['name','value','valueType'] },
    { label: '追加到列表', handler: 'appendToList', autoFields: ['listName','value'] },
    { label: '字符串拼接', handler: 'stringConcat', autoFields: ['targetVar','part1','part2','part3'] },
    { label: '计数器累加', handler: 'increment', autoFields: ['varName','step'] },
    { label: '设置字典值', handler: 'setDictValue', autoFields: ['dictName','key','value'] },
    { label: '获取字典值', handler: 'getDictValue', autoFields: ['dictName','key','varName'] },
    { label: '删除字典键', handler: 'removeDictKey', autoFields: ['dictName','key'] },
    { label: '打印日志', handler: 'log', autoFields: ['message','level'] },
    { label: 'HTTP请求', handler: 'httpRequest', autoFields: ['method','url','headers','body','timeout','resultVar'] },
    { label: '自定义代码', handler: 'custom', autoFields: ['code','description','resultVar'] },
  ],
};

const COMMON_FIELDS = {
  windowVar: { name: 'windowVar', label: '窗口变量', type: 'varName', required: false, default: 'browser1', placeholder: '如 browser1', group: 'input' },
  element_name: { name: 'element_name', label: '元素', type: 'elementName', required: true, isPrimaryElement: true, group: 'input' },
  scope: { name: 'scope', label: '匹配范围', type: 'select', options: [{label:'在当前外层元素内查找',value:'local'},{label:'全页面匹配',value:'global'}], default: 'global', group: 'advanced', description: '在当前外层元素内查找=仅在当前 forEachElement 循环到的元素内部搜索该选择器；全页面匹配=在整个页面搜索，不依赖循环上下文。' },
  text: { name: 'text', label: '输入内容', type: 'text', required: true, group: 'input' },
  clearFirst: { name: 'clearFirst', label: '先清空', type: 'bool', default: true, group: 'input' },
  by: { name: 'by', label: '选择方式', type: 'select', options: [{label:'值',value:'value'},{label:'文本',value:'label'},{label:'索引',value:'index'}], default: 'label', group: 'input' },
  value: { name: 'value', label: '值', type: 'text', required: true, group: 'input' },
  attrName: { name: 'attrName', label: '属性名', type: 'text', required: true, placeholder: 'href / src / data-id', group: 'input' },
  mode: { name: 'mode', label: '模式', type: 'select', options: [{label:'内部HTML',value:'inner'},{label:'包含标签',value:'outer'}], default: 'inner', group: 'input' },
  varName: { name: 'varName', label: '保存到变量', type: 'varName', required: false, group: 'output' },
  scrollType: { name: 'scrollType', label: '滚动类型', type: 'hidden', default: 'toBottom', group: 'advanced' },
  x: { name: 'x', label: '水平距离(px)', type: 'number', default: 0, group: 'input' },
  y: { name: 'y', label: '垂直距离(px)', type: 'number', default: 500, group: 'input' },
  humanLike: { name: 'humanLike', label: '拟人化/平滑', type: 'bool', default: true, group: 'advanced' },
  url: { name: 'url', label: '网址', type: 'text', required: true, placeholder: 'https://...', group: 'input' },
  urlOptional: { name: 'url', label: '网址', type: 'text', required: false, placeholder: '留空则打开 about:blank', group: 'input' },
  browserType: { name: 'browserType', label: '浏览器', type: 'select', options: [{label:'Chrome',value:'chrome'},{label:'Edge',value:'edge'}], default: 'chrome', group: 'input' },
  windowState: { name: 'windowState', label: '窗口状态', type: 'select', options: [{label:'正常',value:'normal'},{label:'最大化',value:'maximized'}], default: 'normal', group: 'input' },
  waitLoad: { name: 'waitLoad', label: '等待加载完成', type: 'bool', default: true, group: 'advanced' },
  timeout: { name: 'timeout', label: '超时(秒)', type: 'number', default: 10, group: 'advanced' },
  saveToVar: { name: 'saveToVar', label: '保存到变量', type: 'varName', required: false, group: 'output' },
  key: { name: 'key', label: '按键', type: 'select', options: [{label:'回车',value:'Enter'},{label:'Tab',value:'Tab'},{label:'Esc',value:'Esc'},{label:'向下箭头',value:'ArrowDown'},{label:'向上箭头',value:'ArrowUp'},{label:'PageDown',value:'PageDown'},{label:'PageUp',value:'PageUp'},{label:'空格',value:'Space'},{label:'退格',value:'Backspace'}], default: 'Enter', group: 'input' },
  seconds: { name: 'seconds', label: '等待秒数', type: 'number', default: 1, group: 'input' },
  script: { name: 'script', label: 'JavaScript代码', type: 'textarea', required: true, rows: 4, group: 'input' },
  resultVar: { name: 'resultVar', label: '返回值变量', type: 'varName', required: false, group: 'output' },
  name: { name: 'name', label: '变量名', type: 'varName', required: true, group: 'input' },
  value: { name: 'value', label: '值', type: 'text', required: true, group: 'input' },
  valueType: { name: 'valueType', label: '值类型', type: 'select', options: [{label:'字符串',value:'string'},{label:'数字',value:'number'},{label:'布尔值',value:'bool'},{label:'列表',value:'list'},{label:'字典',value:'dict'}], default: 'string', group: 'input' },
  listName: { name: 'listName', label: '列表变量', type: 'varName', required: true, group: 'input' },
  targetVar: { name: 'targetVar', label: '目标变量', type: 'varName', required: true, group: 'input' },
  part1: { name: 'part1', label: '片段1', type: 'text', required: true, group: 'input' },
  part2: { name: 'part2', label: '片段2', type: 'text', required: false, group: 'input' },
  part3: { name: 'part3', label: '片段3', type: 'text', required: false, group: 'input' },
  step: { name: 'step', label: '步长', type: 'number', default: 1, group: 'input' },
  dictName: { name: 'dictName', label: '字典变量', type: 'varName', required: true, group: 'input' },
  message: { name: 'message', label: '日志内容', type: 'text', required: true, group: 'input' },
  level: { name: 'level', label: '级别', type: 'select', options: [{label:'信息',value:'info'},{label:'警告',value:'warn'},{label:'错误',value:'error'}], default: 'info', group: 'input' },
  method: { name: 'method', label: '方法', type: 'select', options: [{label:'GET',value:'GET'},{label:'POST',value:'POST'},{label:'PUT',value:'PUT'},{label:'DELETE',value:'DELETE'}], default: 'GET', group: 'input' },
  headers: { name: 'headers', label: 'Headers(JSON)', type: 'textarea', required: false, group: 'input' },
  body: { name: 'body', label: 'Body', type: 'textarea', required: false, group: 'input' },
  code: { name: 'code', label: 'Python代码', type: 'textarea', required: true, rows: 6, placeholder: "# 直接插入的Python代码\nprint('hello')", group: 'input' },
  description: { name: 'description', label: '描述', type: 'text', required: false, group: 'input' },
};

function parseDefault(type, raw) {
  if (raw === '' || raw === undefined) return undefined;
  if (type === 'number') { const n = Number(raw); return isNaN(n) ? raw : n; }
  if (type === 'bool') return raw.toLowerCase?.() === 'true' || raw === true;
  return raw;
}

function formatOptions(options) {
  if (!options || !options.length) return '';
  if (typeof options[0] === 'object') return options.map(o => `${o.label || ''}:${o.value || ''}`).join(',');
  return options.join(',');
}

function parseOptions(raw) {
  if (!raw) return undefined;
  const parts = raw.split(',').map(s => s.trim()).filter(Boolean);
  if (!parts.length) return undefined;
  if (parts[0].includes(':')) {
    return parts.map(p => { const idx = p.indexOf(':'); return { label: p.slice(0, idx).trim(), value: p.slice(idx + 1).trim() }; });
  }
  return parts;
}

function runtimeLabel(c) {
  if (c.isContainer) return <span className="px-1.5 py-0.5 rounded text-[10px] bg-orange-900/40 text-orange-300">容器</span>;
  if (c.isStructural) return <span className="px-1.5 py-0.5 rounded text-[10px] bg-purple-900/40 text-purple-300">结构</span>;
  if (!c.handler) return <span className="px-1.5 py-0.5 rounded text-[10px] bg-gray-700 text-gray-400">无执行</span>;
  if (c.local) return <span className="px-1.5 py-0.5 rounded text-[10px] bg-gray-700 text-gray-300">后端</span>;
  return <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-900/40 text-blue-300">扩展</span>;
}

export default function AdminCommands() {
  const [commands, setCommands] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [categoryFilter, setCategoryFilter] = useState('');
  const [enabledOnly, setEnabledOnly] = useState(true);
  const [auditMode, setAuditMode] = useState(false);
  const [handlers, setHandlers] = useState([]);

  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState('create');
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    id: null, type: '', label: '', category: '', icon: 'fa-circle', iconColor: 'text-gray-500', bgColor: 'bg-gray-50',
    commandOrder: 0, description: '', isContainer: false, isBranch: false, isStructural: false, closesWith: '',
    runtimeMode: 'none', handler: '', local: false, action: '', enabled: true,
  });
  const [params, setParams] = useState([]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [auditResult, setAuditResult] = useState(null);
  const [auditing, setAuditing] = useState(false);

  useEffect(() => { loadCommands(); loadHandlers(); }, []);

  async function loadHandlers() {
    try {
      const data = await api.listCommandHandlers();
      setHandlers(data.handlers || []);
    } catch (e) { console.warn('加载 handlers 失败:', e.message); }
  }

  async function loadCommands() {
    setLoading(true);
    try {
      const data = await api.listCommands({ category: categoryFilter, enabled_only: String(enabledOnly) });
      setCommands(data || []);
      setError(null);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }

  const categories = useMemo(() => [...new Set(commands.map(c => c.category))].sort(), [commands]);

  const grouped = useMemo(() => {
    const sorted = [...commands].sort((a, b) => {
      if (a.enabled !== b.enabled) return b.enabled - a.enabled;
      return (a.categoryOrder ?? 0) - (b.categoryOrder ?? 0) || (a.commandOrder ?? 0) - (b.commandOrder ?? 0);
    });
    const map = {};
    sorted.forEach(c => { if (!map[c.category]) map[c.category] = []; map[c.category].push(c); });
    return map;
  }, [commands]);

  const auditStats = useMemo(() => {
    const total = commands.length;
    const reviewed = commands.filter(c => c.reviewedAt).length;
    return { total, reviewed, pct: total ? Math.round((reviewed / total) * 100) : 0 };
  }, [commands]);

  function updateForm(patch) { setForm(f => ({ ...f, ...patch })); }

  function resetWizard() {
    setStep(1);
    setForm({
      id: null, type: '', label: '', category: '', icon: 'fa-circle', iconColor: 'text-gray-500', bgColor: 'bg-gray-50',
      commandOrder: 0, description: '', isContainer: false, isBranch: false, isStructural: false, closesWith: '',
      runtimeMode: 'none', handler: '', local: false, action: '', enabled: true,
    });
    setParams([]);
    setShowAdvanced(false);
    setAuditResult(null);
  }

  function openCreate() { resetWizard(); setModalMode('create'); setModalOpen(true); }

  function openEdit(cmd) {
    resetWizard();
    setModalMode('edit');
    let mode = 'none';
    if (cmd.isContainer || cmd.isStructural || cmd.type === 'custom') mode = 'none';
    else if (cmd.handler && cmd.local) mode = 'local';
    else if (cmd.handler) mode = 'extension';
    const actionField = cmd.fields?.find(f => f.name === 'action');
    setForm({
      id: cmd.id, type: cmd.type, label: cmd.label, category: cmd.category, icon: cmd.icon,
      iconColor: cmd.iconColor, bgColor: cmd.bgColor, commandOrder: cmd.commandOrder ?? 0,
      description: cmd.description || '', isContainer: cmd.isContainer, isBranch: cmd.isBranch,
      isStructural: cmd.isStructural, closesWith: cmd.closesWith || '', runtimeMode: mode,
      handler: cmd.handler || '', local: !!cmd.local, action: actionField?.default || '', enabled: cmd.enabled,
    });
    setParams((cmd.fields || []).filter(f => f.name !== 'action').map(f => ({ ...f, _id: Math.random().toString(36).slice(2), expanded: true })));
    setModalOpen(true);
  }

  function addParam(field = {}) {
    setParams(p => [...p, {
      _id: Math.random().toString(36).slice(2),
      name: field.name || '', label: field.label || '', type: field.type || 'text', group: field.group || 'input',
      required: !!field.required, isPrimaryElement: !!field.isPrimaryElement,
      default: field.default !== undefined ? String(field.default) : '',
      placeholder: field.placeholder || '', description: field.description || '',
      options: formatOptions(field.options), expanded: true,
    }]);
  }

  function removeParam(id) { setParams(p => p.filter(x => x._id !== id)); }

  function updateParam(id, patch) {
    setParams(p => p.map(x => x._id === id ? { ...x, ...patch } : x));
  }

  function applyPreset(value) {
    if (!value) return;
    const [mode, idx] = value.split(':');
    const preset = ACTION_PRESETS[mode]?.[parseInt(idx, 10)];
    if (!preset) return;
    updateForm({ handler: preset.handler, local: mode === 'local', action: preset.action || '' });
    const existing = new Set(params.map(p => p.name));
    if (preset.autoFields && params.length === 0) {
      preset.autoFields.forEach(name => {
        if (COMMON_FIELDS[name] && !existing.has(name)) addParam(COMMON_FIELDS[name]);
      });
    }
  }

  function currentPresetValue() {
    const presets = ACTION_PRESETS[form.runtimeMode] || [];
    const idx = presets.findIndex(p => p.handler === form.handler && (p.action || '') === form.action);
    return idx >= 0 ? `${form.runtimeMode}:${idx}` : '';
  }

  function collectPayload() {
    const hasRuntime = form.runtimeMode !== 'none';
    const fields = params.map(p => {
      const f = {
        name: p.name.trim(), label: p.label.trim() || p.name.trim(), type: p.type, group: p.group,
        required: p.required,
      };
      if (p.isPrimaryElement) f.isPrimaryElement = true;
      const def = parseDefault(p.type, p.default);
      if (def !== undefined) f.default = def;
      if (p.placeholder) f.placeholder = p.placeholder;
      if (p.description) f.description = p.description;
      const opts = parseOptions(p.options);
      if (opts) f.options = opts;
      return f;
    });
    if (hasRuntime && form.action && !fields.some(f => f.name === 'action')) {
      fields.push({ name: 'action', label: '扩展动作', type: 'hidden', default: form.action });
    }
    return {
      type: form.type.trim(), label: form.label.trim(), category: form.category.trim(),
      icon: form.icon.trim(), iconColor: form.iconColor.trim(), bgColor: form.bgColor.trim(),
      commandOrder: parseInt(form.commandOrder, 10) || 0,
      isContainer: form.isContainer, isBranch: form.isBranch, isStructural: form.isStructural,
      closesWith: form.closesWith.trim() || null, fields, description: form.description.trim(),
      enabled: form.enabled, handler: hasRuntime ? form.handler.trim() : null,
      local: hasRuntime ? form.local : false,
    };
  }

  async function saveCommand() {
    if (!form.type.trim() || !form.label.trim() || !form.category.trim()) {
      setError('请填写指令类型、显示名称和所属分类'); return;
    }
    const payload = collectPayload();
    if (form.runtimeMode !== 'none' && !payload.handler) {
      setError('已选择执行方式，请选择对应的动作模板或填写 handler'); return;
    }
    try {
      if (form.id) await api.updateCommand(form.id, payload);
      else await api.createCommand(payload);
      setModalOpen(false);
      loadCommands();
    } catch (e) { setError(e.message); }
  }

  async function deleteCommand(id) {
    if (!confirm('确定删除该指令？此操作不可恢复。')) return;
    try { await api.deleteCommand(id); loadCommands(); } catch (e) { setError(e.message); }
  }

  async function toggleEnabled(id, checked) {
    try { await api.updateCommand(id, { enabled: checked }); loadCommands(); } catch (e) { setError(e.message); }
  }

  async function updateOrder(id, field, value) {
    try { await api.updateCommand(id, { [field]: parseInt(value, 10) || 0 }); loadCommands(); } catch (e) { setError(e.message); }
  }

  async function updateCategoryOrder(cat, value) {
    const num = parseInt(value, 10) || 0;
    const ids = commands.filter(c => c.category === cat).map(c => c.id);
    try { await Promise.all(ids.map(id => api.updateCommand(id, { categoryOrder: num }))); loadCommands(); } catch (e) { setError(e.message); }
  }

  async function toggleReviewed(id, checked) {
    try {
      await api.updateCommand(id, { reviewedAt: checked ? new Date().toISOString() : null });
      loadCommands();
    } catch (e) { setError(e.message); }
  }

  async function runValidation() {
    try {
      const data = await api.validateCommands();
      const output = (data.stdout || '') + (data.stderr || '');
      alert((data.passed ? '✅ 指令一致性验证通过\n\n' : '❌ 指令一致性验证失败\n\n') + output);
    } catch (e) { setError(e.message); }
  }

  async function enableAll() {
    if (!confirm('确定启用所有指令？')) return;
    try { await api.enableAllCommands(); loadCommands(); } catch (e) { setError(e.message); }
  }

  async function runSmartAudit() {
    setAuditing(true); setAuditResult(null);
    try {
      const payload = collectPayload();
      const data = await api.analyzeCommand({
        type: payload.type, fields: payload.fields, isContainer: payload.isContainer,
        isStructural: payload.isStructural, hasRuntime: !!payload.handler, handler: payload.handler, local: payload.local,
      });
      setAuditResult(data);
    } catch (e) { setError(e.message); }
    finally { setAuditing(false); }
  }

  function exportCsv() {
    api.exportCommandsCsv().then(res => {
      if (!res.ok) throw new Error('导出失败');
      return res.blob();
    }).then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `workflow_commands_${new Date().toISOString().slice(0,19).replace(/[:T]/g, '_')}.csv`; a.click(); URL.revokeObjectURL(url);
    }).catch(e => setError(e.message));
  }

  function validateStep(n) {
    if (n === 1) {
      if (!form.type.trim()) { setError('请填写指令类型'); return false; }
      if (!form.label.trim()) { setError('请填写显示名称'); return false; }
      if (!form.category.trim()) { setError('请填写所属分类'); return false; }
    }
    return true;
  }

  function nextStep() { if (validateStep(step) && step < 4) setStep(s => s + 1); }
  function prevStep() { if (step > 1) setStep(s => s - 1); }

  const payloadPreview = useMemo(() => collectPayload(), [form, params]);

  const visibleFields = payloadPreview.fields.filter(f => f.type !== 'hidden');

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">指令管理</h1>
          <p className="text-gray-500 text-sm mt-1">管理工作流指令、执行方式与参数定义</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={runValidation} className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-sm transition-colors">
            <i className="fas fa-shield-halved mr-2"></i>验证一致性
          </button>
          <button onClick={enableAll} className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-sm transition-colors">
            <i className="fas fa-toggle-on mr-2"></i>全部启用
          </button>
          <button onClick={exportCsv} className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg text-sm transition-colors">
            <i className="fas fa-file-csv mr-2"></i>导出 CSV
          </button>
          <button onClick={openCreate} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors">
            <i className="fas fa-plus mr-2"></i>新增指令
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
          <i className="fas fa-exclamation-circle mr-2"></i>{error}
          <button onClick={() => setError(null)} className="ml-2 text-red-400 hover:text-red-200">×</button>
        </div>
      )}

      <div className="mb-4 flex gap-3 items-center flex-wrap">
        <select value={categoryFilter} onChange={e => { setCategoryFilter(e.target.value); loadCommands(); }} className="px-3 py-2 bg-[#1e293b] border border-gray-700 rounded-lg text-sm text-gray-300">
          <option value="">全部分类</option>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <label className="flex items-center gap-2 text-sm text-gray-300">
          <input type="checkbox" checked={enabledOnly} onChange={e => { setEnabledOnly(e.target.checked); loadCommands(); }} className="rounded bg-[#1e293b] border-gray-600" />
          仅显示启用
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-300 ml-auto">
          <input type="checkbox" checked={auditMode} onChange={e => setAuditMode(e.target.checked)} className="rounded bg-[#1e293b] border-gray-600" />
          <i className="fas fa-glasses text-purple-400"></i>审核模式
        </label>
      </div>

      {auditMode && (
        <div className="mb-4 bg-[#1e293b] border border-gray-700 rounded-lg p-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm text-gray-300">审核进度</span>
            <span className="text-sm text-purple-300 font-mono">{auditStats.reviewed} / {auditStats.total}</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div className="bg-purple-500 h-2 rounded-full transition-all" style={{ width: `${auditStats.pct}%` }} />
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <i className="fas fa-circle-notch fa-spin text-blue-400 text-2xl"></i>
          <span className="ml-3 text-gray-400">加载中...</span>
        </div>
      ) : (
        <div className="space-y-4">
          {commands.length === 0 && <p className="text-gray-500 text-center py-12">暂无指令</p>}
          {Object.entries(grouped).map(([cat, cmds]) => (
            <div key={cat} className="bg-[#1e293b] rounded-xl border border-gray-700 overflow-hidden">
              <div className="px-4 py-2.5 bg-[#252f47] border-b border-gray-700 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-200">{cat}</span>
                  <div className="flex items-center gap-1 ml-2">
                    <span className="text-[10px] text-gray-500">排序</span>
                    <input type="number" defaultValue={cmds[0]?.categoryOrder ?? 0} onBlur={e => updateCategoryOrder(cat, e.target.value)} className="w-14 px-2 py-1 bg-[#1e293b] border border-gray-600 rounded text-white text-xs text-center" />
                  </div>
                </div>
                <span className="text-xs text-gray-500">{cmds.length} 个指令</span>
              </div>
              <div className="divide-y divide-gray-700/60">
                {cmds.map(c => {
                  const issues = [];
                  if (c.isBuiltin && !c.handler && !c.isContainer && !c.isStructural && c.type !== 'custom') issues.push('无runtime');
                  if (!c.isContainer && !c.isStructural && !c.fields?.length) issues.push('无参数');
                  return (
                    <div key={c.id} className={`px-4 py-3 flex items-center gap-3 hover:bg-gray-700/30 transition-colors ${c.enabled ? '' : 'opacity-50'}`}>
                      <input type="checkbox" checked={c.enabled} onChange={e => toggleEnabled(c.id, e.target.checked)} className="rounded bg-[#1e293b] border-gray-600 shrink-0" />
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${c.bgColor} ${c.iconColor} text-xs shrink-0`}>
                        <i className={`fas ${c.icon}`}></i>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-white">{c.label}</span>
                          {c.isBuiltin && <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-900/40 text-blue-300">内置</span>}
                          {runtimeLabel(c)}
                        </div>
                        <div className="text-xs text-gray-500 font-mono">{c.type} · {c.fields?.length || 0} 个参数</div>
                        {auditMode && (
                          <div className="flex items-center gap-2 mt-1">
                            <input type="checkbox" checked={!!c.reviewedAt} onChange={e => toggleReviewed(c.id, e.target.checked)} className="rounded bg-[#1e293b] border-gray-600" />
                            <span className={`text-xs font-mono ${c.handler ? 'text-green-400' : 'text-gray-500'}`}>{c.handler || '-'}{c.local && <span className="text-blue-400"> (local)</span>}</span>
                            {issues.map(i => <span key={i} className="px-1.5 py-0.5 rounded text-[10px] bg-red-900/40 text-red-300">{i}</span>)}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <div className="flex flex-col items-end gap-0.5">
                          <div className="flex items-center gap-1">
                            <span className="text-[10px] text-gray-500">类内</span>
                            <input type="number" defaultValue={c.commandOrder ?? 0} onBlur={e => updateOrder(c.id, 'commandOrder', e.target.value)} className="w-14 px-2 py-1 bg-[#1e293b] border border-gray-600 rounded text-white text-xs text-center" />
                          </div>
                        </div>
                        <button onClick={() => openEdit(c)} className="px-2 py-1 bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 rounded text-xs transition-colors">编辑</button>
                        {!c.isBuiltin && <button onClick={() => deleteCommand(c.id)} className="px-2 py-1 bg-red-600/20 hover:bg-red-600/30 text-red-300 rounded text-xs transition-colors">删除</button>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {modalOpen && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-[#1e293b] rounded-xl border border-gray-700 w-full max-w-6xl mx-4 flex flex-col" style={{ height: '85vh', maxHeight: '900px' }}>
            <div className="px-6 py-4 border-b border-gray-700 flex items-center justify-between shrink-0">
              <h2 className="text-lg font-semibold text-white">{modalMode === 'create' ? '新增指令' : '编辑指令'}</h2>
              <button onClick={() => setModalOpen(false)} className="text-gray-400 hover:text-white"><i className="fas fa-xmark"></i></button>
            </div>

            <div className="px-6 pt-4 shrink-0">
              <div className="flex items-center gap-2">
                {[1,2,3,4].map(s => (
                  <button key={s} onClick={() => setStep(s)} className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${step === s ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}`}>
                    {s}. {['基础信息','执行方式','参数','预览'][s-1]}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex-1 overflow-hidden flex min-h-0">
              <div className="flex-1 overflow-y-auto p-6">
                {step === 1 && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm text-gray-300 mb-1">指令类型 <span className="text-red-400">*</span></label>
                        <input value={form.type} disabled={modalMode === 'edit'} onChange={e => updateForm({ type: e.target.value })} required className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm font-mono" placeholder="如 myCustomAction" />
                      </div>
                      <div>
                        <label className="block text-sm text-gray-300 mb-1">显示名称 <span className="text-red-400">*</span></label>
                        <input value={form.label} onChange={e => updateForm({ label: e.target.value })} required className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" placeholder="如 我的自定义动作" />
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm text-gray-300 mb-1">所属分类 <span className="text-red-400">*</span></label>
                      <input value={form.category} onChange={e => updateForm({ category: e.target.value })} list="categoryList" required className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" placeholder="如 数据提取" />
                      <datalist id="categoryList">{categories.map(c => <option key={c} value={c} />)}</datalist>
                    </div>
                    <div className="grid grid-cols-4 gap-4">
                      <div>
                        <label className="block text-sm text-gray-300 mb-1">图标</label>
                        <div className="flex gap-2">
                          <span className={`w-10 h-10 rounded-lg flex items-center justify-center ${form.bgColor} ${form.iconColor}`}><i className={`fas ${form.icon || 'fa-circle'}`}></i></span>
                          <input value={form.icon} onChange={e => updateForm({ icon: e.target.value })} className="flex-1 px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" placeholder="fa-circle" />
                        </div>
                      </div>
                      <div>
                        <label className="block text-sm text-gray-300 mb-1">图标颜色</label>
                        <input value={form.iconColor} onChange={e => updateForm({ iconColor: e.target.value })} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" />
                      </div>
                      <div>
                        <label className="block text-sm text-gray-300 mb-1">背景颜色</label>
                        <input value={form.bgColor} onChange={e => updateForm({ bgColor: e.target.value })} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" />
                      </div>
                      <div>
                        <label className="block text-sm text-gray-300 mb-1">类内排序</label>
                        <input type="number" value={form.commandOrder} onChange={e => updateForm({ commandOrder: e.target.value })} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" />
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm text-gray-300 mb-1">指令说明</label>
                      <textarea value={form.description} onChange={e => updateForm({ description: e.target.value })} rows={3} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm" placeholder="说明该指令的作用、用法和输出内容..."></textarea>
                    </div>
                    <div className="flex gap-4 pt-2">
                      <label className="flex items-center gap-2 text-sm text-gray-300">
                        <input type="checkbox" checked={form.isContainer} onChange={e => updateForm({ isContainer: e.target.checked })} className="rounded bg-[#0f172a] border-gray-600" />
                        容器（可含子节点）
                      </label>
                      <label className="flex items-center gap-2 text-sm text-gray-300">
                        <input type="checkbox" checked={form.isBranch} onChange={e => updateForm({ isBranch: e.target.checked })} className="rounded bg-[#0f172a] border-gray-600" />
                        分支（else/catch）
                      </label>
                      <label className="flex items-center gap-2 text-sm text-gray-300">
                        <input type="checkbox" checked={form.isStructural} onChange={e => updateForm({ isStructural: e.target.checked })} className="rounded bg-[#0f172a] border-gray-600" />
                        结构标记（endIf/endFor）
                      </label>
                    </div>
                    {form.isContainer && (
                      <div>
                        <label className="block text-sm text-gray-300 mb-1">闭合指令</label>
                        <input value={form.closesWith} onChange={e => updateForm({ closesWith: e.target.value })} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm font-mono" placeholder="endIf" />
                      </div>
                    )}
                  </div>
                )}

                {step === 2 && (
                  <div className="space-y-5">
                    <div>
                      <label className="block text-sm font-medium text-gray-200 mb-3">选择执行方式</label>
                      <div className="grid grid-cols-3 gap-4">
                        {['extension','local','none'].map(m => {
                          const labels = { extension: ['浏览器执行', '通过扩展操作页面 DOM，如点击、输入、滚动、提取等', 'fa-chrome', 'bg-blue-600/20 text-blue-400'],
                            local: ['后端执行', '不经过浏览器，如设置变量、HTTP 请求、日志等', 'fa-server', 'bg-gray-600/30 text-gray-300'],
                            none: ['无执行', '容器、分支、结构标记或自定义代码', 'fa-code-branch', 'bg-orange-600/20 text-orange-400'] };
                          const [title, desc, icon, color] = labels[m];
                          return (
                            <div key={m} onClick={() => { updateForm({ runtimeMode: m, handler: m === 'none' ? '' : form.handler, local: m === 'local' }); }} className={`cursor-pointer rounded-xl border-2 p-4 transition-colors ${form.runtimeMode === m ? 'border-blue-500 bg-blue-900/20' : 'border-gray-600 bg-[#1e293b]'}`}>
                              <div className={`w-10 h-10 rounded-lg flex items-center justify-center mb-3 ${color}`}><i className={`fas ${icon} text-lg`}></i></div>
                              <div className="font-medium text-white mb-1">{title}</div>
                              <div className="text-xs text-gray-400">{desc}</div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {form.runtimeMode !== 'none' && (
                      <div>
                        <label className="block text-sm text-gray-300 mb-2">动作模板</label>
                        <select value={currentPresetValue()} onChange={e => applyPreset(e.target.value)} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm">
                          <option value="">-- 选择动作模板 --</option>
                          {(ACTION_PRESETS[form.runtimeMode] || []).map((p, i) => <option key={`${form.runtimeMode}:${i}`} value={`${form.runtimeMode}:${i}`}>{p.label}</option>)}
                        </select>
                      </div>
                    )}

                    <div className={`border border-gray-600 rounded-lg p-4 space-y-3 ${showAdvanced ? '' : 'hidden'}`}>
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-gray-300">高级设置</span>
                        <span className="text-xs text-gray-500">一般不需要修改</span>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">Handler 名称</label>
                          <select value={form.handler} onChange={e => updateForm({ handler: e.target.value })} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm font-mono">
                            <option value="">-- 选择 handler --</option>
                            {handlers.map(h => <option key={h} value={h}>{h}</option>)}
                          </select>
                        </div>
                        <div className="flex items-end pb-2">
                          <label className="flex items-center gap-2 text-sm text-gray-300">
                            <input type="checkbox" checked={form.local} onChange={e => updateForm({ local: e.target.checked })} className="rounded bg-[#0f172a] border-gray-600" />
                            local（后端本地执行）
                          </label>
                        </div>
                      </div>
                      {form.handler === 'elementAction' && (
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">elementAction 的 action 值</label>
                          <input value={form.action} onChange={e => updateForm({ action: e.target.value })} className="w-full px-3 py-2 bg-[#0f172a] border border-gray-600 rounded-lg text-white text-sm font-mono" placeholder="click" />
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-3">
                      <button onClick={() => setShowAdvanced(s => !s)} className="text-xs text-blue-300 hover:text-blue-200">
                        <i className="fas fa-sliders mr-1"></i>{showAdvanced ? '隐藏高级设置' : '高级设置'}
                      </button>
                      <button onClick={runSmartAudit} disabled={auditing} className="px-3 py-1.5 bg-purple-600 hover:bg-purple-500 disabled:bg-purple-800/50 text-white rounded text-xs transition-colors">
                        <i className="fas fa-wand-magic-sparkles mr-1"></i>{auditing ? '分析中…' : '智能检验'}
                      </button>
                    </div>

                    {auditResult && (
                      <div className="space-y-2 bg-[#0f172a] rounded-lg p-3">
                        <div className={`text-xs font-medium ${auditResult.recommendation.confidence === 'high' ? 'text-green-400' : auditResult.recommendation.confidence === 'medium' ? 'text-yellow-400' : 'text-gray-400'}`}>
                          {auditResult.recommendation.needsRuntime ? '推荐启用 runtime' : '推荐不启用 runtime'}（置信度: {auditResult.recommendation.confidence}）
                        </div>
                        <div className="text-gray-400 text-xs">{auditResult.recommendation.reason}</div>
                        {auditResult.recommendation.handler && <div className="text-gray-300 text-xs">推荐 handler: <span className="font-mono">{auditResult.recommendation.handler}</span>{auditResult.recommendation.local ? '，local=是' : '，local=否'}</div>}
                        <div className="space-y-1">
                          {auditResult.issues.length > 0 ? auditResult.issues.map((i, idx) => <div key={idx} className="px-2 py-1 rounded text-xs bg-red-900/40 text-red-300">{i}</div>) : <div className="px-2 py-1 rounded text-xs bg-green-900/40 text-green-300">当前配置与推荐一致，无问题</div>}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {step === 3 && (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-gray-200">参数定义</span>
                      <button onClick={() => addParam()} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs transition-colors">
                        <i className="fas fa-plus mr-1"></i>添加参数
                      </button>
                    </div>
                    <div className="space-y-3">
                      {params.length === 0 && <p className="text-center py-8 text-gray-500 text-sm">暂无参数，点击上方按钮添加</p>}
                      {params.map(p => (
                        <div key={p._id} className="bg-[#1e293b] border border-gray-600 rounded-lg overflow-hidden">
                          <div className="px-3 py-2 bg-[#252f47] flex items-center gap-2 cursor-pointer" onClick={() => updateParam(p._id, { expanded: !p.expanded })}>
                            <i className="fas fa-grip-vertical text-gray-400 text-xs"></i>
                            <span className="text-sm font-medium text-white">{p.name || '新参数'}</span>
                            <span className="text-xs text-gray-400 truncate flex-1">{p.label}</span>
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-600 text-gray-300">{FIELD_TYPE_LABELS[p.type] || '文本'}</span>
                            {p.required && <span className="text-[10px] text-red-300 ml-1">必填</span>}
                            <button onClick={e => { e.stopPropagation(); removeParam(p._id); }} className="ml-2 text-red-400 hover:text-red-300 text-xs"><i className="fas fa-trash"></i></button>
                          </div>
                          {p.expanded && (
                            <div className="px-4 py-3 space-y-3">
                              <div className="grid grid-cols-2 gap-3">
                                <div>
                                  <label className="block text-xs text-gray-400 mb-1">参数名</label>
                                  <input value={p.name} onChange={e => updateParam(p._id, { name: e.target.value })} className="w-full px-2 py-1.5 bg-[#0f172a] border border-gray-600 rounded text-white text-xs font-mono" />
                                </div>
                                <div>
                                  <label className="block text-xs text-gray-400 mb-1">显示名称</label>
                                  <input value={p.label} onChange={e => updateParam(p._id, { label: e.target.value })} className="w-full px-2 py-1.5 bg-[#0f172a] border border-gray-600 rounded text-white text-xs" />
                                </div>
                              </div>
                              <div className="grid grid-cols-2 gap-3">
                                <div>
                                  <label className="block text-xs text-gray-400 mb-1">类型</label>
                                  <select value={p.type} onChange={e => updateParam(p._id, { type: e.target.value })} className="w-full px-2 py-1.5 bg-[#0f172a] border border-gray-600 rounded text-white text-xs">
                                    {Object.keys(FIELD_TYPE_LABELS).map(t => <option key={t} value={t}>{FIELD_TYPE_LABELS[t]} ({t})</option>)}
                                  </select>
                                </div>
                                <div>
                                  <label className="block text-xs text-gray-400 mb-1">分组</label>
                                  <select value={p.group} onChange={e => updateParam(p._id, { group: e.target.value })} className="w-full px-2 py-1.5 bg-[#0f172a] border border-gray-600 rounded text-white text-xs">
                                    <option value="input">输入</option>
                                    <option value="output">输出</option>
                                    <option value="advanced">高级</option>
                                  </select>
                                </div>
                              </div>
                              <div className="grid grid-cols-2 gap-3">
                                <div>
                                  <label className="block text-xs text-gray-400 mb-1">默认值</label>
                                  <input value={p.default} onChange={e => updateParam(p._id, { default: e.target.value })} className="w-full px-2 py-1.5 bg-[#0f172a] border border-gray-600 rounded text-white text-xs" />
                                </div>
                                <div>
                                  <label className="block text-xs text-gray-400 mb-1">占位提示</label>
                                  <input value={p.placeholder} onChange={e => updateParam(p._id, { placeholder: e.target.value })} className="w-full px-2 py-1.5 bg-[#0f172a] border border-gray-600 rounded text-white text-xs" />
                                </div>
                              </div>
                              <div>
                                <label className="block text-xs text-gray-400 mb-1">选项 <span className="text-gray-600">(仅下拉选择，格式：标签:值,标签:值)</span></label>
                                <input value={p.options} onChange={e => updateParam(p._id, { options: e.target.value })} className="w-full px-2 py-1.5 bg-[#0f172a] border border-gray-600 rounded text-white text-xs" />
                              </div>
                              <div>
                                <label className="block text-xs text-gray-400 mb-1">字段说明</label>
                                <input value={p.description} onChange={e => updateParam(p._id, { description: e.target.value })} className="w-full px-2 py-1.5 bg-[#0f172a] border border-gray-600 rounded text-white text-xs" />
                              </div>
                              <div className="flex items-center gap-4">
                                <label className="flex items-center gap-2 text-xs text-gray-300">
                                  <input type="checkbox" checked={p.required} onChange={e => updateParam(p._id, { required: e.target.checked })} className="rounded bg-[#0f172a] border-gray-600" />
                                  必填
                                </label>
                                <label className="flex items-center gap-2 text-xs text-gray-300">
                                  <input type="checkbox" checked={p.isPrimaryElement} onChange={e => updateParam(p._id, { isPrimaryElement: e.target.checked })} className="rounded bg-[#0f172a] border-gray-600" />
                                  主元素
                                </label>
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {step === 4 && (
                  <div className="space-y-5">
                    <div>
                      <span className="text-sm font-medium text-gray-200">指令卡片预览</span>
                      <div className="mt-3">
                        <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-gray-600 bg-[#1e293b] max-w-xs">
                          <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${payloadPreview.bgColor} ${payloadPreview.iconColor} text-xs shrink-0`}>
                            <i className={`fas ${payloadPreview.icon}`}></i>
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-sm text-white truncate">{payloadPreview.label}</div>
                            <div className="text-[10px] text-gray-500 truncate">{payloadPreview.type} · {payloadPreview.category}</div>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div>
                      <span className="text-sm font-medium text-gray-200">节点属性表单预览</span>
                      <div className="mt-3 bg-[#0f172a] rounded-lg border border-gray-700 p-4">
                        {visibleFields.length === 0 ? <p className="text-gray-500 text-sm">该指令没有可见参数</p> : visibleFields.map(f => (
                          <div key={f.name} className="mb-3">
                            <label className="flex items-center gap-2 text-xs text-gray-300 mb-1">
                              <i className={`fas ${FIELD_TYPE_ICONS[f.type]} text-gray-500 text-[10px]`}></i>
                              {f.label}
                              {f.required && <span className="text-red-400">*</span>}
                              <span className="text-[10px] text-gray-600 font-mono">{f.name}</span>
                            </label>
                            {f.type === 'select' ? (
                              <select className="w-full px-2 py-1 bg-[#1e293b] border border-gray-600 rounded text-xs text-white" disabled>
                                <option>{f.default !== undefined ? String(f.default) : '请选择'}</option>
                                {(f.options || []).map((o, i) => <option key={i} value={typeof o === 'object' ? o.value : o}>{typeof o === 'object' ? o.label : o}</option>)}
                              </select>
                            ) : f.type === 'bool' ? (
                              <label className="flex items-center gap-2 text-sm text-gray-300">
                                <input type="checkbox" checked={!!f.default} disabled className="rounded bg-[#1e293b] border-gray-600" /> {f.label}
                              </label>
                            ) : f.type === 'textarea' ? (
                              <textarea className="w-full px-2 py-1 bg-[#1e293b] border border-gray-600 rounded text-xs text-white" rows={2} disabled defaultValue={f.default !== undefined ? String(f.default) : ''} />
                            ) : (
                              <input type="text" className="w-full px-2 py-1 bg-[#1e293b] border border-gray-600 rounded text-xs text-white" disabled value={f.default !== undefined ? String(f.default) : ''} />
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <span className="text-sm font-medium text-gray-200">配置摘要</span>
                      <div className="mt-3 text-xs text-gray-400 font-mono bg-[#0f172a] rounded-lg border border-gray-700 p-3 space-y-1">
                        <div>type: {payloadPreview.type}</div>
                        <div>handler: {payloadPreview.handler || '无'} · local: {String(payloadPreview.local)}</div>
                        <div>action: {form.action || '无'}</div>
                        <div>参数: {payloadPreview.fields.map(f => f.name).join(', ') || '无'}</div>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="w-80 border-l border-gray-700 bg-[#1e293b]/50 p-5 overflow-y-auto hidden lg:block">
                <div className="text-sm font-medium text-gray-200 mb-3">实时预览</div>
                <div className="mb-5">
                  <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-gray-600 bg-[#1e293b]">
                    <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${payloadPreview.bgColor} ${payloadPreview.iconColor} text-xs shrink-0`}>
                      <i className={`fas ${payloadPreview.icon}`}></i>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white truncate">{payloadPreview.label}</div>
                      <div className="text-[10px] text-gray-500 truncate">{payloadPreview.type} · {payloadPreview.category}</div>
                    </div>
                  </div>
                </div>
                <div className="text-xs text-gray-500 mb-2">执行方式</div>
                <div className="mb-4">
                  {<span className={`px-2 py-1 rounded text-xs ${payloadPreview.isContainer ? 'bg-orange-900/40 text-orange-300' : payloadPreview.isStructural ? 'bg-purple-900/40 text-purple-300' : !payloadPreview.handler ? 'bg-gray-700 text-gray-400' : payloadPreview.local ? 'bg-gray-700 text-gray-300' : 'bg-blue-900/40 text-blue-300'}`}>
                    {payloadPreview.isContainer ? '容器' : payloadPreview.isStructural ? '结构' : !payloadPreview.handler ? '无执行' : payloadPreview.local ? '后端执行' : '浏览器执行'}
                  </span>}
                </div>
                <div className="text-xs text-gray-500 mb-2">参数数量</div>
                <div className="text-sm text-white">{payloadPreview.fields.length}</div>
              </div>
            </div>

            <div className="px-6 py-4 border-t border-gray-700 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <input type="checkbox" checked={form.enabled} onChange={e => updateForm({ enabled: e.target.checked })} className="rounded bg-[#1e293b] border-gray-600" />
                <label className="text-sm text-gray-300 cursor-pointer">启用该指令</label>
              </div>
              <div className="flex items-center gap-3">
                <button onClick={prevStep} disabled={step === 1} className="px-4 py-2 bg-gray-600 hover:bg-gray-500 text-white rounded-lg text-sm disabled:opacity-50">上一步</button>
                {step === 4 ? (
                  <button onClick={saveCommand} className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg text-sm">保存</button>
                ) : (
                  <button onClick={nextStep} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm">下一步</button>
                )}
                <button onClick={() => setModalOpen(false)} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm">取消</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
