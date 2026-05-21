import { useState } from 'react';
import { useWorkflow } from '../store/WorkflowContext';
import { api } from '../api';

function buildDpCall(node) {
  const m = node.method || 'ele';
  const loc = (node.locator || '').replace(/'/g, "\\'");
  return `tab.${m}('${loc}')`;
}

function exportAsNaturalLanguage(nodes, workflow, typeMap) {
  const sorted = [...nodes].sort((a, b) => a.order - b.order);
  if (sorted.length === 0) {
    alert('还没有任何操作步骤');
    return;
  }

  let hostname = '未知页面';
  if (workflow?.url) {
    try { hostname = new URL(workflow.url).hostname; } catch { hostname = workflow.url; }
  }

  let nl = `需求: 自动化操作流程 - ${hostname}\n\n`;
  nl += `页面URL: ${workflow?.url || ''}\n`;
  nl += `使用的框架: DrissionPage (每步骤后括号内为定位语法,请严格照搬不要改写)\n`;
  nl += `约定: tab 是已连接的 ChromiumPage / SessionPage 对象\n\n`;
  nl += `操作步骤:\n`;

  sorted.forEach((node, idx) => {
    const n = idx + 1;
    const typeInfo = typeMap[node.type] || {};
    const desc = node.locator
      ? `「${typeInfo.label || node.type}」(${node.locator})`
      : `「${typeInfo.label || node.type}」`;
    const call = node.locator ? buildDpCall(node) : '';
    const extra = node.extra && typeof node.extra === 'object' ? node.extra : {};

    switch (node.type) {
      case 'custom':
        nl += `${n}. ${extra.description || '自定义操作'} [元素: ${desc}]${call ? ' -> ' + call : ''}\n`;
        break;
      case 'click':
        nl += `${n}. 点击 ${desc}${call ? ' -> ' + call + '.click()' : ''}\n`;
        break;
      case 'getText':
        nl += `${n}. 获取 ${desc} 的文本${call ? ' -> ' + call + '.text' : ''}\n`;
        break;
      case 'input':
      case 'inputAndPressEnter': {
        const txt = (extra.text || '').replace(/'/g, "\\'");
        nl += `${n}. 在 ${desc} 中输入: "${extra.text || ''}"${call ? ' -> ' + call + ".input('" + txt + "')" : ''}\n`;
        break;
      }
      case 'getAttr':
        nl += `${n}. 获取 ${desc} 的 ${extra.attrName || ''} 属性${call ? ' -> ' + call + ".attr('" + (extra.attrName || '') + "')" : ''}\n`;
        break;
      case 'hover':
        nl += `${n}. 鼠标悬停 ${desc}${call ? ' -> ' + call + '.hover()' : ''}\n`;
        break;
      case 'findWithin': {
        const sub = (extra.subSelector || '').replace(/'/g, "\\'");
        nl += `${n}. 在 ${desc} 内查找子元素${call ? ' -> ' + call + ".ele('" + sub + "')" : ''}\n`;
        break;
      }
      case 'waitForElement': {
        const loc = (node.locator || '').replace(/'/g, "\\'");
        nl += `${n}. 等待 ${desc} 出现(最长 ${extra.seconds || 10} 秒) -> tab.wait.ele_displayed('${loc}', timeout=${extra.seconds || 10})\n`;
        break;
      }
      case 'navigate':
        nl += `${n}. 打开网页: ${extra.url || ''} -> tab.get('${extra.url || ''}')\n`;
        break;
      case 'sleep':
        nl += `${n}. 等待 ${extra.seconds || 1} 秒 -> time.sleep(${extra.seconds || 1})\n`;
        break;
      case 'pressKey':
        nl += `${n}. 按键: ${extra.key || 'Enter'}\n`;
        break;
      case 'scrollToBottom':
        nl += `${n}. 滚动到底部\n`;
        break;
      case 'scrollToTop':
        nl += `${n}. 滚动到顶部\n`;
        break;
      case 'scrollBy':
        nl += `${n}. 滚动 (${extra.x || 0}, ${extra.y || 500})\n`;
        break;
      case 'newTab':
        nl += `${n}. 新建标签页: ${extra.url || ''}\n`;
        break;
      case 'closeTab':
        nl += `${n}. 关闭当前标签页\n`;
        break;
      case 'goBack':
        nl += `${n}. 返回上一页\n`;
        break;
      case 'goForward':
        nl += `${n}. 前进\n`;
        break;
      case 'refresh':
        nl += `${n}. 刷新页面${extra.hardReload ? ' (强制)' : ''}\n`;
        break;
      case 'getCurrentUrl':
        nl += `${n}. 获取当前页面URL -> ${extra.varName || 'currentUrl'} = tab.url\n`;
        break;
      case 'getPageTitle':
        nl += `${n}. 获取页面标题 -> ${extra.varName || 'pageTitle'} = tab.title\n`;
        break;
      case 'getHtml':
        nl += `${n}. 获取元素HTML${call ? ' -> ' + call + '.html' : ''}\n`;
        break;
      case 'getValue':
        nl += `${n}. 获取元素值${call ? ' -> ' + call + '.value' : ''}\n`;
        break;
      case 'clearInput':
        nl += `${n}. 清空输入框${call ? ' -> ' + call + '.clear()' : ''}\n`;
        break;
      case 'selectOption':
        nl += `${n}. 选择下拉选项: ${extra.value || ''}${call ? ' -> ' + call + ".select('" + (extra.value || '') + "')" : ''}\n`;
        break;
      case 'takeScreenshot':
        nl += `${n}. 截图保存到: ${extra.savePath || ''}\n`;
        break;
      case 'executeJs':
        nl += `${n}. 执行JavaScript: ${(extra.script || '').slice(0, 60)}...\n`;
        break;
      case 'ifElementExists':
        nl += `${n}. 条件判断: 如果元素存在 ${desc}\n`;
        break;
      case 'ifElementNotExists':
        nl += `${n}. 条件判断: 如果元素不存在 ${desc}\n`;
        break;
      case 'else':
        nl += `${n}. 否则\n`;
        break;
      case 'endIf':
        nl += `${n}. 结束条件判断\n`;
        break;
      case 'forEachElement':
        nl += `${n}. 循环遍历: ${desc}\n`;
        break;
      case 'forRange':
        nl += `${n}. 循环范围: ${extra.start || 0} 到 ${extra.end || 10}\n`;
        break;
      case 'endFor':
        nl += `${n}. 结束循环\n`;
        break;
      case 'break':
        nl += `${n}. 跳出循环\n`;
        break;
      case 'continue':
        nl += `${n}. 继续下一次循环\n`;
        break;
      case 'setVar':
        nl += `${n}. 设置变量: ${extra.name || 'x'} = ${extra.value || ''}\n`;
        break;
      case 'log':
        nl += `${n}. 日志输出 [${extra.level || 'info'}]: ${extra.message || ''}\n`;
        break;
      case 'pushItem':
        nl += `${n}. 推送结果项\n`;
        break;
      case 'return':
        nl += `${n}. 结束并返回结果\n`;
        break;
      default:
        nl += `${n}. ${typeInfo.label || node.type} ${desc}${call ? ' -> ' + call : ''}\n`;
    }
  });

  nl += `\n请根据以上步骤生成完整的 DrissionPage Python 脚本:\n`;
  nl += `1. 用 ChromiumOptions 显式设置浏览器路径和用户数据目录后启动 ChromiumPage:\n`;
  nl += `\n`;
  nl += "```python\n";
  nl += `from DrissionPage import ChromiumPage, ChromiumOptions\n`;
  nl += `\n`;
  nl += `chrome_path = r'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'\n`;
  nl += `user_data_path = r'D:\\Chrome_Work'\n`;
  nl += `\n`;
  nl += `co = ChromiumOptions()\n`;
  nl += `co.set_browser_path(chrome_path)\n`;
  nl += `co.set_user_data_path(user_data_path)\n`;
  nl += `co.set_argument('--no-sandbox')\n`;
  nl += `co.set_argument('--disable-blink-features=AutomationControlled')\n`;
  nl += `tab = ChromiumPage(addr_or_opts=co)\n`;
  if (workflow?.url) {
    nl += `tab.get('${workflow.url}')\n`;
  }
  nl += "```\n";
  nl += `\n`;
  nl += `2. 严格按上述定位语法,不要自行改写为 CSS 或 xpath\n`;
  nl += `3. 加随机延迟(random.uniform(0.5, 1.5))模拟人类操作\n`;
  nl += `4. 加 try/except 错误处理,关键步骤打印日志\n`;
  nl += `5. eles/s_eles 返回列表时遍历处理\n`;
  nl += `6. 不要写 tab.quit(),让 Chrome 保持运行以便用户继续观察\n`;
  return nl;
}

export default function Toolbar() {
  const { workflow, saving, wfId, isDirty, commit, nodes, NODE_TYPE_MAP } = useWorkflow();
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState(null);

  const handleExport = async () => {
    console.log(`[Toolbar] exportPython wfId=${wfId}`);
    try {
      const data = await api.exportPython(wfId);
      console.log(`[Toolbar] exportPython success, ${data.python?.length || 0} chars`);
      if (data.python) {
        await navigator.clipboard.writeText(data.python);
        alert('Python 脚本已复制到剪贴板');
      }
    } catch (e) {
      console.error(`[Toolbar] exportPython failed: ${e.message}`);
      alert('导出失败: ' + e.message);
    }
  };

  const handleExportNL = async () => {
    console.log(`[Toolbar] exportNL wfId=${wfId}`);
    try {
      const nl = exportAsNaturalLanguage(nodes, workflow, NODE_TYPE_MAP);
      if (!nl) return;
      await navigator.clipboard.writeText(nl);
      console.log(`[Toolbar] exportNL success, ${nl.length} chars`);
      alert('自然语言描述已复制到剪贴板');
    } catch (e) {
      console.error(`[Toolbar] exportNL failed: ${e.message}`);
      alert('导出失败: ' + e.message);
    }
  };

  const handleSave = async () => {
    try {
      await commit();
    } catch (e) {
      alert('保存失败: ' + e.message);
    }
  };

  const handleRun = async () => {
    console.log(`[Toolbar] run clicked, isDirty=${isDirty}`);
    if (isDirty) {
      const ok = confirm('工作流有未保存的更改，先保存再运行？');
      if (!ok) return;
      try {
        await commit();
      } catch (e) {
        alert('保存失败，无法运行: ' + e.message);
        return;
      }
    }

    setRunning(true);
    setRunResult(null);
    console.log(`[Toolbar] calling runWorkflow wfId=${wfId}`);
    try {
      const data = await api.runWorkflow(wfId);
      console.log(`[Toolbar] runWorkflow result success=${data.success} returncode=${data.returncode}`);
      setRunResult(data);
    } catch (e) {
      console.error(`[Toolbar] runWorkflow failed: ${e.message}`);
      setRunResult({ success: false, stderr: e.message, stdout: '', returncode: -1 });
    } finally {
      setRunning(false);
    }
  };

  const closeResult = () => setRunResult(null);

  return (
    <>
      <header className="h-11 bg-white border-b border-[#e8e8e8] flex items-center justify-between px-3 select-none shrink-0">
        {/* 左侧：标题 */}
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex items-center gap-1.5">
            <div className="w-6 h-6 bg-[#1677ff] rounded flex items-center justify-center text-white text-xs font-bold">
              <i className="fas fa-project-diagram text-[10px]"></i>
            </div>
            <span className="text-sm font-medium text-gray-700 truncate max-w-[200px]">
              {workflow?.name || '加载中...'}
            </span>
          </div>
          {saving && <span className="text-xs text-gray-400">保存中...</span>}
          {isDirty && !saving && <span className="text-xs text-orange-500">● 未保存</span>}
        </div>

        {/* 中间：工具按钮 */}
        <div className="flex items-center gap-1">
          <button
            className={`h-7 px-3 flex items-center gap-1.5 rounded text-xs transition-colors ${
              isDirty
                ? 'bg-[#1677ff] hover:bg-[#4096ff] text-white'
                : 'bg-gray-100 text-gray-400 cursor-not-allowed'
            }`}
            onClick={handleSave}
            disabled={!isDirty || saving}
            title="保存到服务器"
          >
            <i className="fas fa-save text-[10px]"></i>
            <span>保存</span>
          </button>
          <div className="w-px h-5 bg-gray-200 mx-1"></div>
          <button
            className="h-7 px-3 flex items-center gap-1.5 rounded border border-[#d9d9d9] hover:border-[#1677ff] hover:text-[#1677ff] text-xs text-gray-600 transition-colors"
            onClick={handleExport}
          >
            <i className="fas fa-code text-[10px]"></i>
            <span>导出 Python</span>
          </button>
          <button
            className="h-7 px-3 flex items-center gap-1.5 rounded border border-[#d9d9d9] hover:border-[#6a4a8a] hover:text-[#6a4a8a] text-xs text-gray-600 transition-colors"
            onClick={handleExportNL}
          >
            <i className="fas fa-file-alt text-[10px]"></i>
            <span>导出自然语言</span>
          </button>
          <div className="w-px h-5 bg-gray-200 mx-1"></div>
          <button
            className={`h-7 px-3 flex items-center gap-1.5 rounded bg-[#1f1f1f] hover:bg-black text-white text-xs transition-colors ${running ? '' : 'run-pulse'}`}
            onClick={handleRun}
            disabled={running}
          >
            <i className={`fas ${running ? 'fa-spinner fa-spin' : 'fa-play'} text-[10px]`}></i>
            <span>{running ? '运行中...' : '运行'}</span>
          </button>
          <a
            href="/admin/workflows"
            className="h-7 px-2.5 flex items-center gap-1.5 rounded border border-[#d9d9d9] hover:border-[#1677ff] hover:text-[#1677ff] text-xs text-gray-600 transition-colors"
          >
            <i className="fas fa-arrow-left text-[10px]"></i>
            <span>返回</span>
          </a>
        </div>

        {/* 右侧：用户信息 */}
        <div className="flex items-center gap-3">
          {typeof window !== 'undefined' && window.__USER__ ? (
            <>
              <div className="flex items-center gap-1.5 text-xs text-gray-500">
                <i className="fas fa-user-circle text-gray-400"></i>
                <span className="font-medium">{window.__USER__.username}</span>
              </div>
              <a
                href="/admin/logout"
                className="text-xs text-gray-400 hover:text-red-500 transition-colors"
                title="退出登录"
              >
                <i className="fas fa-sign-out-alt"></i>
              </a>
            </>
          ) : (
            <span className="text-xs text-gray-400">workflow-editor</span>
          )}
        </div>
      </header>

      {/* 运行结果弹窗 */}
      {runResult && (
        <RunResultModal result={runResult} onClose={closeResult} />
      )}
    </>
  );
}

function RunResultModal({ result, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
        {/* 头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <i className={`fas ${result.success ? 'fa-check-circle text-green-500' : 'fa-times-circle text-red-500'}`}></i>
            <span className="text-sm font-medium">
              {result.success ? '运行成功' : '运行失败'}
            </span>
            <span className="text-xs text-gray-400">exit code: {result.returncode}</span>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded hover:bg-gray-100 text-gray-400"
          >
            <i className="fas fa-times text-xs"></i>
          </button>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {result.stdout && (
            <div>
              <div className="text-xs text-gray-500 mb-1 font-medium">标准输出</div>
              <pre className="bg-gray-50 rounded p-3 text-xs text-gray-700 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto">
                {result.stdout}
              </pre>
            </div>
          )}
          {result.stderr && (
            <div>
              <div className="text-xs text-red-500 mb-1 font-medium">错误输出</div>
              <pre className="bg-red-50 rounded p-3 text-xs text-red-700 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto">
                {result.stderr}
              </pre>
            </div>
          )}
          {!result.stdout && !result.stderr && (
            <div className="text-sm text-gray-400 text-center py-8">无输出</div>
          )}
        </div>

        {/* 底部 */}
        <div className="px-4 py-3 border-t border-gray-200 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-[#1677ff] hover:bg-[#4096ff] text-white text-xs rounded transition-colors"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
