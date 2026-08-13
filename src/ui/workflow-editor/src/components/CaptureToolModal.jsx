import { useState, useEffect, useRef } from 'react';
import { api } from '../api';
import ImageLightbox from './ImageLightbox';

/**
 * 元素捕获工具 — 原生模态框
 * 布局参考影刀: 无元素列表, 捕获后直接编辑当前元素
 * 设计约定: 主色 #1677ff / hover #4096ff / 边框 #d9d9d9 / 输入底 #fafafa,
 *          字号三级 (label=text-xs font-medium, 正文=text-sm, 辅助=text-[11px] 仅非交互)
 */
const PRIMARY_BTN = 'px-3 py-1.5 text-xs text-white bg-[#1677ff] rounded hover:bg-[#4096ff] disabled:opacity-50 transition-colors flex items-center gap-1.5';
const SECTION_LABEL = 'text-xs font-medium text-gray-500';

export default function CaptureToolModal({ wfId, onClose, onSaved }) {
  const [mode, setMode] = useState(0); // 0=推荐方案 1=手动编辑
  const [capturingMode, setCapturingMode] = useState(null); // 'desktop' | 'web' | null
  const [captureError, setCaptureError] = useState('');
  const [showHelp, setShowHelp] = useState(false);
  const [showJsCode, setShowJsCode] = useState(false); // 手动验证代码块默认折叠
  const [savedId, setSavedId] = useState(null); // 已保存元素ID, null=未保存
  const [cur, setCur] = useState(null); // 当前编辑元素
  const [cands, setCands] = useState([]);
  const [selector, setSelector] = useState('');
  const [domPath, setDomPath] = useState([]);
  const [domChecked, setDomChecked] = useState([]);
  const [attrVars, setAttrVars] = useState({});
  const [selLevel, setSelLevel] = useState(-1);
  const [domAttrs, setDomAttrs] = useState({});
  const [domFragile, setDomFragile] = useState([]);
  const [sortDir, setSortDir] = useState({ syntax: false, family: false, match: false });
  const [extBrowsers, setExtBrowsers] = useState(null); // {chrome: n, edge: n} | null=未检测
  const [verifyResult, setVerifyResult] = useState(null); // {ok, msg} 常驻结果条
  const [toast, setToast] = useState(null); // {msg, type}
  const [lightbox, setLightbox] = useState(null); // {src, alt} 截图灯箱
  const [chainKind, setChainKind] = useState('uia'); // 桌面元素层级视图: 'uia' | 'win32'
  const toastTimer = useRef(null);

  const strip = (s) => (s || '').replace(/^(css:|xpath:|drission:)/i, '');

  const showToast = (msg, type = 'info') => {
    setToast({ msg, type });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2500);
  };
  useEffect(() => () => clearTimeout(toastTimer.current), []);

  // 轮询扩展在线状态（按浏览器细分）— 弹窗关闭即停止
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const data = await api.getExtensionStatus();
        const browsers = {};
        (data.browsers || []).forEach(b => { browsers[b.browser] = b.count; });
        setExtBrowsers(browsers);
      } catch {
        setExtBrowsers({});
      }
    };
    checkStatus();
    const timer = setInterval(checkStatus, 3000);
    return () => clearInterval(timer);
  }, []);

  // 捕获元素 → 直接填入编辑器
  const startCapture = async (m) => {
    setCapturingMode(m);
    setCaptureError('');
    setVerifyResult(null);
    try {
      const data = await api.runGuiPicker(m);
      if (data.cancelled) { showToast('已取消'); return; }
      setSavedId(null);
      setCur(data);
      const cs = data.candidates || [];
      setCands(cs.filter(c => ['css', 'xpath'].includes((c.family || c.type || '').toLowerCase())));
      const path = data.dom_path || data.path || [];
      setDomPath(path);
      setDomChecked(path.map(() => true));
      setAttrVars({});
      setSelLevel(-1);
      setDomAttrs(data.attrs || {});
      setSelector(strip(data.css_selector || (cs[0] && cs[0].syntax) || ''));
      setMode(0);
      setChainKind('uia'); // 捕获后默认展示 UIA 层级（有则用）
      showToast('捕获成功', 'success');
    } catch (e) {
      if (e.message !== 'cancelled') setCaptureError(String(e));
    } finally {
      setCapturingMode(null);
    }
  };

  const sortCands = (col) => {
    const nd = { ...sortDir, [col]: !sortDir[col] };
    setSortDir(nd);
    const idx = { syntax: 0, family: 1, match: 2 }[col];
    const sorted = [...cands].sort((a, b) => {
      let va = idx === 2 ? (a.matchCount || 0) : (a[['syntax', 'family', 'match'][idx]] || '');
      let vb = idx === 2 ? (b.matchCount || 0) : (b[['syntax', 'family', 'match'][idx]] || '');
      if (typeof va === 'string') va = va.toLowerCase();
      if (typeof vb === 'string') vb = vb.toLowerCase();
      return nd[col] ? (va > vb ? -1 : 1) : (va < vb ? -1 : 1);
    });
    setCands(sorted);
  };

  // 勾选/取消勾选层级 (参与选择器生成)
  const toggleDomCheck = (i) => {
    const nd = [...domChecked]; nd[i] = !nd[i];
    setDomChecked(nd);
    updateDomSel(nd, attrVars, selLevel);
  };

  // 选中层级 (显示该层属性)
  const selectDomLevel = (i) => {
    setSelLevel(i);
    const node = domPath[i];
    const nodeAttrs = (node && typeof node === 'object' && node.attrs) || {};
    setDomAttrs(nodeAttrs);
    setDomFragile((node && typeof node === 'object' && node.fragile) || []);
  };

  const toggleAttr = (i, key) => {
    const na = { ...attrVars, [i]: { ...(attrVars[i] || {}), [key]: !(attrVars[i] || {})[key] } };
    setAttrVars(na);
    updateDomSel(domChecked, na, selLevel);
  };

  const updateDomSel = (checked, av, level) => {
    const parts = [];
    for (let i = 0; i < domPath.length; i++) {
      if (!checked[i]) continue;
      const n = domPath[i];
      let p = typeof n === 'object' ? (n.tag || 'div') : String(n);
      if (n && n.id) p += '#' + n.id;
      if (n && n.classes?.length) p += '.' + n.classes.slice(0, 3).join('.');
      if (av[i]) {
        for (const [k, v] of Object.entries(av[i])) {
          if (v) p += `[${k}="${(n && n.attrs && n.attrs[k]) || ''}"]`;
        }
      }
      parts.push(p);
    }
    setSelector(parts.join(' > ') || '');
  };

  const selectAll = () => { const nd = domChecked.map(() => true); setDomChecked(nd); updateDomSel(nd, attrVars, selLevel); };
  const selectNone = () => { const nd = domChecked.map(() => false); setDomChecked(nd); updateDomSel(nd, attrVars, selLevel); };

  const verify = async () => {
    if (!cur) return showToast('请先捕获元素');
    try {
      if (cur.element_type === 'web' && (cur.css_selector || selector)) {
        // web 元素: 浏览器验证选择器 (extension querySelectorAll + 可见/不可见统计)
        const sel = strip(selector || cur.css_selector);
        const d = await api.verifyWebSelector(sel);
        if (d.found) {
          const hitPage = d.tabUrl ? ` · ${String(d.tabUrl).replace(/^https?:\/\//, '').slice(0, 40)}` : '';
          const dupHint = (d.sameUrlCount || 1) > 1 ? ` · ⚠️ 打开 ${d.sameUrlCount} 个相同页面，仅验证其中一个` : '';
          setVerifyResult({ ok: true, msg: `命中 ${d.count ?? 0} 个 · 可见 ${d.visible ?? 0} · 不可见 ${d.invisible ?? 0}${hitPage}${dupHint}` });
        } else if ((d.count || 0) > 0) {
          setVerifyResult({ ok: false, msg: `匹配 ${d.count} 个但均不可见` });
        } else {
          const scannedN = d.scanned?.length;
          setVerifyResult({ ok: false, msg: `${d.error || '未找到'}${scannedN ? `（已扫描 ${scannedN} 个可见标签页）` : ''}` });
        }
      } else {
        // 桌面元素: GUI flash_element 闪烁
        const d = await api.runGuiVerify(cur);
        setVerifyResult({ ok: !!d.found, msg: d.found ? '元素存在' : '元素失效' });
      }
    } catch (e) { setVerifyResult({ ok: false, msg: '验证失败: ' + e.message }); }
  };

  const save = async () => {
    if (!cur) return showToast('请先捕获元素');
    try {
      const payload = { ...cur, css_selector: selector, name: cur.name || '捕获元素' };
      const name = String(cur.name || '捕获元素').substring(0, 128) || '捕获元素';
      if (savedId) {
        await api.updateWorkflowElement(wfId, savedId, { name, attributes: payload });
      } else {
        const created = await api.createWorkflowElement(wfId, { name, attributes: payload });
        if (created && created.id) setSavedId(created.id);
      }
      showToast('已保存', 'success');
      onSaved && onSaved();
      onClose();
    } catch (e) { showToast('保存失败: ' + e.message, 'error'); }
  };

  const copySel = () => { navigator.clipboard.writeText(selector); showToast('已复制'); };

  // 生成控制台验证 JS 代码 (CSS vs XPath)
  const jsCode = selector
    ? (selector.startsWith('/')
        ? `const r = document.evaluate(\`${selector}\`, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);\nconsole.log('匹配:', r.snapshotLength); r.snapshotItem(0)?.scrollIntoView();`
        : `const el = document.querySelectorAll(\`${selector}\`);\nconsole.log('匹配:', el.length); el[0]?.scrollIntoView();`)
    : '';

  const bothOffline = extBrowsers && !extBrowsers.chrome && !extBrowsers.edge;

  // ── 桌面元素（win32/uia）派生数据 ──
  // 按数据形态判定：有 candidates/dom_path/css_selector 才是网页捕获；
  // 桌面捕获只有 win32_path/uia_path 祖先链 —— 包括桌面模式捕获浏览器窗口
  // （element_type 会被标成 web，但没有任何网页选择器数据，仍应走桌面视图）
  const hasWebData = !!cur && !!(
    (cur.candidates || []).length
    || (cur.dom_path || cur.path || []).length
    || cur.css_selector
  );
  const isDesktop = !!cur && !hasWebData;
  const uiaPath = (cur && cur.uia_path) || [];
  const win32Path = (cur && cur.win32_path) || [];
  // 双链都存在时按 chainKind 切换；只有一条时用有的那条
  const hasBothChains = isDesktop && uiaPath.length > 0 && win32Path.length > 0;
  const useUiaChain = hasBothChains ? chainKind === 'uia' : uiaPath.length > 0;
  const desktopPath = useUiaChain ? uiaPath : win32Path;
  // 目标层级：UIA 链用捕获时的 target_index；win32 链目标即叶子（最后层）
  const rawTarget = useUiaChain
    ? ((cur && cur.uia_target_index) ?? -1)
    : -1;
  const targetIdx = (rawTarget >= 0 && rawTarget < desktopPath.length)
    ? rawTarget
    : desktopPath.length - 1;
  const desktopLeaf = desktopPath.length ? desktopPath[targetIdx] : {};

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
        <div className="bg-gray-50 rounded-lg shadow-2xl w-[95vw] h-[90vh] max-w-6xl flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 bg-white border-b shrink-0">
            <div className="flex items-center gap-3">
              <h2 className="text-sm font-semibold text-gray-800">元素捕获工具</h2>
              <button
                onClick={() => startCapture('desktop')}
                disabled={!!capturingMode}
                className={PRIMARY_BTN}
                title="捕获桌面窗口/控件（Win32+UIA）"
              >
                {capturingMode === 'desktop'
                  ? <><i className="fas fa-spinner fa-spin"></i>捕获中... Alt+点击 选取目标</>
                  : <><i className="fas fa-crosshairs"></i>捕获桌面元素</>}
              </button>
              <button
                onClick={() => startCapture('desktop_mask')}
                disabled={!!capturingMode}
                className={PRIMARY_BTN}
                title="捕获桌面窗口/控件（全屏遮罩式高亮，Win32+UIA）"
              >
                {capturingMode === 'desktop_mask'
                  ? <><i className="fas fa-spinner fa-spin"></i>捕获中... Alt+点击 选取目标</>
                  : <><i className="fas fa-vector-square"></i>捕获桌面元素新</>}
              </button>
              <button
                onClick={() => startCapture('web')}
                disabled={!!capturingMode}
                className={PRIMARY_BTN}
                title="对最前面的浏览器页面进入 DOM 拾取"
              >
                {capturingMode === 'web'
                  ? <><i className="fas fa-spinner fa-spin"></i>捕获中... Alt+点击 选取目标</>
                  : <><i className="fas fa-globe"></i>捕获网页元素</>}
              </button>
              {/* 扩展在线状态（按浏览器细分） */}
              <div className="flex items-center gap-2 border-l border-gray-200 pl-3 ml-1">
                {['chrome', 'edge'].map(b => {
                  const online = !!extBrowsers?.[b];
                  const label = b === 'edge' ? 'Edge' : 'Chrome';
                  return (
                    <span
                      key={b}
                      className="flex items-center gap-1 text-[11px] text-gray-400"
                      title={`${label} 扩展${online ? '在线' : '离线'}`}
                    >
                      <span className={`w-2 h-2 rounded-full ${online ? 'bg-green-500' : 'bg-gray-300'}`}></span>
                      {label} {online ? '在线' : '离线'}
                    </span>
                  );
                })}
                {bothOffline && (
                  <span className="text-[11px] text-amber-500">未检测到浏览器扩展在线</span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setShowHelp(v => !v)}
                className={`w-7 h-7 flex items-center justify-center rounded hover:bg-gray-100 ${showHelp ? 'text-[#1677ff]' : 'text-gray-400 hover:text-gray-600'}`}
                title="使用说明"
              >
                <i className="fas fa-question-circle text-sm"></i>
              </button>
              <button
                onClick={onClose}
                className="w-7 h-7 flex items-center justify-center rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100"
                title="关闭"
              >
                <i className="fas fa-times text-sm"></i>
              </button>
            </div>
          </div>

          {/* 使用说明（可折叠） */}
          {showHelp && (
            <div className="px-4 py-3 bg-blue-50 border-b text-xs text-blue-700 space-y-2">
              <p className="font-medium">
                网页元素：先打开 Chrome/Edge 并把目标页面放在最前面；桌面控件直接在当前屏幕上框选。
              </p>
              <ol className="list-decimal pl-4 space-y-1">
                <li>点「捕获桌面元素」→ 鼠标移到目标上（蓝色边框高亮）→ Alt+点击 确认</li>
                <li>点「捕获网页元素」→ 自动进入最前面浏览器的 DOM 拾取 → 鼠标悬停查看元素 → Alt+点击 确认；Alt+1/2 切父子级</li>
                <li>网页捕获前提：打开 Chrome/Edge → chrome://extensions（edge://extensions）→ 开发者模式 → 加载已解压的扩展 → 选择项目目录下 <code className="bg-white border border-blue-100 px-1 rounded">extension/</code> 文件夹</li>
                <li>捕获后编辑名称/选择器，验证通过后保存，元素自动同步到元素库</li>
              </ol>
            </div>
          )}

          {/* Body */}
          <div className="flex-1 flex flex-col gap-3 p-4 overflow-y-auto">
            {/* 捕获错误（可关闭） */}
            {captureError && (
              <div className="flex items-center justify-between px-3 py-2 bg-red-50 border border-red-200 rounded text-xs text-red-600 shrink-0">
                <span><i className="fas fa-exclamation-circle mr-1.5"></i>{captureError}</span>
                <button onClick={() => setCaptureError('')} className="ml-3 opacity-60 hover:opacity-100">
                  <i className="fas fa-times"></i>
                </button>
              </div>
            )}

            {!cur ? (
              /* 统一引导空态 */
              <div className="flex-1 flex flex-col items-center justify-center text-gray-400 gap-3">
                <i className="fas fa-crosshairs text-3xl text-gray-300"></i>
                <p className="text-sm">点击上方「捕获桌面元素」或「捕获网页元素」开始</p>
                <p className="text-[11px]">捕获后可在此编辑选择器、验证并保存到元素库</p>
              </div>
            ) : (
              <>
                {/* 名称行 */}
                <div className="flex items-center gap-3">
                  <label className={`${SECTION_LABEL} w-10 shrink-0`}>名称</label>
                  <input
                    value={(cur && cur.name) || ''}
                    onChange={(e) => setCur({ ...cur, name: e.target.value })}
                    placeholder="编辑元素名称"
                    className="flex-1 px-2 py-1.5 bg-[#fafafa] border border-[#d9d9d9] rounded text-sm text-gray-700 focus:outline-none focus:border-[#1677ff]"
                  />
                  {cur && cur.screenshot && (
                    <div
                      className="relative group shrink-0 cursor-zoom-in"
                      title="点击预览大图"
                      onClick={() => setLightbox({ src: cur.screenshot, alt: cur.name || '捕获截图' })}
                    >
                      <img src={cur.screenshot} alt="截图"
                           className="h-14 w-auto rounded object-contain border border-[#d9d9d9] bg-white" />
                      <div className="absolute inset-0 rounded bg-black/0 group-hover:bg-black/30 flex items-center justify-center opacity-0 group-hover:opacity-100 transition">
                        <i className="fas fa-expand text-white text-xs"></i>
                      </div>
                    </div>
                  )}
                </div>

                {/* ── 桌面元素视图（win32/uia）：身份卡片 + 控件层级路径 ── */}
                {isDesktop && (
                  <>
                    {/* UIA 依赖缺失警告（静默降级防护） */}
                    {cur.uia_available === false && (
                      <div className="flex items-start gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-700 shrink-0">
                        <i className="fas fa-exclamation-triangle mt-0.5"></i>
                        <span>UIA 依赖不可用（缺少 uiautomation），本次仅捕获 Win32 窗口层级。单窗口应用（浏览器/终端等）将无法获取内部控件，请在运行环境中安装 uiautomation。</span>
                      </div>
                    )}
                    {/* 目标提权 + 自身未提权 → UIPI 拦截警告 */}
                    {cur.elevation_blocked && (
                      <div className="flex items-start gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-700 shrink-0">
                        <i className="fas fa-shield-alt mt-0.5"></i>
                        <span>目标应用以管理员身份运行，而本工具未提权，系统（UIPI）拦截了对其内部控件的读取，本次仅捕获到窗口层级。请退出后以管理员身份运行本工具再捕获。</span>
                      </div>
                    )}
                    {/* 身份卡片（目标层级） */}
                    <div className="bg-white rounded border border-[#d9d9d9] p-3 shrink-0">
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`px-1.5 py-0.5 rounded text-[11px] ${useUiaChain ? 'bg-green-50 text-green-600' : 'bg-purple-50 text-purple-600'}`}>
                          {useUiaChain ? 'UIA 桌面控件' : 'Win32 桌面控件'}
                        </span>
                        <span className="text-[11px] text-gray-400">定位方式：顶层窗口按标题模糊匹配 → 逐层下钻（按兄弟序号精确匹配）</span>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        {useUiaChain ? (
                          <>
                            <div>
                              <div className="text-[11px] text-gray-400">名称</div>
                              <div className="text-xs text-gray-700 bg-[#fafafa] px-2 py-1 rounded font-mono break-all">{desktopLeaf.name || '-'}</div>
                            </div>
                            <div>
                              <div className="text-[11px] text-gray-400">控件类型</div>
                              <div className="text-xs text-gray-700 bg-[#fafafa] px-2 py-1 rounded font-mono">{desktopLeaf.control_type || '-'}</div>
                            </div>
                            <div>
                              <div className="text-[11px] text-gray-400">AutomationId</div>
                              <div className="text-xs text-gray-700 bg-[#fafafa] px-2 py-1 rounded font-mono break-all">{desktopLeaf.automation_id || '(空)'}</div>
                            </div>
                            <div>
                              <div className="text-[11px] text-gray-400">类名 · 兄弟序号</div>
                              <div className="text-xs text-gray-700 bg-[#fafafa] px-2 py-1 rounded font-mono break-all">
                                {desktopLeaf.class_name || '-'}{desktopLeaf.index != null ? ` · #${desktopLeaf.index}` : ''}
                              </div>
                            </div>
                          </>
                        ) : (
                          <>
                            <div>
                              <div className="text-[11px] text-gray-400">类名</div>
                              <div className="text-xs text-gray-700 bg-[#fafafa] px-2 py-1 rounded font-mono break-all">{desktopLeaf.class_name || '-'}</div>
                            </div>
                            <div>
                              <div className="text-[11px] text-gray-400">标题</div>
                              <div className="text-xs text-gray-700 bg-[#fafafa] px-2 py-1 rounded break-all">{desktopLeaf.title || '(空)'}</div>
                            </div>
                            <div>
                              <div className="text-[11px] text-gray-400">兄弟序号 · 尺寸</div>
                              <div className="text-xs text-gray-700 bg-[#fafafa] px-2 py-1 rounded">
                                {desktopLeaf.index != null ? `#${desktopLeaf.index} · ` : ''}{desktopLeaf.rect?.width || '?'} × {desktopLeaf.rect?.height || '?'}
                              </div>
                            </div>
                            <div>
                              <div className="text-[11px] text-gray-400">状态</div>
                              <div className="text-xs text-gray-700 bg-[#fafafa] px-2 py-1 rounded">
                                {desktopLeaf.enabled === false ? '禁用' : '启用'}{desktopLeaf.visible === false ? ' · 不可见' : ''}
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    </div>

                    {/* 控件层级路径 */}
                    <div className="flex-1 bg-white rounded border border-[#d9d9d9] p-3 overflow-y-auto min-h-0">
                      <div className="flex items-center gap-2 mb-2">
                        <span className={SECTION_LABEL}>控件层级路径（{desktopPath.length} 层）</span>
                        {hasBothChains && (
                          <div className="flex gap-0.5 ml-auto bg-gray-100 rounded p-0.5">
                            {[['uia', 'UIA'], ['win32', 'Win32']].map(([k, label]) => (
                              <button key={k} onClick={() => setChainKind(k)}
                                className={`px-2 py-0.5 text-[11px] rounded ${chainKind === k ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>
                                {label}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                      {useUiaChain && (
                        <div className="text-[11px] text-gray-400 mb-1.5">点击某层设为目标层级（运行时定位到该层）</div>
                      )}
                      <div className="space-y-0.5">
                        {desktopPath.map((node, idx) => {
                          const isTarget = idx === targetIdx;
                          const selectable = useUiaChain;
                          return (
                            <div key={idx}
                              onClick={selectable ? () => setCur({ ...cur, uia_target_index: idx }) : undefined}
                              title={selectable ? '设为目标层级' : undefined}
                              className={`text-xs px-2 py-1 rounded flex items-center gap-2 ${isTarget ? 'bg-blue-50 ring-1 ring-blue-200' : 'bg-[#fafafa]'} ${selectable ? 'cursor-pointer hover:bg-blue-50/60' : ''}`}>
                              <span className="text-gray-300 w-4 text-right shrink-0">{idx === 0 ? '⊞' : '└'}</span>
                              <span className={`font-mono text-[11px] ${useUiaChain ? 'text-green-600' : 'text-purple-600'}`}>
                                {useUiaChain ? (node.control_type || node.class_name) : node.class_name}
                              </span>
                              {node.index != null && (
                                <span className="text-gray-400 text-[10px] font-mono shrink-0">#{node.index}</span>
                              )}
                              {(useUiaChain ? node.name : node.title) ? (
                                <span className="text-gray-500 truncate">"{useUiaChain ? node.name : node.title}"</span>
                              ) : null}
                              {useUiaChain && node.automation_id && (
                                <span className="text-gray-400 text-[10px] font-mono truncate shrink" title={node.automation_id}>{node.automation_id}</span>
                              )}
                              {node.enabled === false && (
                                <span className="text-amber-500 text-[10px] shrink-0">禁用</span>
                              )}
                              {isTarget && <span className="text-[#1677ff] text-[11px] font-medium shrink-0">目标</span>}
                              <span className="text-gray-300 text-[11px] ml-auto shrink-0">{node.rect?.width}×{node.rect?.height}</span>
                            </div>
                          );
                        })}
                        {!desktopPath.length && (
                          <div className="text-[11px] text-gray-400 py-4 text-center">无层级路径数据</div>
                        )}
                      </div>
                    </div>
                  </>
                )}

                {/* Tab（仅网页元素） */}
                {!isDesktop && (
                <div className="flex gap-1 shrink-0 border-b border-gray-200">
                  <button onClick={() => setMode(0)}
                    className={`px-4 py-1.5 text-xs border-b-2 -mb-px ${mode === 0 ? 'text-[#1677ff] border-[#1677ff] font-medium' : 'text-gray-500 border-transparent hover:text-gray-700'}`}>
                    推荐方案
                  </button>
                  <button onClick={() => setMode(1)}
                    className={`px-4 py-1.5 text-xs border-b-2 -mb-px ${mode === 1 ? 'text-[#1677ff] border-[#1677ff] font-medium' : 'text-gray-500 border-transparent hover:text-gray-700'}`}>
                    手动编辑
                  </button>
                </div>
                )}

                {/* 推荐方案（仅网页元素） */}
                {!isDesktop && mode === 0 && (
                  <div className="flex-1 bg-white rounded border border-[#d9d9d9] overflow-hidden flex flex-col min-h-0">
                    <div className="flex-1 overflow-y-auto min-h-0">
                      <table className="w-full text-xs">
                      <thead className="bg-[#fafafa] sticky top-0">
                        <tr>
                          <th className="px-3 py-2 text-left font-medium text-gray-500 cursor-pointer hover:text-[#1677ff]" onClick={() => sortCands('syntax')}>选择器</th>
                          <th className="w-16 px-2 py-2 font-medium text-gray-500 cursor-pointer hover:text-[#1677ff]" onClick={() => sortCands('family')}>类型</th>
                          <th className="w-14 px-2 py-2 font-medium text-gray-500 cursor-pointer hover:text-[#1677ff]" onClick={() => sortCands('match')}>匹配</th>
                        </tr>
                      </thead>
                      <tbody>
                        {cands.map((c) => {
                          const syn = strip(c.syntax);
                          const isSel = !!selector && syn === selector;
                          return (
                            <tr key={syn} onClick={() => setSelector(syn)}
                                className={`cursor-pointer border-t border-gray-100 ${isSel ? 'bg-blue-50' : 'hover:bg-[#fafafa]'}`}>
                              <td className="px-3 py-2 font-mono break-all">{syn}</td>
                              <td className="px-2 py-2">
                                <span className={`px-1.5 py-0.5 rounded text-[11px] ${(c.family||'').toLowerCase()==='css' ? 'bg-orange-50 text-orange-600' : 'bg-green-50 text-green-600'}`}>
                                  {(c.family || '?').toUpperCase()}
                                </span>
                              </td>
                              <td className="px-2 py-2">{c.matchCount || ''}</td>
                            </tr>
                          );
                        })}
                        {!cands.length && <tr><td colSpan={3} className="px-3 py-6 text-center text-gray-400">暂无候选方案</td></tr>}
                      </tbody>
                    </table>
                    </div>
                  </div>
                )}

                {/* 手动编辑（仅网页元素） */}
                {!isDesktop && mode === 1 && (
                  <div className="flex-1 flex gap-3 min-h-0 overflow-hidden">
                    {/* DOM 层级 */}
                    <div className="flex-1 bg-white rounded border border-[#d9d9d9] p-3 overflow-y-auto">
                      <div className="flex items-center gap-2 mb-2">
                        <button onClick={selectAll} className="px-2 py-1 text-xs text-[#1677ff] border border-[#1677ff] rounded hover:bg-blue-50">全选</button>
                        <button onClick={selectNone} className="px-2 py-1 text-xs text-gray-500 border border-[#d9d9d9] rounded hover:bg-[#fafafa]">全不选</button>
                        <span className="text-[11px] text-gray-400">勾选层级参与选择器生成</span>
                      </div>
                      <div className={`${SECTION_LABEL} mb-1`}>页面层级</div>
                      {domPath.map((node, i) => {
                        const isLeaf = i === domPath.length - 1;
                        const n = typeof node === 'object' ? node : { tag: String(node) };
                        const isSel = i === selLevel;
                        return (
                          <div
                            key={i}
                            className={`flex items-center gap-1.5 py-1 px-1 cursor-pointer rounded ${isSel ? 'bg-blue-50 ring-1 ring-blue-200' : 'hover:bg-[#fafafa]'}`}
                            onClick={() => selectDomLevel(i)}
                          >
                            <input type="checkbox" checked={domChecked[i]} onChange={(e) => { e.stopPropagation(); toggleDomCheck(i); }} className="accent-[#1677ff]" />
                            <span className={`font-mono text-xs ${isLeaf ? 'text-[#1677ff] font-semibold' : 'text-gray-700'}`}>
                              &lt;{n.tag || 'div'}&gt;
                            </span>
                            {n.id && <span className="text-green-600 text-xs">#{n.id}</span>}
                            {n.classes?.length > 0 && <span className="text-purple-600 text-xs">.{n.classes.slice(0, 3).join('.')}</span>}
                          </div>
                        );
                      })}
                    </div>

                    {/* 元素属性 */}
                    <div className="w-96 bg-white rounded border border-[#d9d9d9] p-3 overflow-y-auto shrink-0">
                      <div className={`${SECTION_LABEL} mb-2`}>元素属性</div>
                      {selLevel >= 0 && Object.keys(domAttrs || {}).length > 0 ? (
                        <>
                          <div className="text-[11px] text-gray-400 mb-2">id/class 已在左侧层级中展示</div>
                          {Object.entries(domAttrs || {}).filter(([k]) => !['id','class'].includes(k)).map(([k, v]) => {
                            const fragile = domFragile.includes(k);
                            return (
                              <div key={k} className="flex items-center gap-1.5 py-1"
                                title={fragile ? '易变属性：每次渲染可能变化，勾选后选择器可能不稳定' : ''}>
                                <input type="checkbox"
                                  checked={(attrVars[selLevel] || {})[k] || false}
                                  onChange={() => toggleAttr(selLevel, k)}
                                  className="accent-[#1677ff]" />
                                <span className={`font-mono text-[11px] break-all ${fragile ? 'text-gray-400' : 'text-purple-700'}`}>
                                  {fragile ? <i className="fas fa-exclamation-triangle mr-1"></i> : ''}{k}="{v}"
                                </span>
                              </div>
                            );
                          })}
                        </>
                      ) : (
                        <div className="text-[11px] text-gray-400">点击左侧层级查看属性</div>
                      )}
                    </div>
                  </div>
                )}

                {/* 选择器（仅网页元素；桌面元素的"选择器"即上方层级路径） */}
                {!isDesktop && (
                <div className="shrink-0">
                  <label className={`${SECTION_LABEL} block mb-1`}>选择器</label>
                  <div className="flex gap-2 items-start">
                    <textarea
                      value={selector}
                      onChange={(e) => setSelector(e.target.value)}
                      rows={2}
                      className="flex-1 px-2 py-1.5 bg-[#fafafa] border border-[#d9d9d9] rounded text-sm font-mono text-gray-700 focus:outline-none focus:border-[#1677ff] resize-none"
                    />
                    <button onClick={copySel} title="复制选择器"
                      className="px-3 py-2 text-xs text-gray-500 bg-white hover:bg-[#fafafa] rounded border border-[#d9d9d9]">
                      <i className="fas fa-copy"></i>
                    </button>
                  </div>

                  {/* JS 验证代码（默认折叠） */}
                  {selector && (
                    <div className="mt-2">
                      <button onClick={() => setShowJsCode(v => !v)}
                        className="text-[11px] text-gray-400 hover:text-[#1677ff]">
                        <i className={`fas fa-chevron-${showJsCode ? 'down' : 'right'} mr-1`}></i>
                        手动验证 (F12 → Console)
                      </button>
                      {showJsCode && (
                        <div className="mt-1.5 bg-[#fafafa] rounded border border-[#d9d9d9] p-2 font-mono text-[11px] text-gray-700 relative">
                          <button
                            onClick={() => { navigator.clipboard.writeText(jsCode); showToast('JS 已复制'); }}
                            className="absolute top-1.5 right-1.5 text-gray-400 hover:text-[#1677ff] text-[11px] px-1.5 border border-[#d9d9d9] rounded bg-white"
                          >复制</button>
                          <pre className="whitespace-pre-wrap break-all pr-12">{jsCode}</pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
                )}

                {/* 验证结果（常驻，可关闭；网页/桌面共用） */}
                {verifyResult && (
                  <div className={`flex items-center justify-between px-3 py-2 rounded border text-xs shrink-0 ${verifyResult.ok ? 'bg-green-50 border-green-200 text-green-700' : 'bg-red-50 border-red-200 text-red-600'}`}>
                    <span>
                      <i className={`fas ${verifyResult.ok ? 'fa-check-circle' : 'fa-exclamation-circle'} mr-1.5`}></i>
                      {verifyResult.msg}
                    </span>
                    <button onClick={() => setVerifyResult(null)} className="ml-3 opacity-60 hover:opacity-100 shrink-0">
                      <i className="fas fa-times"></i>
                    </button>
                  </div>
                )}

                {/* 操作按钮（右对齐，保存为主操作） */}
                <div className="flex justify-end gap-2 shrink-0">
                  <button onClick={verify} disabled={!cur}
                    className="px-4 py-1.5 text-xs text-[#1677ff] border border-[#1677ff] rounded hover:bg-blue-50 disabled:opacity-40 flex items-center gap-1.5">
                    <i className="fas fa-check-circle"></i>验证
                  </button>
                  <button onClick={save} disabled={!cur}
                    className="px-4 py-1.5 text-xs text-white bg-[#1677ff] rounded hover:bg-[#4096ff] disabled:opacity-40 flex items-center gap-1.5">
                    <i className="fas fa-save"></i>保存
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
      {toast && (
        <div className={`fixed top-4 left-1/2 -translate-x-1/2 text-white px-5 py-2.5 rounded-lg text-sm z-[9999] transition-opacity duration-200 ${toast.type === 'success' ? 'bg-green-500' : toast.type === 'error' ? 'bg-red-500' : 'bg-[#1677ff]'}`}>
          {toast.msg}
        </div>
      )}
      {lightbox && (
        <ImageLightbox src={lightbox.src} alt={lightbox.alt} onClose={() => setLightbox(null)} />
      )}
    </>
  );
}
