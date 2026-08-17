import { useEffect, useState, Fragment } from 'react';
import { api } from '../api';

const HANDLER_DESC = {
  launchBrowser:'启动浏览器并加载扩展',wait:'等待指定秒数',randomWait:'随机等待',setVar:'设置变量值',
  appendToList:'追加到列表',stringConcat:'字符串拼接',increment:'数值递增/递减',
  setDictValue:'设置字典键值',getDictValue:'读取字典键值',removeDictKey:'删除字典键',
  log:'打印日志',custom:'执行自定义Python代码',httpRequest:'发送HTTP请求',executeJs:'执行JavaScript',
  readTableCell:'读取表格单元格',writeTableCell:'写入表格单元格',writeTableRow:'追加表格行',
  getTableRowCount:'获取表格行数',navigate:'页面导航跳转',newTab:'新建标签页',
  closeBrowser:'关闭浏览器窗口',getCurrentUrl:'获取当前页面URL',
  elementAction:'通用元素操作',pressKey:'发送键盘按键',
};

const FIELD_TYPES = [
  {v:'string',l:'str · 文本'},{v:'text',l:'str · 多行'},{v:'str-var',l:'str · 变量引用'},
  {v:'any-input',l:'any · 自动推断'},
  {v:'select',l:'str · 下拉'},{v:'element',l:'str · 元素'},
  {v:'number',l:'int · 数字'},{v:'boolean',l:'bool · 开关'},
  {v:'code',l:'any · 代码/表达式'},
];

const FIELD_GROUPS = [
  {v:'主属性',l:'⭐ 主属性'},{v:'advanced',l:'🔧 高级'},
  {v:'output',l:'📤 输出'},{v:'input',l:'📥 输入'},{v:'anchor',l:'⚓ 锚点'},
];

function controlLabel(cmd) {
  if (cmd.isStructural) return {text:'结束',color:'text-warn',bg:'bg-warn/30',desc:'闭合标记，不参与执行，仅标记范围结束'};
  if (cmd.isBranch) return {text:'分支',color:'text-purple-400',bg:'bg-purple-900/40',desc:'容器内部的分支路径'};
  if (cmd.isContainer) return {text:'开始',color:'text-ok',bg:'bg-green-900/40',desc:`开启一个子指令块${cmd.closesWith?` → ${cmd.closesWith}结束`:''}`};
  // emitter 指令但没有身份标记（如 break、continue）— 控制流跳转
  if (!cmd.hasRuntime) return {text:'跳转',color:'text-orange-400',bg:'bg-orange-900/40',desc:'控制流跳转，不经过 handler'};
  return null;
}

