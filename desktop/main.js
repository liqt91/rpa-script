/**
 * RPA 桌面版 - Electron 主进程
 * 1. 启动 Python 后端 (uvicorn, 端口 8000)
 * 2. 等待端口就绪
 * 3. 打开主窗口加载 workflow-editor
 */
const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');

const PORT = 8000;
const APP_URL = `http://127.0.0.1:${PORT}/workflow-editor/`;
const PROJECT_ROOT = path.resolve(__dirname, '..');

let backendProc = null;
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

function findPython() {
  // 优先 venv, 其次系统 Python
  const candidates = [
    path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe'),
    path.join(PROJECT_ROOT, 'venv', 'Scripts', 'python.exe'),
    'python',
    'py',
  ];
  for (const c of candidates) {
    if (c !== 'python' && c !== 'py' && !fs.existsSync(c)) continue;
    return c;
  }
  return 'python';
}

async function startBackend() {
  if (await isPortOpen(PORT)) {
    console.log('[desktop] 后端已在运行, 直接打开');
    return;
  }
  const python = findPython();
  console.log('[desktop] 启动后端:', python, 'python -m src.runtime.main');
  backendProc = spawn(python, ['-m', 'src.runtime.main'], {
    cwd: PROJECT_ROOT,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
    env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
  });
  backendProc.stdout.on('data', (d) => process.stdout.write(`[backend] ${d}`));
  backendProc.stderr.on('data', (d) => process.stderr.write(`[backend-err] ${d}`));
  backendProc.on('exit', (code) => {
    console.log('[desktop] 后端退出:', code);
    backendProc = null;
  });

  // 等待端口就绪 (最长 30s)
  for (let i = 0; i < 60; i++) {
    if (await isPortOpen(PORT)) {
      console.log('[desktop] 后端就绪');
      return;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  dialog.showErrorBox('启动失败', 'Python 后端 30 秒内未就绪, 请确认依赖已安装:\n  pip install -r requirements.txt');
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
  await startBackend();
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  // 不退出后端, 保持扩展连接; 完全退出用 app.quit
  if (process.platform !== 'darwin') app.quit();
});

app.on('quit', () => {
  if (backendProc) {
    console.log('[desktop] 关闭后端');
    backendProc.kill();
    backendProc = null;
  }
});
