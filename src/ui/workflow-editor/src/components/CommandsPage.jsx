import { useEffect, useState, Fragment } from 'react';
import { api } from '../api';

const HANDLER_DESC = {
  openBrowser:'启动浏览器并加载扩展',wait:'等待指定秒数',randomWait:'随机等待',setVar:'设置变量值',
  appendToList:'追加到列表',stringConcat:'字符串拼接',increment:'数值递增/递减',
  setDictValue:'设置字典键值',getDictValue:'读取字典键值',removeDictKey:'删除字典键',
  log:'打印日志',custom:'执行自定义Python代码',httpRequest:'发送HTTP请求',executeJs:'执行JavaScript',
  readTableCell:'读取表格单元格',writeTableCell:'写入表格单元格',writeTableRow:'追加表格行',
  getTableRowCount:'获取表格行数',navigate:'页面导航跳转',newTab:'新建标签页',
  closeBrowser:'关闭浏览器窗口',getCurrentUrl:'获取当前页面URL',
  elementAction:'通用元素操作',pressKey:'发送键盘按键',
};

const FIELD_TYPES = [
  {v:'text',l:'文本'},{v:'number',l:'数字'},{v:'bool',l:'开关'},
  {v:'select',l:'下拉'},{v:'varName',l:'变量'},{v:'elementName',l:'元素'},
  {v:'textarea',l:'多行'},{v:'code',l:'代码'},
];

const FIELD_GROUPS = [
  {v:'主属性',l:'⭐ 主属性'},{v:'advanced',l:'🔧 高级'},
  {v:'output',l:'📤 输出'},{v:'input',l:'📥 输入'},{v:'anchor',l:'⚓ 锚点'},
];

