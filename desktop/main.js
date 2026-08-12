/**
 * RPA 桌面版 - Electron 主进程
 * 1. 等待 Python 后端 (uvicorn, 端口 8000) 就绪
 * 2. 打开主窗口加载 workflow-editor
 *
 * 后端由开发者手动启动, Electron 不再 spawn:
 *   .venv 终端里: python -m src.runtime.main
 */
const { app, BrowserWindow, dialog } = require('electron');
const { execSync } = require('child_process');
const http = require('http');
const path = require('path');

const PORT = 8000;
const APP_URL = `http://127.0.0.1:${PORT}/workflow-editor/`;
const PROJECT_ROOT = path.resolve(__dirname, '..');

let mainWindow = null;

function isPortOpen(port, timeout = 500) {
  return new Promise((resolve) => {
    const req = http.get({ host: '127.0.0.1', port, path: '/', timeout }, (res) => {
      res.destroy();
      resolve(true);
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => { req.destroy(); resolve(false); });
  });
}

function findPortOwner(port) {
  // 返回占用端口的进程 {pid, exe, cmdline}, 查不到返回 null
  try {
    const netstat = execSync('netstat -ano', { encoding: 'utf8', windowsHide: true });
    for (const line of netstat.split('\n')) {
      const m = line.match(new RegExp(`:${port}\\s+\\S+\\s+LISTENING\\s+(\\d+)`, 'i'));
      if (!m) continue;
      const pid = m[1];
      let exe = '';
      let cmdline = '';
      try {
        const wmic = execSync(`wmic process where ProcessId=${pid} get ExecutablePath,CommandLine /format:list`, {
          encoding: 'utf8', windowsHide: true,
        });
        const lines = wmic.split('\n').map((l) => l.trim());
        const exeHit = lines.find((l) => l.startsWith('ExecutablePath='));
        const cmdHit = lines.find((l) => l.startsWith('CommandLine='));
        exe = exeHit ? exeHit.slice('ExecutablePath='.length) : '';
        cmdline = cmdHit ? cmdHit.slice('CommandLine='.length) : '';
      } catch (e) { exe = '(无法读取)'; }
      return { pid, exe, cmdline };
    }
  } catch (e) { /* 忽略 */ }
  return null;
}

async function waitForBackend() {
  const PORT = 8000;
  for (let i = 0; i < 40; i++) {
    if (await isPortOpen(PORT)) {
      const owner = findPortOwner(PORT);
      // venv 重定向后监听进程的 exe 是基解释器(uv), 所以用命令行判断是否本项目后端
      const isOwnBackend = owner && owner.cmdline.includes('src.runtime.main');
      if (owner && !isOwnBackend) {
        console.log(`[desktop] 警告: ${PORT} 被非本项目后端占用 (PID ${owner.pid}): ${owner.exe || owner.cmdline}`);
        console.log(`[desktop] 若非你手动起的后端, 清理后重启: taskkill /F /PID ${owner.pid}`);
      } else {
        console.log('[desktop] 后端已在运行');
      }
      return;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  const owner = findPortOwner(PORT);
  const msg = owner
    ? `Python 后端 20 秒内未就绪。\n\n当前占用 ${PORT} 的进程:\n  PID: ${owner.pid}\n  ${owner.exe || '(路径未知)'}\n\n请在 .venv 终端里手动启动:\n  python -m src.runtime.main`
    : `Python 后端 20 秒内未就绪。\n\n请先在 .venv 终端里手动启动:\n  python -m src.runtime.main`;
  dialog.showErrorBox('后端未就绪', msg);
  app.quit();
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    title: 'RPA 脚本编辑器',
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.loadURL(APP_URL);
  mainWindow.on('closed', () => { mainWindow = null; });
}

app.whenReady().then(async () => {
  await waitForBackend();
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
