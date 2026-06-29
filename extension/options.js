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
  $('port').value = cfg.backendPort || '8811';
}

async function save() {
  const host = $('host').value.trim() || 'localhost';
  const port = parseInt($('port').value, 10);
  if (!port || port < 1 || port > 65535) {
    showStatus('端口无效，请输入 1-65535 之间的数字', false);
    return;
  }
  await chrome.storage.local.set({ backendHost: host, backendPort: port });
  showStatus('已保存，请刷新插件或等待自动重连', true);
}

async function reset() {
  await chrome.storage.local.remove(['backendHost', 'backendPort']);
  $('host').value = 'localhost';
  $('port').value = '8811';
  showStatus('已恢复默认', true);
}

async function reconnect() {
  const host = $('host').value.trim() || 'localhost';
  const port = parseInt($('port').value, 10);
  if (!port || port < 1 || port > 65535) {
    showStatus('端口无效，无法重连', false);
    return;
  }
  showStatus('正在连接...', true);
  try {
    const res = await chrome.runtime.sendMessage({
      action: 'reconnect',
      host,
      port,
    });
    if (res?.connected) {
      showStatus('连接成功', true);
    } else {
      showStatus('连接失败: ' + (res?.error || '未知错误'), false);
    }
  } catch (e) {
    showStatus('连接失败: ' + e.message, false);
  }
}

$('btnSave').addEventListener('click', save);
$('btnReset').addEventListener('click', reset);
$('btnDev').addEventListener('click', () => {
  $('host').value = 'localhost';
  $('port').value = '8000';
  save();
});
$('btnPkg').addEventListener('click', () => {
  $('host').value = 'localhost';
  $('port').value = '8811';
  save();
});
$('btnReconnect').addEventListener('click', reconnect);

load();
