import { useState, useEffect } from 'react';
import { useWorkflow } from '../store/WorkflowContext';
import { api } from '../api';

const BOTTOM_TABS = [
  { key: 'elements', label: '元素库', icon: 'fa-crosshairs' },
  { key: 'images', label: '图像库', icon: 'fa-image' },
  { key: 'logs', label: '运行日志', icon: 'fa-terminal' },
  { key: 'params', label: '流程参数', icon: 'fa-sliders-h' },
];

export default function ElementLibraryTab() {
  const { elements, loadElements } = useWorkflow();
  const [hosts, setHosts] = useState([]);
  const [selectedHost, setSelectedHost] = useState('');
  const [activeTab, setActiveTab] = useState('elements');
  const [expanded, setExpanded] = useState(true);
  const [selectedElementId, setSelectedElementId] = useState(null);
  const [extOnline, setExtOnline] = useState(false);
  const [extCount, setExtCount] = useState(0);
  const [extBrowsers, setExtBrowsers] = useState([]);  // [{browser, count}]
  const [targetBrowser, setTargetBrowser] = useState(''); // '' = all, 'chrome', 'edge'
  const [capturing, setCapturing] = useState(false);
  const [toast, setToast] = useState(null);

  const selectedElement = elements.find(e => e.id === selectedElementId) || null;

  // 加载元素库 + 站点列表
  const refresh = async () => {
    await loadElements();
    api.getElementHosts().then(setHosts).catch(() => {});
  };

  useEffect(() => {
    refresh();
  }, []);

  // 轮询扩展在线状态
  useEffect(() => {
    let timer = null;
    const checkStatus = async () => {
      try {
        const data = await api.getExtensionStatus();
        setExtOnline(data.online);
        setExtCount(data.count);
        setExtBrowsers(data.browsers || []);
        // 如果只有一个浏览器在线，自动选它
        if ((data.browsers || []).length === 1 && !targetBrowser) {
          setTargetBrowser(data.browsers[0].browser);
        }
      } catch {
        setExtOnline(false);
        setExtCount(0);
        setExtBrowsers([]);
      }
    };
    checkStatus();
    timer = setInterval(checkStatus, 3000);
    return () => clearInterval(timer);
  }, [targetBrowser]);

  // 捕获完成后自动刷新（轮询检测新元素）
  useEffect(() => {
    if (!capturing) return;
    const beforeCount = elements.length;
    const timer = setInterval(async () => {
      await loadElements();
      if (elements.length > beforeCount) {
        setCapturing(false);
        clearInterval(timer);
      }
    }, 2000);
    // 最长等待 30 秒
    const timeout = setTimeout(() => {
      setCapturing(false);
      clearInterval(timer);
    }, 30000);
    return () => {
      clearInterval(timer);
      clearTimeout(timeout);
    };
  }, [capturing]);

  const filtered = selectedHost
    ? elements.filter(e => e.hostname === selectedHost)
    : elements;

  const showToast = (msg, type = 'info') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleCapture = async () => {
    if (!extOnline) {
      showToast('浏览器扩展未连接，请确认扩展已安装并刷新页面', 'error');
      return;
    }
    setCapturing(true);
    try {
      const res = await api.sendExtensionCommand('enterCaptureMode', {}, targetBrowser || undefined);
      if (res.success) {
        const browserLabel = targetBrowser ? `[${targetBrowser}] ` : '';
        showToast(`${browserLabel}已发送抓取命令，请点击元素捕获`);
      } else {
        showToast('抓取命令发送失败: ' + (res.error || '未知错误'), 'error');
        setCapturing(false);
      }
    } catch (e) {
      showToast('抓取失败: ' + e.message, 'error');
      setCapturing(false);
    }
  };

  if (!expanded) {
    return (
      <div className="h-8 bg-white border-t border-[#e8e8e8] flex items-center px-4 cursor-pointer hover:bg-gray-50"
           onClick={() => setExpanded(true)}>
        <span className="text-xs text-gray-500">
          <i className="fas fa-chevron-up mr-1"></i>
          元素库 ({elements.length})
        </span>
      </div>
    );
  }

  return (
    <div className="h-[220px] bg-white border-t border-[#e8e8e8] flex flex-col shrink-0 select-none">
      {/* Tab 栏 */}
      <div className="flex items-center border-b border-[#e8e8e8] px-2">
        {BOTTOM_TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-3 py-2 text-xs ${activeTab === tab.key ? 'tab-active' : 'text-gray-500 hover:text-gray-700'}`}
          >
            <i className={`fas ${tab.icon} mr-1`}></i>
            {tab.label}
          </button>
        ))}
        <button
          onClick={() => setExpanded(false)}
          className="ml-auto px-2 py-2 text-xs text-gray-400 hover:text-gray-600"
        >
          <i className="fas fa-chevron-down"></i>
        </button>
      </div>

      {/* 内容区 */}
      <div className="flex-1 flex overflow-hidden">
        {activeTab === 'elements' ? (
          <>
            {/* 左侧元素树 */}
            <div className="w-[280px] border-r border-[#e8e8e8] overflow-y-auto p-2">
              <div className="flex items-center gap-2 mb-2">
                <select
                  value={selectedHost}
                  onChange={(e) => setSelectedHost(e.target.value)}
                  className="flex-1 px-2 py-1 bg-[#fafafa] border border-[#d9d9d9] rounded text-xs text-gray-700 outline-none"
                >
                  <option value="">全部站点</option>
                  {hosts.map(h => (
                    <option key={h} value={h}>{h}</option>
                  ))}
                </select>
                <span className="text-xs text-gray-400">{filtered.length}</span>
              </div>
              {filtered.length === 0 ? (
                <div className="text-center text-gray-400 text-xs py-8">暂无元素</div>
              ) : (
                <div className="space-y-0.5">
                  {filtered.map(el => (
                    <div
                      key={el.id}
                      onClick={() => setSelectedElementId(el.id)}
                      className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer ${
                        selectedElementId === el.id
                          ? 'bg-blue-50 border border-blue-200'
                          : 'hover:bg-gray-100 border border-transparent'
                      }`}
                    >
                      <i className={`fas fa-crosshairs text-[10px] w-4 text-center ${
                        selectedElementId === el.id ? 'text-blue-500' : 'text-gray-400'
                      }`}></i>
                      <div className="flex-1 min-w-0">
                        <div className={`text-xs truncate ${
                          selectedElementId === el.id ? 'text-blue-700 font-medium' : 'text-gray-700'
                        }`}>{el.name}</div>
                        <div className="text-[10px] text-gray-400 truncate">{el.locator}</div>
                      </div>
                      <span className="text-[10px] text-gray-400">{el.locator_type}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            {/* 右侧详情区 */}
            <div className="flex-1 overflow-y-auto p-4">
              <div className="flex items-center justify-end mb-4 gap-2">
                {/* 浏览器选择器（多浏览器时显示） */}
                {extBrowsers.length > 1 && (
                  <select
                    value={targetBrowser}
                    onChange={(e) => setTargetBrowser(e.target.value)}
                    className="px-2 py-1 bg-[#fafafa] border border-[#d9d9d9] rounded text-xs text-gray-700 outline-none"
                  >
                    <option value="">所有浏览器</option>
                    {extBrowsers.map(b => (
                      <option key={b.browser} value={b.browser}>
                        {b.browser === 'edge' ? 'Edge' : 'Chrome'} ({b.count})
                      </option>
                    ))}
                  </select>
                )}
                <div className="flex items-center gap-1.5 mr-1">
                  <div
                    className={`w-2 h-2 rounded-full ${extOnline ? 'bg-green-500' : 'bg-gray-300'}`}
                    title={extOnline ? `扩展在线 (${extCount})` : '扩展未连接'}
                  />
                  <span className="text-[10px] text-gray-400">
                    {extOnline ? `在线 (${extCount})` : '未连接'}
                  </span>
                </div>
                <button
                  className={`flex items-center gap-1 px-3 py-1.5 rounded text-xs transition-colors ${
                    extOnline
                      ? 'bg-orange-500 hover:bg-orange-600 text-white'
                      : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                  }`}
                  onClick={handleCapture}
                  disabled={!extOnline || capturing}
                  title={extOnline ? `发送到: ${targetBrowser || '所有浏览器'}` : '扩展未连接'}
                >
                  <i className={`fas ${capturing ? 'fa-spinner fa-spin' : 'fa-plus'} text-[10px]`}></i>
                  <span>{capturing ? '等待捕获...' : '捕获新元素'}</span>
                </button>
              </div>
              {selectedElement ? (
                <div className="max-w-2xl">
                  {/* 标题 */}
                  <div className="flex items-center gap-2 mb-4">
                    <i className="fas fa-crosshairs text-blue-500"></i>
                    <h3 className="text-sm font-medium text-gray-800">{selectedElement.name}</h3>
                    {selectedElement.tag && (
                      <span className="px-1.5 py-0.5 bg-gray-100 rounded text-[10px] text-gray-500">
                        {selectedElement.tag}
                      </span>
                    )}
                  </div>

                  {/* 截图 */}
                  {selectedElement.screenshot && (
                    <div className="mb-4">
                      <div className="text-xs text-gray-500 mb-1">截图</div>
                      <img
                        src={selectedElement.screenshot}
                        alt={selectedElement.name}
                        className="max-h-48 border border-gray-200 rounded cursor-zoom-in hover:border-blue-300"
                        onClick={() => window.open(selectedElement.screenshot, '_blank')}
                      />
                    </div>
                  )}

                  {/* 定位信息 */}
                  <div className="grid grid-cols-3 gap-3 mb-4">
                    <div>
                      <div className="text-[10px] text-gray-400 mb-0.5">定位方式</div>
                      <div className="text-xs text-gray-700 font-mono bg-gray-50 px-2 py-1 rounded">
                        {selectedElement.locator_type}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-gray-400 mb-0.5">方法</div>
                      <div className="text-xs text-gray-700 font-mono bg-gray-50 px-2 py-1 rounded">
                        {selectedElement.method}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-gray-400 mb-0.5">站点</div>
                      <div className="text-xs text-gray-700 truncate bg-gray-50 px-2 py-1 rounded" title={selectedElement.hostname}>
                        {selectedElement.hostname}
                      </div>
                    </div>
                  </div>

                  {/* Locator */}
                  <div className="mb-3">
                    <div className="text-[10px] text-gray-400 mb-0.5">Locator</div>
                    <code className="block text-xs text-gray-700 bg-gray-50 px-2 py-1.5 rounded break-all font-mono">
                      {selectedElement.locator}
                    </code>
                  </div>

                  {/* CSS Selector */}
                  {selectedElement.css_selector && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-0.5">CSS Selector</div>
                      <code className="block text-xs text-gray-700 bg-gray-50 px-2 py-1.5 rounded break-all font-mono">
                        {selectedElement.css_selector}
                      </code>
                    </div>
                  )}

                  {/* 描述 */}
                  {selectedElement.description && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-0.5">描述</div>
                      <div className="text-xs text-gray-600">{selectedElement.description}</div>
                    </div>
                  )}

                  {/* 文本预览 */}
                  {selectedElement.text_preview && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-0.5">文本预览</div>
                      <div className="text-xs text-gray-600 bg-yellow-50 px-2 py-1.5 rounded border border-yellow-100">
                        {selectedElement.text_preview}
                      </div>
                    </div>
                  )}

                  {/* 页面 URL */}
                  {selectedElement.page_url && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-0.5">页面 URL</div>
                      <a
                        href={selectedElement.page_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-600 hover:underline truncate block"
                        title={selectedElement.page_url}
                      >
                        {selectedElement.page_url}
                      </a>
                    </div>
                  )}

                  {/* 候选方案 */}
                  {selectedElement.candidates && selectedElement.candidates.length > 0 && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-1">
                        候选方案 ({selectedElement.candidates.length})
                      </div>
                      <div className="space-y-1">
                        {selectedElement.candidates.map((cand, idx) => (
                          <div key={idx} className="text-xs bg-gray-50 px-2 py-1 rounded">
                            <span className="text-gray-400 mr-1">#{idx + 1}</span>
                            <span className="text-gray-600 font-mono">
                              {typeof cand === 'string' ? cand : JSON.stringify(cand)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 特征 */}
                  {selectedElement.features && Object.keys(selectedElement.features).length > 0 && (
                    <div className="mb-3">
                      <div className="text-[10px] text-gray-400 mb-1">特征</div>
                      <div className="grid grid-cols-2 gap-1">
                        {Object.entries(selectedElement.features).map(([k, v]) => (
                          <div key={k} className="text-xs bg-gray-50 px-2 py-1 rounded flex justify-between">
                            <span className="text-gray-400">{k}</span>
                            <span className="text-gray-600 font-mono truncate ml-2">{String(v)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 时间 */}
                  <div className="flex gap-4 text-[10px] text-gray-400 mt-4 pt-3 border-t border-gray-100">
                    {selectedElement.created_at && (
                      <span>创建: {new Date(selectedElement.created_at).toLocaleString('zh-CN')}</span>
                    )}
                    {selectedElement.updated_at && (
                      <span>更新: {new Date(selectedElement.updated_at).toLocaleString('zh-CN')}</span>
                    )}
                  </div>
                </div>
              ) : (
                <div className="text-center text-gray-400 text-sm mt-12">
                  选择左侧元素查看详情
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center">
            <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mb-3">
              <i className="fas fa-inbox text-gray-400 text-xl"></i>
            </div>
            <p className="text-gray-500 text-sm">{BOTTOM_TABS.find(t => t.key === activeTab)?.label}</p>
            <p className="text-gray-400 text-xs mt-1">暂无内容</p>
          </div>
        )}
      </div>

      {/* Toast 提示 */}
      {toast && (
        <div className={`fixed bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 rounded shadow-lg text-xs z-50 transition-opacity ${
          toast.type === 'error' ? 'bg-red-600 text-white' : 'bg-gray-800 text-white'
        }`}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}
