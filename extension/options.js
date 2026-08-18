/* eslint-env browser */

const $ = (id) => document.getElementById(id);
const statusEl = $('status');

function showStatus(text, ok) {
  statusEl.textContent = text;
  statusEl.className = ok ? 'ok' : 'err';
  if (ok) {
    setTimeout(() => { statusEl.textContent = ''; statusEl.className = ''; }, 2000);
  }
}

async function load() {
  const cfg = await chrome.storage.local.get(['backendHost', 'backendPort']);
  $('host').value = cfg.backendHost || 'localhost';
  $('port').value = cfg.backendPort || '';
  $('port').placeholder = '自动发现（8100-8199）';
}

async function save() {
  const host = $('host').value.trim() || 'localhost';
  const raw = $('port').value.trim();
  if (raw) {
    const port = parseInt(raw, 10);
    if (!port || port < 1 || port > 65535) {
      showStatus('端口无效，请输入 1-65535 之间的数字（留空=自动发现）', false);
      return;
    }
    await chrome.storage.local.set({ backendHost: host, backendPort: port });
  } else {
    await chrome.storage.local.set({ backendHost: host });
    await chrome.storage.local.remove('backendPort');
  }
  showStatus('已保存，正在自动重连...', true);
  setTimeout(() => reconnect(), 300);
}

async function reset() {
  await chrome.storage.local.remove(['backendHost', 'backendPort']);
  $('host').value = 'localhost';
  $('port').value = '';
  $('port').placeholder = '自动发现（8100-8199）';
  showStatus('已恢复默认，正在自动重连...', true);
  setTimeout(() => reconnect(), 300);
}

async function reconnect() {
  const host = $('host').value.trim() || 'localhost';
  const raw = $('port').value.trim();
  showStatus('正在连接...', true);
  try {
    // 端口留空 → 自动发现（后台探测 8100-8199）
    const res = await chrome.runtime.sendMessage({
      action: 'reconnect',
      host,
      port: raw ? parseInt(raw, 10) : 0,
    });
    if (res?.connected) {
      showStatus('连接成功', true);
    } else {
      showStatus('连接失败: ' + (res?.error || '未发现后端，请确认后端已启动'), false);
    }
  } catch (e) {
    showStatus('连接失败: ' + e.message, false);
  }
}

$('btnSave').addEventListener('click', save);
$('btnReset').addEventListener('click', reset);
// 开发环境（旧固定 8000）→ 自动发现；打包应用（8811）→ 固定端口
$('btnDev').addEventListener('click', () => {
  $('host').value = 'localhost';
  $('port').value = '';
  save();
});
$('btnPkg').addEventListener('click', () => {
  $('host').value = 'localhost';
  $('port').value = '8811';
  save();
});
$('btnReconnect').addEventListener('click', reconnect);

load();