function controlLabel(cmd) {
  if (cmd.isStructural) return {text:'结束',color:'text-yellow-400',bg:'bg-yellow-900/40',desc:'闭合标记，不参与执行，仅标记范围结束'};
  if (cmd.isBranch) return {text:'分支',color:'text-purple-400',bg:'bg-purple-900/40',desc:'容器内部的分支路径'};
  if (cmd.isContainer) return {text:'开始',color:'text-green-400',bg:'bg-green-900/40',desc:`开启一个子指令块${cmd.closesWith?` → ${cmd.closesWith}结束`:''}`};
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
    setViewSource({ type: cmd.type, source: null, loading: true });
    try {
      const data = await api.request(`/api/commands/${cmd.id}/source`);
      setViewSource({ type: data.type, source: data.source, loading: false });
    } catch (e) {
      setViewSource({ type: cmd.type, source: null, loading: false, error: e.message });
    }
  }

  const allCommands=commands?.commands||{};
  const categories=commands?.categories||[];
  const containerTypes=commands?.containerTypes||[];
  const filtered=search.trim()
    ?categories.map(cat=>{const cmds=(allCommands[cat]||[]).filter(c=>c.type?.toLowerCase().includes(search.toLowerCase())||c.label?.includes(search)||(c.description||'').includes(search));return cmds.length>0?{cat,cmds}:null;}).filter(Boolean)
    :categories.map(cat=>({cat,cmds:allCommands[cat]||[]}));

  if(loading)return(<div className="flex items-center justify-center py-20"><i className="fas fa-circle-notch fa-spin text-blue-400 text-2xl"></i><span className="ml-3 text-gray-400">加载中...</span></div>);

  return(<div className="p-6">
    <div className="mb-6 flex items-center justify-between">
      <div><h1 className="text-xl font-semibold text-white">指令管理</h1><p className="text-gray-500 text-sm mt-1">共 {categories.length} 个分类，{Object.values(allCommands).reduce((s,a)=>s+a.length,0)} 个指令，{containerTypes.length} 种容器</p></div>
      <div className="flex items-center gap-2">
        <input type="text" value={search} onChange={e=>setSearch(e.target.value)} placeholder="搜索类型/标签/说明..." className="px-3 py-1.5 bg-[#1e293b] border border-gray-600 rounded text-sm text-white placeholder-gray-500 outline-none focus:border-blue-500 w-56"/>
        <button onClick={loadCommands} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded text-sm flex items-center gap-2 transition-colors"><i className="fas fa-sync-alt"></i>刷新</button>
      </div>
    </div>
    {error&&<div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm"><i className="fas fa-exclamation-circle mr-2"></i>{error}</div>}
    {filtered.length===0?(<div className="text-center py-12 text-gray-500">无匹配指令</div>):(<div className="space-y-3">
      {filtered.map(({cat,cmds})=>(<div key={cat} className="bg-[#1e293b] rounded-xl border border-gray-700 overflow-hidden">
        <div className="px-4 py-2.5 bg-[#252f47] border-b border-gray-700 flex items-center gap-3"><span className="text-sm font-medium text-gray-300">{cat}</span><span className="text-xs text-gray-500">{cmds.length} 个</span></div>
        <div className="overflow-x-auto"><table className="w-full text-xs table-fixed">
          <colgroup><col style={{width:'120px'}}/><col style={{width:'100px'}}/><col style={{width:'56px'}}/><col style={{width:'80px'}}/><col style={{width:'100px'}}/><col style={{width:'60px'}}/><col style={{width:'150px'}}/><col/></colgroup>
          <thead><tr className="border-b border-gray-700/50"><th className="text-left px-3 py-2 font-medium text-gray-500">类型</th><th className="text-left px-3 py-2 font-medium text-gray-500">标签</th><th className="text-center px-3 py-2 font-medium text-gray-500">状态</th><th className="text-center px-3 py-2 font-medium text-gray-500">类别</th><th className="text-center px-3 py-2 font-medium text-gray-500">控制身份</th><th className="text-center px-3 py-2 font-medium text-gray-500">参数</th><th className="text-left px-3 py-2 font-medium text-gray-500">运行时</th><th className="text-left px-3 py-2 font-medium text-gray-500">说明</th></tr></thead>
          <tbody>{cmds.map(cmd=>{
            const ctrl=controlLabel(cmd);
            const isEmitter=!!ctrl;
            return(<tr key={cmd.type} className="border-b border-gray-700/30 hover:bg-[#252f47] cursor-pointer" onClick={()=>setEditCmd({...cmd,fields:JSON.parse(JSON.stringify(cmd.fields||[]))})}>
            <td className="px-3 py-2 font-mono text-blue-300 truncate">{cmd.type}</td>
            <td className="px-3 py-2 text-gray-300 truncate">{cmd.label||'-'}</td>
            <td className="px-3 py-2 text-center">{cmd.enabled!==false?<span className="px-1.5 py-0.5 bg-green-900/40 text-green-300 rounded text-[10px]">启用</span>:<span className="px-1.5 py-0.5 bg-gray-700/50 text-gray-400 rounded text-[10px]">禁用</span>}</td>
            <td className="px-3 py-2 text-center">{isEmitter?<span className="px-1.5 py-0.5 bg-yellow-900/40 text-yellow-300 rounded text-[10px]">控制</span>:<span className="px-1.5 py-0.5 bg-blue-900/40 text-blue-300 rounded text-[10px]">操作</span>}</td>
            <td className="px-3 py-2 text-center">{ctrl?<span className={`px-1.5 py-0.5 ${ctrl.bg} ${ctrl.color} rounded text-[10px]`}>{ctrl.text}</span>:'—'}</td>
            <td className="px-3 py-2 text-center">{(cmd.fields||[]).length===0?<span className="text-gray-500">—</span>:<span className="text-[#1677ff]">{(cmd.fields||[]).length}</span>}</td>
            <td className="px-3 py-2">{isEmitter?<span className="px-1 py-0.5 bg-yellow-900/40 text-yellow-300 rounded text-[10px]">emitter</span>:cmd.hasRuntime?<div className="flex items-center gap-1.5"><span className="text-gray-300 font-mono text-[10px] truncate">{cmd.handler||'—'}</span><span className={`shrink-0 px-1 rounded text-[10px] whitespace-nowrap ${cmd.local?'bg-purple-900/40 text-purple-300':'bg-blue-900/40 text-blue-300'}`}>{cmd.local?'后端':'扩展'}</span></div>:<span className="text-gray-500">—</span>}</td>
            <td className="px-3 py-2 text-gray-400 truncate">{(cmd.description||'')}</td>
          </tr>);})}</tbody>
        </table></div>
      </div>))}
    </div>)}

    {/* Edit Modal */}
    {editCmd&&(()=>{const ctrl=controlLabel(editCmd);const isEmitter=!!ctrl;return(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={()=>setEditCmd(null)}>
      <div className="bg-[#1e293b] rounded-xl border border-gray-700 w-[740px] max-w-[95vw] max-h-[90vh] flex flex-col" onClick={e=>e.stopPropagation()}>
        <div className="px-5 py-3 border-b border-gray-700 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <h3 className="text-base font-semibold text-white font-mono">{editCmd.type}</h3>
            <span className="text-xs text-gray-400">{editCmd.label}</span>
            <span className={`px-1.5 py-0.5 rounded text-[10px] ${isEmitter?'bg-yellow-900/40 text-yellow-300':'bg-blue-900/40 text-blue-300'}`}>{isEmitter?'控制指令':'操作指令'}</span>
          </div>
          <button onClick={()=>setEditCmd(null)} className="text-gray-400 hover:text-white"><i className="fas fa-times"></i></button>
        </div>

        <div className="flex-1 overflow-auto p-5 space-y-4">

          {/* ═══ 操作指令（handler） ═══ */}
          {!isEmitter&&(<>
            {/* ① 执行位置 */}
            <div className="border border-gray-700/50 rounded-lg p-4 bg-[#0f172a]/50">
              <div className="flex items-center gap-2 mb-3">
                <span className="w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">①</span>
                <span className="text-xs font-medium text-gray-300">执行位置</span>
                <span className="text-[10px] text-gray-500">— 决定指令在何处执行</span>
              </div>
              <div className="px-3 py-2 bg-[#0f172a] border border-gray-700 rounded text-xs">
                {editCmd.local?<span className="text-purple-300"><i className="fas fa-server mr-1.5"></i>后端本地 (Python)</span>:<span className="text-blue-300"><i className="fas fa-globe mr-1.5"></i>浏览器扩展 (content.js)</span>}
              </div>
            </div>

            {/* ② Handler */}
            <div className="border border-gray-700/50 rounded-lg p-4 bg-[#0f172a]/50">
              <div className="flex items-center gap-2 mb-3">
                <span className="w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">②</span>
                <span className="text-xs font-medium text-gray-300">Handler</span>
                <span className="text-[10px] text-gray-500">— 执行该指令的函数，1:1 对应</span>
                {editCmd.handler && (
                  <button onClick={() => handleViewSource(editCmd)} className="ml-auto text-[10px] text-[#1677ff] hover:text-blue-400">
                    <i className="fas fa-code mr-1"></i>查看源码
                  </button>
                )}
              </div>
              <div className="px-3 py-2 bg-[#0f172a] border border-gray-700 rounded text-xs font-mono text-gray-300">
                {editCmd.handler||<span className="text-gray-500 italic">无（可能未注册或缺失运行时）</span>}
                {editCmd.handler&&!HANDLER_DESC[editCmd.handler]&&<span className="text-yellow-400 ml-2 text-[10px] font-normal">⚠ 未在已知列表</span>}
                {HANDLER_DESC[editCmd.handler]&&<span className="text-gray-500 ml-2 font-normal">— {HANDLER_DESC[editCmd.handler]}</span>}
              </div>
            </div>

            {/* Handler source code */}
            {viewSource && (
              <div className="border border-gray-700/50 rounded-lg overflow-hidden">
                <div className="flex items-center justify-between px-3 py-2 bg-[#0f172a]/80 border-b border-gray-700/50">
                  <span className="text-[10px] text-gray-400 font-mono">{viewSource.type} source</span>
                  <button onClick={() => setViewSource(null)} className="text-gray-400 hover:text-white"><i className="fas fa-times"></i></button>
                </div>
                {viewSource.loading ? (
                  <div className="px-4 py-8 text-center text-gray-500 text-xs"><i className="fas fa-circle-notch fa-spin mr-2"></i>加载中...</div>
                ) : viewSource.error ? (
                  <div className="px-4 py-4 text-red-400 text-xs">{viewSource.error}</div>
                ) : viewSource.source ? (
                  <pre className="p-4 text-[11px] font-mono text-gray-300 bg-[#0a0e14] overflow-auto max-h-64 leading-relaxed">{viewSource.source}</pre>
                ) : (
                  <div className="px-4 py-4 text-gray-500 text-xs">无法获取源码（可能是 emitter 或旧指令）</div>
                )}
              </div>
            )}
          </>)}

          {/* ═══ 控制指令（emitter） ═══ */}
          {isEmitter&&(
            <div className="border border-gray-700/50 rounded-lg p-4 bg-[#0f172a]/50">
              <div className="flex items-center gap-2 mb-3">
                <span className="w-5 h-5 rounded-full bg-green-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">①</span>
                <span className="text-xs font-medium text-gray-300">控制身份</span>
                <span className={`px-1.5 py-0.5 rounded text-[10px] ${ctrl.bg} ${ctrl.color}`}>{ctrl.text}</span>
                <span className="text-[10px] text-gray-500">— {ctrl.desc}</span>
              </div>
            </div>
          )}

          {/* ③/① 参数字段 */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className={`w-5 h-5 rounded-full ${isEmitter?'bg-green-600':'bg-blue-600'} text-white text-[10px] font-bold flex items-center justify-center shrink-0`}>{isEmitter?'②':'③'}</span>
                <span className="text-xs font-medium text-gray-300">参数字段</span>
                <span className="text-[10px] text-gray-500">— 变量名由 {isEmitter?'emitter':'handler'} 定义，不可改</span>
              </div>
              {!editCmd.isBuiltin && <button onClick={()=>setEditCmd({...editCmd,fields:[...editCmd.fields,{name:'',label:'',type:'text',group:'主属性'}]})} className="text-[10px] text-[#1677ff] hover:text-blue-400 shrink-0">+ 添加字段</button>}
            </div>
            <p className="text-[10px] text-yellow-400/70 mb-2">⚠ 变量名与{isEmitter?'emitter 代码':<>handler 中 <code className="text-yellow-300 bg-yellow-900/30 px-1 rounded">extra.get("变量名")</code></>}绑定，必须一致</p>
            <div className="flex items-center gap-1.5 px-2 py-1 text-[10px] text-gray-500 bg-[#0f172a]/50 rounded-t"><span className="w-[74px] shrink-0">变量名</span><span className="w-[64px] shrink-0">显示名</span><span className="w-[74px] shrink-0">类型 <button type="button" onClick={e=>{e.stopPropagation();setShowTypeHelp(!showTypeHelp);}} className="inline text-gray-500 hover:text-gray-300 ml-0.5" title="字段类型说明">?</button></span><span className="w-[58px] shrink-0">分组</span><span className="w-[28px] shrink-0 text-center">必填</span><span className="flex-1">默认值</span></div>
            <div className="space-y-1 max-h-48 overflow-y-auto">{editCmd.fields.map((f,i)=>(<Fragment key={i}>
              <div className="flex items-center gap-1.5 bg-[#0f172a] rounded px-2 py-1">
              <div className="w-[74px] flex items-center gap-0.5"><span className="text-[10px] text-gray-600 shrink-0">🔒</span><input value={f.name||''} disabled className="flex-1 px-1.5 py-1 bg-gray-800/50 border border-gray-700 rounded text-gray-400 text-[10px] font-mono" placeholder="url"/></div>
              <input value={f.label||''} onChange={e=>{const fs=[...editCmd.fields];fs[i]={...fs[i],label:e.target.value};setEditCmd({...editCmd,fields:fs});}} placeholder="显示名" className="w-[65px] px-1.5 py-1 bg-transparent border border-gray-600 rounded text-white text-[10px] outline-none focus:border-blue-500"/>
              <div className="w-[74px] px-1 py-1 bg-gray-800/50 border border-gray-700 rounded text-gray-400 text-[10px] flex items-center gap-0.5"><span className="text-[10px] text-gray-600">🔒</span><span className="truncate">{(FIELD_TYPES.find(t=>t.v===f.type)||{}).l||f.type||'text'}</span></div>
              <select value={f.group||'主属性'} onChange={e=>{const fs=[...editCmd.fields];fs[i]={...fs[i],group:e.target.value};setEditCmd({...editCmd,fields:fs});}} className="w-[58px] px-1 py-1 bg-[#1e293b] border border-gray-500 rounded text-white text-[10px] outline-none focus:border-blue-500">{FIELD_GROUPS.map(g=><option key={g.v} value={g.v}>{g.l}</option>)}</select>
              <label className="flex justify-center w-[28px] shrink-0"><input type="checkbox" checked={!!f.required} onChange={e=>{const fs=[...editCmd.fields];fs[i]={...fs[i],required:e.target.checked};setEditCmd({...editCmd,fields:fs});}} className="accent-[#1677ff]"/></label>
              {f.default!==undefined&&f.default!==null?<input value={String(f.default)} onChange={e=>{const fs=[...editCmd.fields];fs[i]={...fs[i],default:e.target.value};setEditCmd({...editCmd,fields:fs});}} placeholder="默认值" className="flex-1 px-1.5 py-1 bg-transparent border border-gray-600 rounded text-white text-[10px] outline-none focus:border-blue-500"/>
              :<button onClick={()=>{const fs=[...editCmd.fields];fs[i]={...fs[i],default:''};setEditCmd({...editCmd,fields:fs});}} className="text-[10px] text-gray-500 hover:text-gray-300 flex-1">+默认</button>}
              <button onClick={()=>{const fs=editCmd.fields.filter((_,j)=>j!==i);setEditCmd({...editCmd,fields:fs});}} className="text-red-400 hover:text-red-300 text-[10px] shrink-0"><i className="fas fa-trash-alt"></i></button>
            </div>
            {f.type==='select'&&f.options&&f.options.length>0&&(
              <div className="flex items-center gap-1.5 px-2 py-0.5 text-[10px] text-gray-500">
                <span className="w-[74px] shrink-0"></span>
                <span className="text-gray-600">🔒 选项:</span>
                <span className="text-gray-400">{f.options.map(o=>typeof o==='object'?o.label:o).join(', ')}</span>
              </div>
            )}
            </Fragment>))}</div>

            {/* Type help popover */}
            {showTypeHelp && (
              <div className="relative">
                <div className="absolute z-30 top-0 left-[170px] w-[380px] bg-[#1a2236] border border-gray-600 rounded-lg shadow-2xl p-4 text-xs">
                  <div className="flex items-center justify-between mb-3">
                    <span className="font-medium text-gray-200">字段类型说明</span>
                    <button onClick={() => setShowTypeHelp(false)} className="text-gray-400 hover:text-white"><i className="fas fa-times"></i></button>
                  </div>
                  <table className="w-full text-[10px]">
                    <thead>
                      <tr className="text-gray-400 border-b border-gray-700">
                        <th className="text-left py-1.5 pr-2">类型</th>
                        <th className="text-left py-1.5 pr-2">含义</th>
                        <th className="text-left py-1.5 pr-2">变量替换</th>
                        <th className="text-left py-1.5">示例</th>
                      </tr>
                    </thead>
                    <tbody className="text-gray-300">
                      <tr className="border-b border-gray-700/50"><td className="py-1 pr-2 text-blue-300">文本</td><td className="py-1 pr-2">任意字符串</td><td className="py-1 pr-2 text-green-400">{'${var}→文本'}</td><td className="py-1 font-mono">https://...</td></tr>
                      <tr className="border-b border-gray-700/50"><td className="py-1 pr-2 text-blue-300">数字</td><td className="py-1 pr-2">数值</td><td className="py-1 pr-2 text-gray-500">—</td><td className="py-1 font-mono">30</td></tr>
                      <tr className="border-b border-gray-700/50"><td className="py-1 pr-2 text-blue-300">开关</td><td className="py-1 pr-2">布尔</td><td className="py-1 pr-2 text-gray-500">—</td><td className="py-1 font-mono">true</td></tr>
                      <tr className="border-b border-gray-700/50"><td className="py-1 pr-2 text-blue-300">下拉</td><td className="py-1 pr-2">枚举选一</td><td className="py-1 pr-2 text-gray-500">—</td><td className="py-1 font-mono">chrome</td></tr>
                      <tr className="border-b border-gray-700/50"><td className="py-1 pr-2 text-blue-300">变量</td><td className="py-1 pr-2">变量名引用</td><td className="py-1 pr-2 text-amber-400">原类型传递</td><td className="py-1 font-mono">browser1 → {'{windowId,tabId}'}</td></tr>
                      <tr className="border-b border-gray-700/50"><td className="py-1 pr-2 text-blue-300">元素</td><td className="py-1 pr-2">元素库选择</td><td className="py-1 pr-2 text-gray-500">—</td><td className="py-1 font-mono">login_btn</td></tr>
                      <tr className="border-b border-gray-700/50"><td className="py-1 pr-2 text-blue-300">多行</td><td className="py-1 pr-2">多行文本</td><td className="py-1 pr-2 text-green-400">{'${var}→文本'}</td><td className="py-1">长文本内容</td></tr>
                      <tr><td className="py-1 pr-2 text-blue-300">代码</td><td className="py-1 pr-2">Python/JS</td><td className="py-1 pr-2 text-gray-500">—</td><td className="py-1 font-mono">print('hi')</td></tr>
                    </tbody>
                  </table>
                  <div className="mt-2 text-gray-500 text-[10px]">
                    <span className="text-green-400">变量替换</span> = 文本/多行会把 <code className="text-yellow-300 bg-yellow-900/30 px-1 rounded">{'${name}'}</code> 替换为变量值并转字符串；
                    <span className="text-amber-400 ml-1">原类型传递</span> = 变量类型保留原始类型（字典/列表等）
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* ④/③ 基本信息 */}
          <div>
            <div className="flex items-center gap-2 mb-3"><span className={`w-5 h-5 rounded-full ${isEmitter?'bg-green-600':'bg-blue-600'} text-white text-[10px] font-bold flex items-center justify-center shrink-0`}>{isEmitter?'③':'④'}</span><span className="text-xs font-medium text-gray-300">基本信息</span><span className="text-[10px] text-gray-500">— 可修改</span></div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="block text-[10px] text-gray-500 mb-1">类型标识（唯一ID，不可改）</label><input value={editCmd.type} disabled className="w-full px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-gray-400 text-xs font-mono"/></div>
              <div><label className="block text-[10px] text-gray-500 mb-1">中文显示名</label><input value={editCmd.label||''} onChange={e=>setEditCmd({...editCmd,label:e.target.value})} className="w-full px-2 py-1.5 bg-[#0f172a] border border-gray-600 rounded text-white text-xs outline-none focus:border-blue-500"/></div>
              <div><label className="block text-[10px] text-gray-500 mb-1">分类</label><select value={editCmd.category||''} onChange={e=>setEditCmd({...editCmd,category:e.target.value})} className="w-full px-2 py-1.5 bg-[#0f172a] border border-gray-600 rounded text-white text-xs outline-none focus:border-blue-500">{categories.map(c=><option key={c} value={c}>{c}</option>)}</select></div>
              <div><label className="block text-[10px] text-gray-500 mb-1">说明（悬停提示）</label><textarea value={editCmd.description||''} onChange={e=>setEditCmd({...editCmd,description:e.target.value})} rows={2} className="w-full px-2 py-1.5 bg-[#0f172a] border border-gray-600 rounded text-white text-xs outline-none focus:border-blue-500 resize-none" placeholder="描述该指令的功能和使用场景"/></div>
            </div>
          </div>
        </div>

        <div className="px-5 py-3 border-t border-gray-700 flex justify-between shrink-0">
          <div>
            {editCmd.isBuiltin ? (
              <span className="px-2 py-1 text-xs text-gray-500"><i className="fas fa-lock mr-1"></i>内建指令，不可禁用</span>
            ) : (
              <button onClick={()=>handleToggleEnabled(editCmd)} className={`px-3 py-1.5 text-xs rounded ${editCmd.enabled!==false?'bg-red-900/40 hover:bg-red-900/60 text-red-300':'bg-green-900/40 hover:bg-green-900/60 text-green-300'}`}>{editCmd.enabled!==false?'禁用':'启用'}</button>
            )}
          </div>
          <div className="flex gap-2"><button onClick={()=>setEditCmd(null)} className="px-4 py-1.5 text-xs text-gray-400 hover:text-white">取消</button><button onClick={handleSaveEdit} disabled={editSaving} className="px-4 py-1.5 text-xs text-white bg-[#1677ff] rounded hover:bg-[#4096ff] disabled:opacity-50">{editSaving?'保存中...':'保存'}</button></div>
        </div>
      </div>
    </div>
    );})()}
  </div>);
}