export default function CommandsPage() {
  const [commands, setCommands] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [editCmd, setEditCmd] = useState(null);
  const [editSaving, setEditSaving] = useState(false);
  const [showTypeHelp, setShowTypeHelp] = useState(false);
  const [viewSource, setViewSource] = useState(null); // {type, source, loading}

  useEffect(() => { loadCommands(); }, []);

  async function loadCommands() {
    setLoading(true);
    try { const data = await api.getCommands(); setCommands(data); setError(null); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }

  async function handleToggleEnabled(cmd) {
    try { await api.request(`/api/commands/${cmd.id}`,{method:'PUT',body:JSON.stringify({enabled:cmd.enabled===false})}); loadCommands(); }
    catch(e){alert('更新失败: '+e.message);}
  }

  async function handleSaveEdit() {
    setEditSaving(true);
    try {
      await api.request(`/api/commands/${editCmd.id}`,{method:'PUT',body:JSON.stringify({
        label:editCmd.label,category:editCmd.category,description:editCmd.description,
        enabled:editCmd.enabled,isContainer:editCmd.isContainer,isBranch:editCmd.isBranch,
        isStructural:editCmd.isStructural,closesWith:editCmd.closesWith,
        handler:editCmd.handler,local:editCmd.local,fields:editCmd.fields,
      })});
      setEditCmd(null);loadCommands();
    }catch(e){alert('保存失败: '+e.message);}
    finally{setEditSaving(false);}
  }

  async function handleViewSource(cmd) {
    setViewSource({ type: cmd.cmd, source: null, loading: true });
    try {
      const data = await api.request(`/api/commands/${cmd.id}/source`);
      setViewSource({ type: data.type, source: data.source, loading: false });
    } catch (e) {
      setViewSource({ type: cmd.cmd, source: null, loading: false, error: e.message });
    }
  }

  const allCommands=commands?.commands||{};
  const categories=commands?.categories||[];
  const containerTypes=commands?.containerTypes||[];
  const filtered=search.trim()
    ?categories.map(cat=>{const cmds=(allCommands[cat]||[]).filter(c=>c.type?.toLowerCase().includes(search.toLowerCase())||c.label?.includes(search)||(c.description||'').includes(search));return cmds.length>0?{cat,cmds}:null;}).filter(Boolean)
    :categories.map(cat=>({cat,cmds:allCommands[cat]||[]}));

  if(loading)return(<div className="flex items-center justify-center py-20"><i className="fas fa-circle-notch fa-spin text-accent text-2xl"></i><span className="ml-3 text-faint">加载中...</span></div>);

  return(<div className="p-6">
    <div className="mb-6 flex items-center justify-between">
      <div><h1 className="text-xl font-semibold text-white">指令管理</h1><p className="text-muted text-sm mt-1">共 {categories.length} 个分类，{Object.values(allCommands).reduce((s,a)=>s+a.length,0)} 个指令，{containerTypes.length} 种容器</p></div>
      <div className="flex items-center gap-2">
        <input type="text" value={search} onChange={e=>setSearch(e.target.value)} placeholder="搜索类型/标签/说明..." className="px-3 py-1.5 bg-surface-2 border border-border-strong rounded text-sm text-white placeholder-gray-500 outline-none focus:border-blue-500 w-56"/>
        <button onClick={loadCommands} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded text-sm flex items-center gap-2 transition-colors"><i className="fas fa-sync-alt"></i>刷新</button>
      </div>
    </div>
    {error&&<div className="mb-4 p-3 bg-danger/25 border border-danger rounded-lg text-danger text-sm"><i className="fas fa-exclamation-circle mr-2"></i>{error}</div>}
    {filtered.length===0?(<div className="text-center py-12 text-muted">无匹配指令</div>):(<div className="space-y-3">
      {filtered.map(({cat,cmds})=>(<div key={cat} className="bg-surface-2 rounded-xl border border-gray-700 overflow-hidden">
        <div className="px-4 py-2.5 bg-[#252f47] border-b border-gray-700 flex items-center gap-3"><span className="text-sm font-medium text-muted">{cat}</span><span className="text-xs text-muted">{cmds.length} 个</span></div>
        <div className="overflow-x-auto"><table className="w-full text-xs table-fixed">
          <colgroup><col style={{width:'120px'}}/><col style={{width:'100px'}}/><col style={{width:'56px'}}/><col style={{width:'80px'}}/><col style={{width:'100px'}}/><col style={{width:'60px'}}/><col style={{width:'150px'}}/><col/></colgroup>
          <thead><tr className="border-b border-gray-700/50"><th className="text-left px-3 py-2 font-medium text-muted">类型</th><th className="text-left px-3 py-2 font-medium text-muted">标签</th><th className="text-center px-3 py-2 font-medium text-muted">状态</th><th className="text-center px-3 py-2 font-medium text-muted">类别</th><th className="text-center px-3 py-2 font-medium text-muted">控制身份</th><th className="text-center px-3 py-2 font-medium text-muted">参数</th><th className="text-left px-3 py-2 font-medium text-muted">运行时</th><th className="text-left px-3 py-2 font-medium text-muted">说明</th></tr></thead>
          <tbody>{cmds.map(cmd=>{
            const ctrl=controlLabel(cmd);
            const isControl=!!ctrl;
            return(<tr key={cmd.cmd} className="border-b border-gray-700/30 hover:bg-[#252f47] cursor-pointer" onClick={()=>setEditCmd({...type,fields:JSON.parse(JSON.stringify(cmd.fields||[]))})}>
            <td className="px-3 py-2 font-mono text-accent-strong truncate">{cmd.cmd}</td>
            <td className="px-3 py-2 text-muted truncate">{cmd.label||'-'}</td>
            <td className="px-3 py-2 text-center">{cmd.enabled!==false?<span className="px-1.5 py-0.5 bg-green-900/40 text-ok rounded text-[10px]">启用</span>:<span className="px-1.5 py-0.5 bg-gray-700/50 text-faint rounded text-[10px]">禁用</span>}</td>
            <td className="px-3 py-2 text-center">{isControl?<span className="px-1.5 py-0.5 bg-warn/30 text-warn rounded text-[10px]">控制</span>:<span className="px-1.5 py-0.5 bg-accent/25 text-accent-strong rounded text-[10px]">操作</span>}</td>
            <td className="px-3 py-2 text-center">{ctrl?<span className={`px-1.5 py-0.5 ${ctrl.bg} ${ctrl.color} rounded text-[10px]`}>{ctrl.text}</span>:'—'}</td>
            <td className="px-3 py-2 text-center">{(cmd.fields||[]).length===0?<span className="text-muted">—</span>:<span className="text-accent">{(cmd.fields||[]).length}</span>}</td>
            <td className="px-3 py-2">{isControl?<span className="px-1 py-0.5 bg-warn/30 text-warn rounded text-[10px]">emitter</span>:cmd.hasRuntime?<div className="flex items-center gap-1.5"><span className="text-muted font-mono text-[10px] truncate">{cmd.handler||'—'}</span><span className={`shrink-0 px-1 rounded text-[10px] whitespace-nowrap ${cmd.local?'bg-purple-900/40 text-purple-300':'bg-accent/25 text-accent-strong'}`}>{cmd.local?'后端':'扩展'}</span></div>:<span className="text-muted">—</span>}</td>
            <td className="px-3 py-2 text-faint truncate">{(cmd.description||'')}</td>
          </tr>);})}</tbody>
        </table></div>
      </div>))}
    </div>)}

    {/* Edit Modal */}
    {editCmd&&(()=>{const ctrl=controlLabel(editCmd);const isControl=!!ctrl;return(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={()=>setEditCmd(null)}>
      <div className="bg-surface-2 rounded-xl border border-gray-700 w-[740px] max-w-[95vw] max-h-[90vh] flex flex-col" onClick={e=>e.stopPropagation()}>
        <div className="px-5 py-3 border-b border-gray-700 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <h3 className="text-base font-semibold text-white font-mono">{editCmd.cmd}</h3>
            <span className="text-xs text-faint">{editCmd.label}</span>
            <span className={`px-1.5 py-0.5 rounded text-[10px] ${isControl?'bg-warn/30 text-warn':'bg-accent/25 text-accent-strong'}`}>{isControl?'控制指令':'操作指令'}</span>
          </div>
          <button onClick={()=>setEditCmd(null)} className="text-faint hover:text-white"><i className="fas fa-times"></i></button>
        </div>

        <div className="flex-1 overflow-auto p-5 space-y-4">

          {/* ═══ 操作指令（handler） ═══ */}
          {!isControl&&(<>
            {/* ① 执行位置 */}
            <div className="border border-gray-700/50 rounded-lg p-4 bg-bg/50">
              <div className="flex items-center gap-2 mb-3">
                <span className="w-5 h-5 rounded-full bg-accent text-white text-[10px] font-bold flex items-center justify-center shrink-0">①</span>
                <span className="text-xs font-medium text-muted">执行位置</span>
                <span className="text-[10px] text-muted">— 决定指令在何处执行</span>
              </div>
              <div className="px-3 py-2 bg-bg border border-gray-700 rounded text-xs">
                {editCmd.local?<span className="text-purple-300"><i className="fas fa-server mr-1.5"></i>后端本地 (Python)</span>:<span className="text-accent-strong"><i className="fas fa-globe mr-1.5"></i>浏览器扩展 (content.js)</span>}
              </div>
            </div>

            {/* ② Handler */}
            <div className="border border-gray-700/50 rounded-lg p-4 bg-bg/50">
              <div className="flex items-center gap-2 mb-3">
                <span className="w-5 h-5 rounded-full bg-accent text-white text-[10px] font-bold flex items-center justify-center shrink-0">②</span>
                <span className="text-xs font-medium text-muted">Handler</span>
                <span className="text-[10px] text-muted">— 执行该指令的函数，1:1 对应</span>
                {editCmd.handler && (
                  <button onClick={() => handleViewSource(editCmd)} className="ml-auto text-[10px] text-accent hover:text-accent">
                    <i className="fas fa-code mr-1"></i>查看源码
                  </button>
                )}
              </div>
              <div className="px-3 py-2 bg-bg border border-gray-700 rounded text-xs font-mono text-muted">
                {editCmd.handler||<span className="text-muted italic">无（可能未注册或缺失运行时）</span>}
                {editCmd.handler&&!HANDLER_DESC[editCmd.handler]&&<span className="text-warn ml-2 text-[10px] font-normal">⚠ 未在已知列表</span>}
                {HANDLER_DESC[editCmd.handler]&&<span className="text-muted ml-2 font-normal">— {HANDLER_DESC[editCmd.handler]}</span>}
              </div>
            </div>

            {/* Handler source code */}
            {viewSource && (
              <div className="border border-gray-700/50 rounded-lg overflow-hidden">
                <div className="flex items-center justify-between px-3 py-2 bg-bg/80 border-b border-gray-700/50">
                  <span className="text-[10px] text-faint font-mono">{viewSource.cmd} source</span>
                  <button onClick={() => setViewSource(null)} className="text-faint hover:text-white"><i className="fas fa-times"></i></button>
                </div>
                {viewSource.loading ? (
                  <div className="px-4 py-8 text-center text-muted text-xs"><i className="fas fa-circle-notch fa-spin mr-2"></i>加载中...</div>
                ) : viewSource.error ? (
                  <div className="px-4 py-4 text-danger text-xs">{viewSource.error}</div>
                ) : viewSource.source ? (
                  <pre className="p-4 text-[11px] font-mono text-muted bg-[#0a0e14] overflow-auto max-h-64 leading-relaxed">{viewSource.source}</pre>
                ) : (
                  <div className="px-4 py-4 text-muted text-xs">无法获取源码（可能是 emitter 或旧指令）</div>
                )}
              </div>
            )}
          </>)}

          {/* ═══ 控制指令（emitter） ═══ */}
          {isControl&&(
            <div className="border border-gray-700/50 rounded-lg p-4 bg-bg/50">
              <div className="flex items-center gap-2 mb-3">
                <span className="w-5 h-5 rounded-full bg-ok text-white text-[10px] font-bold flex items-center justify-center shrink-0">①</span>
                <span className="text-xs font-medium text-muted">控制身份</span>
                <span className={`px-1.5 py-0.5 rounded text-[10px] ${ctrl.bg} ${ctrl.color}`}>{ctrl.text}</span>
                <span className="text-[10px] text-muted">— {ctrl.desc}</span>
              </div>
            </div>
          )}

          {/* ③/① 参数字段 */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className={`w-5 h-5 rounded-full ${isControl?'bg-ok':'bg-accent'} text-white text-[10px] font-bold flex items-center justify-center shrink-0`}>{isControl?'②':'③'}</span>
                <span className="text-xs font-medium text-muted">参数字段</span>
                <span className="text-[10px] text-muted">— 变量名由 {isControl?'emitter':'handler'} 定义，不可改</span>
              </div>
              {!editCmd.isBuiltin && <button onClick={()=>setEditCmd({...editCmd,fields:[...editCmd.fields,{name:'',label:'',type:'text',group:'主属性'}]})} className="text-[10px] text-accent hover:text-accent shrink-0">+ 添加字段</button>}
            </div>
            <p className="text-[10px] text-warn/70 mb-2">⚠ 变量名与{isControl?'emitter 代码':<>handler 中 <code className="text-warn bg-warn/25 px-1 rounded">extra.get("变量名")</code></>}绑定，必须一致</p>
            <div className="flex items-center gap-1.5 px-2 py-1 text-[10px] text-muted bg-bg/50 rounded-t"><span className="w-[74px] shrink-0">变量名</span><span className="w-[64px] shrink-0">显示名</span><span className="w-[74px] shrink-0">类型 <button type="button" onClick={e=>{e.stopPropagation();setShowTypeHelp(!showTypeHelp);}} className="inline text-muted hover:text-muted ml-0.5" title="字段类型说明">?</button></span><span className="w-[58px] shrink-0">分组</span><span className="w-[28px] shrink-0 text-center">必填</span><span className="flex-1">默认值</span></div>
            <div className="space-y-1 max-h-48 overflow-y-auto">{editCmd.fields.map((f,i)=>(<Fragment key={i}>
              <div className="flex items-center gap-1.5 bg-bg rounded px-2 py-1">
              <div className="w-[74px] flex items-center gap-0.5"><span className="text-[10px] text-muted shrink-0">🔒</span><input value={f.name||''} disabled className="flex-1 px-1.5 py-1 bg-gray-800/50 border border-gray-700 rounded text-faint text-[10px] font-mono" placeholder="url"/></div>
              <input value={f.label||''} onChange={e=>{const fs=[...editCmd.fields];fs[i]={...fs[i],label:e.target.value};setEditCmd({...editCmd,fields:fs});}} placeholder="显示名" className="w-[65px] px-1.5 py-1 bg-transparent border border-border-strong rounded text-white text-[10px] outline-none focus:border-blue-500"/>
              <div className="w-[74px] px-1 py-1 bg-gray-800/50 border border-gray-700 rounded text-faint text-[10px] flex items-center gap-0.5"><span className="text-[10px] text-muted">🔒</span><span className="truncate">{(FIELD_TYPES.find(t=>t.v===f.type)||{}).l||f.type||'text'}</span></div>
              <select value={f.group||'主属性'} onChange={e=>{const fs=[...editCmd.fields];fs[i]={...fs[i],group:e.target.value};setEditCmd({...editCmd,fields:fs});}} className="w-[58px] px-1 py-1 bg-surface-2 border border-gray-500 rounded text-white text-[10px] outline-none focus:border-blue-500">{FIELD_GROUPS.map(g=><option key={g.v} value={g.v}>{g.l}</option>)}</select>
              <label className="flex justify-center w-[28px] shrink-0"><input type="checkbox" checked={!!f.required} onChange={e=>{const fs=[...editCmd.fields];fs[i]={...fs[i],required:e.target.checked};setEditCmd({...editCmd,fields:fs});}} className="accent-accent"/></label>
              {f.default!==undefined&&f.default!==null?<input value={String(f.default)} onChange={e=>{const fs=[...editCmd.fields];fs[i]={...fs[i],default:e.target.value};setEditCmd({...editCmd,fields:fs});}} placeholder="默认值" className="flex-1 px-1.5 py-1 bg-transparent border border-border-strong rounded text-white text-[10px] outline-none focus:border-blue-500"/>
              :<button onClick={()=>{const fs=[...editCmd.fields];fs[i]={...fs[i],default:''};setEditCmd({...editCmd,fields:fs});}} className="text-[10px] text-muted hover:text-muted flex-1">+默认</button>}
              <button onClick={()=>{const fs=editCmd.fields.filter((_,j)=>j!==i);setEditCmd({...editCmd,fields:fs});}} className="text-danger hover:text-danger text-[10px] shrink-0"><i className="fas fa-trash-alt"></i></button>
            </div>
            {f.type==='select'&&f.options&&f.options.length>0&&(
              <div className="flex items-center gap-1.5 px-2 py-0.5 text-[10px] text-muted">
                <span className="w-[74px] shrink-0"></span>
                <span className="text-muted">🔒 选项:</span>
                <span className="text-faint">{f.options.map(o=>typeof o==='object'?o.label:o).join(', ')}</span>
              </div>
            )}
            </Fragment>))}</div>

            {/* Type help popover */}
            {showTypeHelp && (
              <div className="relative">
                <div className="absolute z-30 top-0 left-[170px] w-[380px] bg-[#1a2236] border border-border-strong rounded-lg shadow-2xl p-4 text-xs">
                  <div className="flex items-center justify-between mb-3">
                    <span className="font-medium text-body">字段类型说明</span>
                    <button onClick={() => setShowTypeHelp(false)} className="text-faint hover:text-white"><i className="fas fa-times"></i></button>
                  </div>
                  <table className="w-full text-[10px]">
                    <thead>
                      <tr className="text-faint border-b border-gray-700">
                        <th className="text-left py-1.5 pr-2">类型</th>
                        <th className="text-left py-1.5 pr-2">含义</th>
                        <th className="text-left py-1.5 pr-2">变量替换</th>
                        <th className="text-left py-1.5">示例</th>
                      </tr>
                    </thead>
                    <tbody className="text-muted">
                      <tr className="border-b border-gray-700/50"><td className="py-1 pr-2 text-accent-strong">文本</td><td className="py-1 pr-2">任意字符串</td><td className="py-1 pr-2 text-ok">{'{{var}}→文本'}</td><td className="py-1 font-mono">https://...</td></tr>
                      <tr className="border-b border-gray-700/50"><td className="py-1 pr-2 text-accent-strong">数字</td><td className="py-1 pr-2">数值</td><td className="py-1 pr-2 text-muted">—</td><td className="py-1 font-mono">30</td></tr>
                      <tr className="border-b border-gray-700/50"><td className="py-1 pr-2 text-accent-strong">开关</td><td className="py-1 pr-2">布尔</td><td className="py-1 pr-2 text-muted">—</td><td className="py-1 font-mono">true</td></tr>
                      <tr className="border-b border-gray-700/50"><td className="py-1 pr-2 text-accent-strong">下拉</td><td className="py-1 pr-2">枚举选一</td><td className="py-1 pr-2 text-muted">—</td><td className="py-1 font-mono">chrome</td></tr>
                      <tr className="border-b border-gray-700/50"><td className="py-1 pr-2 text-accent-strong">变量</td><td className="py-1 pr-2">变量名引用</td><td className="py-1 pr-2 text-amber-400">原类型传递</td><td className="py-1 font-mono">browser1 → {'{windowId,tabId}'}</td></tr>
                      <tr className="border-b border-gray-700/50"><td className="py-1 pr-2 text-accent-strong">元素</td><td className="py-1 pr-2">元素库选择</td><td className="py-1 pr-2 text-muted">—</td><td className="py-1 font-mono">login_btn</td></tr>
                      <tr className="border-b border-gray-700/50"><td className="py-1 pr-2 text-accent-strong">多行</td><td className="py-1 pr-2">多行文本</td><td className="py-1 pr-2 text-ok">{'{{var}}→文本'}</td><td className="py-1">长文本内容</td></tr>
                      <tr><td className="py-1 pr-2 text-accent-strong">代码</td><td className="py-1 pr-2">Python/JS</td><td className="py-1 pr-2 text-muted">—</td><td className="py-1 font-mono">print('hi')</td></tr>
                    </tbody>
                  </table>
                  <div className="mt-2 text-muted text-[10px]">
                    <span className="text-ok">变量替换</span> = 文本/多行会把 <code className="text-warn bg-warn/25 px-1 rounded">{'{{name}}'}</code> 替换为变量值并转字符串；
                    <span className="text-amber-400 ml-1">原类型传递</span> = 变量类型保留原始类型（字典/列表等）
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* ④/③ 基本信息 */}
          <div>
            <div className="flex items-center gap-2 mb-3"><span className={`w-5 h-5 rounded-full ${isControl?'bg-ok':'bg-accent'} text-white text-[10px] font-bold flex items-center justify-center shrink-0`}>{isControl?'③':'④'}</span><span className="text-xs font-medium text-muted">基本信息</span><span className="text-[10px] text-muted">— 可修改</span></div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="block text-[10px] text-muted mb-1">类型标识（唯一ID，不可改）</label><input value={editCmd.cmd} disabled className="w-full px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-faint text-xs font-mono"/></div>
              <div><label className="block text-[10px] text-muted mb-1">中文显示名</label><input value={editCmd.label||''} onChange={e=>setEditCmd({...editCmd,label:e.target.value})} className="w-full px-2 py-1.5 bg-bg border border-border-strong rounded text-white text-xs outline-none focus:border-blue-500"/></div>
              <div><label className="block text-[10px] text-muted mb-1">分类</label><select value={editCmd.category||''} onChange={e=>setEditCmd({...editCmd,category:e.target.value})} className="w-full px-2 py-1.5 bg-bg border border-border-strong rounded text-white text-xs outline-none focus:border-blue-500">{categories.map(c=><option key={c} value={c}>{c}</option>)}</select></div>
              <div><label className="block text-[10px] text-muted mb-1">说明（悬停提示）</label><textarea value={editCmd.description||''} onChange={e=>setEditCmd({...editCmd,description:e.target.value})} rows={2} className="w-full px-2 py-1.5 bg-bg border border-border-strong rounded text-white text-xs outline-none focus:border-blue-500 resize-none" placeholder="描述该指令的功能和使用场景"/></div>
            </div>
          </div>
        </div>

        <div className="px-5 py-3 border-t border-gray-700 flex justify-between shrink-0">
          <div>
            {editCmd.isBuiltin ? (
              <span className="px-2 py-1 text-xs text-muted"><i className="fas fa-lock mr-1"></i>内建指令，不可禁用</span>
            ) : (
              <button onClick={()=>handleToggleEnabled(editCmd)} className={`px-3 py-1.5 text-xs rounded ${editCmd.enabled!==false?'bg-red-900/40 hover:bg-red-900/60 text-danger':'bg-green-900/40 hover:bg-green-900/60 text-ok'}`}>{editCmd.enabled!==false?'禁用':'启用'}</button>
            )}
          </div>
          <div className="flex gap-2"><button onClick={()=>setEditCmd(null)} className="px-4 py-1.5 text-xs text-faint hover:text-white">取消</button><button onClick={handleSaveEdit} disabled={editSaving} className="px-4 py-1.5 text-xs text-white bg-accent rounded hover:bg-accent-strong disabled:opacity-50">{editSaving?'保存中...':'保存'}</button></div>
        </div>
      </div>
    </div>
    );})()}
  </div>);
}
