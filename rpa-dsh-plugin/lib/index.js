/**
 * rpa-dsh-plugin — RPA Script 的 DSH 原生工具插件（Cordis v4 格式）。
 *
 * 设计要点（对应"更优化的方案"）：
 *   1. 小工具面 + 按需目录：不把 67 个指令全量注册成工具，而是
 *      rpa_commands 按需拉目录 + 少量高频便捷封装（省 context token）。
 *   2. 文件即工作流：模型用 DSH 文件工具写好 JSON，rpa_import_workflow
 *      一次原子导入（避免逐节点 N 次调用）。
 *   3. 异步运行：rpa_run_start 立即返回 run_id，rpa_run_wait 可中断轮询
 *      （避免长流程撞 60s 工具超时）。
 *   4. 直接调 REST（fetch），不经 MCP 双跳；认证机制与
 *      src/mcp_server/client.py 完全一致（Bearer token + 401 重登一次）。
 *
 * 已确认的产品决策（访谈）：
 *   - 后台服务：T1 —— 插件托管 Python 后端（autoStartBackend 配置项）
 *   - 并行：先单流程（默认容量 1），并行后置
 *   - 认证：保持后端登录，DSH 代管凭证（token / username+password，401 自动重登）
 *   - 页面：独立页面（:8000）+ DSH 内 /rpa 斜杠命令跳转
 *   - NL 生成：模型直接产出节点 JSON，C1-C4 向量匹配不做
 *
 * 后端前置（P0 已完成）：
 *   [x] POST /api/workflows/import            —— 原子导入（rpa_import_workflow 依赖）
 *   [x] run/extension 增加 async 模式          —— 立即返回 run_id（rpa_run_start 依赖）
 *
 * 安装（web profile）：
 *   dsh plugin --profile web add file:../rpa-dsh-plugin
 *   然后编辑 ~/.dsh/profiles/web/cordis.patch.yml 加入实例条目（见 README）。
 */

import { defineTool } from "@deepseek-ai/dsh-tools";
import z from "@deepseek-ai/schemastery";
import { spawn, execFile } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, extname, join, resolve, sep } from "node:path";
import { homedir } from "node:os";
import { createRequire } from "node:module";

const _require = createRequire(import.meta.url);
function require_node_child_process() {
  return _require("node:child_process");
}

const name = "rpa-bridge";
const inject = ["tools", "systemPrompt", "webServer"];

const Config = z.object({
  // 后端地址：留空自动从端口文件发现（随机端口 8100-8199）；也可显式固定
  backendUrl: z.string().default(""),
  // 以下字段保留兼容旧配置，后端已免认证（RPA_AUTH_DISABLED 默认开），不再使用
  token: z.string().default(""),
  username: z.string().default(""),
  password: z.string().default(""),
  // 可选：激活时自动拉起后端（detached，不接管生命周期）
  autoStartBackend: z.boolean().default(false),
  backendCommand: z.string().default(""),
  backendCwd: z.string().default(""),
  // 浏览器单指令默认超时
  browserExecTimeoutMs: z.number().default(30000),
  // rpa_run_wait 轮询间隔
  waitPollMs: z.number().default(1500),
});

/* ------------------------------------------------------------------ */
/* Python 后端自举（npm 发布形态：无仓库可用时在包内建 venv）          */
/* ------------------------------------------------------------------ */

/** 本模块绝对路径对应的包根目录（<pkg>/lib/index.js → <pkg>）。 */
function packageRoot() {
  return resolve(dirname(fileURLToPath(import.meta.url)), "..");
}

/** 包内 python/ 后端目录（npm 形态）。 */
function bundledPythonDir() {
  return join(packageRoot(), "python");
}

/** workflow-editor 静态文件根：优先包内（npm 形态），本地形态回退仓库源码产物。 */
function editorStaticRoot() {
  const inPkg = join(packageRoot(), "python", "static", "workflow-editor");
  if (existsSync(join(inPkg, "index.html"))) return inPkg;
  // 本地 file: 形态（仓库）：../python/static/workflow-editor 未打包时读仓库源码产物
  const repo = join(packageRoot(), "..", "src", "runtime", "static", "workflow-editor");
  if (existsSync(join(repo, "index.html"))) return resolve(repo);
  return inPkg;
}

/** 静态文件 MIME 表（workflow-editor 构建产物用到的类型）。 */
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".map": "application/json; charset=utf-8",
};

/** 静态文件响应：路径穿越防护 + SPA fallback 到 index.html。 */
function serveStatic(root, pathname, res) {
  let rel = decodeURIComponent(pathname.split("?")[0]);
  // 路径穿越防护：仅允许包内相对路径
  const safe = resolve(root, "." + rel);
  if (!safe.startsWith(root + sep)) {
    res.writeHead(403, { "Content-Type": "text/plain" });
    res.end("forbidden");
    return;
  }
  let target = safe;
  try {
    if (!statSync(target).isFile()) target = join(root, "index.html");
  } catch {
    target = join(root, "index.html");
  }
  try {
    const data = readFileSync(target);
    const type = MIME[extname(target).toLowerCase()] ?? "application/octet-stream";
    res.writeHead(200, { "Content-Type": type, "Cache-Control": "no-cache" });
    res.end(data);
  } catch (e) {
    res.writeHead(404, { "Content-Type": "text/plain" });
    res.end("not found");
  }
}

/** 数据目录：npm 形态落到用户 .dsh 下（不污染 node_modules）。 */
function defaultDataDir() {
  return join(homedir(), ".dsh", "rpa-data");
}

function hasCommand(cmd) {
  try {
    const { spawnSync } = require_node_child_process();
    const r = spawnSync(cmd, ["--version"], { stdio: "ignore", timeout: 10000, shell: process.platform === "win32" });
    return r.status === 0;
  } catch {
    return false;
  }
}

// 动态 require（ESM 下避免静态依赖 child_process 的 spawnSync 影响 tree-shake 无碍）

/**
 * 异步 spawn 并等待完成（stdio 继承输出）。替代 spawnSync：
 * 不阻塞 Node 事件循环 —— dsh web 启动不会被 venv 创建/依赖安装卡住。
 */
function spawnAsync(cmd, args, opts) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { ...opts, stdio: "inherit" });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${cmd} exited with code ${code}`));
    });
  });
}

/**
 * 确保 python/ 下有可用 venv（uv 优先，pip 兜底），返回 python 可执行文件路径。
 * 幂等：venv 已存在且 requirements 满足则直接复用（快速路径）。
 * 首次创建为异步（spawn 后台执行），不阻塞 dsh web 启动；后端待 venv 就绪后拉起。
 */
async function ensureBundledVenv(pythonDir, log) {
  const venvPy = join(pythonDir, "venv", "Scripts", "python.exe");
  if (existsSync(venvPy)) {
    log?.("[rpa-bridge] 复用已有 venv");
    return venvPy;
  }
  const req = join(pythonDir, "requirements.txt");
  if (!existsSync(req)) {
    throw new Error(`[rpa-bridge] python/ 缺少 requirements.txt（${req}）—— 插件包构建不完整`);
  }

  // 1) uv 优先：uv venv + uv pip install（约快 10x）
  if (hasCommand("uv")) {
    log?.("[rpa-bridge] 使用 uv 创建 venv（首次安装，异步后台进行）…");
    try {
      await spawnAsync("uv", ["venv", "venv", "--python", "3.12"], { cwd: pythonDir, timeout: 120000 });
      await spawnAsync("uv", ["pip", "install", "-p", "venv", "-r", "requirements.txt"], { cwd: pythonDir, timeout: 600000 });
      return venvPy;
    } catch (e) {
      log?.(`[rpa-bridge] uv 安装失败（${e.message}），回退 pip`);
    }
  }

  // 2) pip 兜底：python -m venv + pip install
  const py = process.env.RPA_PYTHON || "py";
  log?.("[rpa-bridge] 使用 pip 创建 venv（首次安装，异步后台进行）…");
  try {
    await spawnAsync(py, ["-3", "-m", "venv", "venv"], { cwd: pythonDir, timeout: 180000 });
  } catch {
    await spawnAsync("python", ["-m", "venv", "venv"], { cwd: pythonDir, timeout: 180000 });
  }
  const pip = join(pythonDir, "venv", "Scripts", "pip.exe");
  try {
    await spawnAsync(pip, ["install", "-r", "requirements.txt"], { cwd: pythonDir, timeout: 600000 });
  } catch {
    throw new Error("[rpa-bridge] pip 安装依赖失败，请手动运行：uv pip install -r requirements.txt（在 python/ 目录）");
  }
  return venvPy;
}

/**
 * 解析后端启动命令。
 * 返回 { command, cwd, env } 或 null（不可启动）。
 * - backendCommand 已配置（本地 file: 形态）→ 原样使用
 * - 未配置且包内 python/ 存在（npm 形态）→ 自举 venv 后使用
 */
async function resolveBackendLaunch(cfg, log) {
  if (cfg.backendCommand) {
    // 兼容字符串命令（走 shell）；同时拆分 argv 供无窗口启动
    const cmd = cfg.backendCommand.trim();
    return {
      command: cmd,
      argv: parseCommandLine(cmd),
      cwd: cfg.backendCwd || undefined,
      env: {},
    };
  }
  const pythonDir = bundledPythonDir();
  if (!existsSync(join(pythonDir, "src", "runtime", "main.py"))) {
    return null; // 无包内后端：调用方决定是否告警
  }
  const venvPy = await ensureBundledVenv(pythonDir, log);
  const dataDir = process.env.RPA_DATA_DIR || defaultDataDir();
  mkdirSync(dataDir, { recursive: true });
  return {
    command: `"${venvPy}" -m src.runtime.main`,
    argv: [venvPy, "-m", "src.runtime.main"],
    cwd: pythonDir,
    env: { RPA_DATA_DIR: dataDir, RPA_REPO_ROOT: pythonDir },
  };
}

/**
 * 简单命令行解析（支持双引号路径），用于无 shell 启动。
 * 仅处理本项目的命令形态：`"C:\path with space\python.exe" -m src.runtime.main`。
 */
function parseCommandLine(cmdline) {
  const argv = [];
  let cur = "";
  let inQuote = false;
  for (let i = 0; i < cmdline.length; i++) {
    const ch = cmdline[i];
    if (ch === '"') {
      inQuote = !inQuote;
    } else if (ch === " " && !inQuote) {
      if (cur) { argv.push(cur); cur = ""; }
    } else {
      cur += ch;
    }
  }
  if (cur) argv.push(cur);
  return argv;
}

/* ------------------------------------------------------------------ */
/* 迷你 REST 客户端（后端免认证：RPA_AUTH_DISABLED 默认开，无需 JWT）  */
/* ------------------------------------------------------------------ */

/** 解析后端 base URL：配置 backendUrl 优先；否则读端口文件（随机端口自动适配）。 */
function resolveBackendUrl(cfg) {
  const explicit = (cfg.backendUrl || "").trim();
  if (explicit) return explicit.replace(/\/+$/, "");
  const candidates = [];
  if (process.env.RPA_DATA_DIR) candidates.push(join(process.env.RPA_DATA_DIR, "backend.port"));
  candidates.push(join(defaultDataDir(), "backend.port")); // ~/.dsh/rpa-data
  if (cfg.backendCwd) candidates.push(join(cfg.backendCwd, "data", "backend.port"));
  candidates.push(join(process.cwd(), "data", "backend.port"));
  for (const f of candidates) {
    try {
      const port = readFileSync(f, "utf8").trim();
      if (/^\d+$/.test(port)) return `http://127.0.0.1:${port}`;
    } catch {}
  }
  return "http://127.0.0.1:8000"; // 兜底（旧版固定端口）
}

function createApi(cfg) {
  async function request(method, path, { body, signal, timeoutMs } = {}) {
    const headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs ?? 60000);
    if (signal) {
      signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
    try {
      const base = resolveBackendUrl(cfg); // 每次请求解析：后端重启换端口自动适配
      let resp = await fetch(`${base}${path}`, {
        method,
        headers,
        signal: controller.signal,
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      });
      const text = await resp.text();
      let data = {};
      if (text) {
        try { data = JSON.parse(text); } catch { data = text; }
      }
      if (!resp.ok) {
        const detail = typeof data === "string" ? data : JSON.stringify(data.detail ?? data);
        throw new Error(`HTTP ${resp.status}: ${String(detail).slice(0, 300)}`);
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  }

  return {
    get: (p, o) => request("GET", p, o),
    post: (p, o) => request("POST", p, o),
  };
}

/** spawn 后端后轮询等待其就绪（随机端口：等端口文件 + health）。 */
async function waitForBackendReady(cfg, timeoutMs = 30000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const api = createApi(cfg);
      await api.get("/health", { timeoutMs: 1500 });
      return true;
    } catch {}
    await new Promise((r) => setTimeout(r, 1000));
  }
  return false;
}

/* ------------------------------------------------------------------ */
/* 小工具                                                            */
/* ------------------------------------------------------------------ */

const toText = (_args, value) => [
  { type: "text", text: typeof value === "string" ? value : JSON.stringify(value, null, 2) },
];

function abortableSleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(signal.reason ?? new Error("aborted"));
    const t = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(t);
      reject(signal.reason ?? new Error("aborted"));
    }, { once: true });
  });
}

/** 判断一次运行是否已到终态。后端 get_run_log 返回 {events, running, runId}，running 为权威信号。 */
function isTerminal(log) {
  if (!log || typeof log !== "object") return false;
  if (typeof log.running === "boolean") return !log.running;
  if (typeof log.status === "string") {
    return ["completed", "failed", "stopped", "error", "done"].includes(log.status);
  }
  const events = log.events ?? log.log ?? [];
  if (Array.isArray(events) && events.length) {
    const last = events[events.length - 1];
    const evt = typeof last === "string" ? last : (last?.type ?? last?.event ?? "");
    return typeof evt === "string" && /(finished|failed|stopped|done|error|completed)$/i.test(evt);
  }
  return Boolean(log.finishedAt ?? log.completedAt ?? log.endTime);
}

/** 浏览器单指令透传（/api/extension/exec，免认证；与工作流运行互斥 409）。 */
function browserExec(api, cfg, args, signal) {
  return api.post("/api/extension/exec", {
    auth: false,
    timeoutMs: args.timeout ?? cfg.browserExecTimeoutMs,
    signal,
    body: {
      type: args.type,
      locator: args.locator ?? "",
      selectorFamily: args.selector_family ?? "css",
      action: args.action ?? "",
      extra: args.extra ?? {},
      timeout: args.timeout ?? cfg.browserExecTimeoutMs,
      allowDuringRun: args.allow_during_run ?? false,
    },
  });
}

function apply(ctx, config) {
  const api = createApi(config);

  /* -------- 激活时健康检查（不阻塞激活，失败仅告警） -------- */
  setTimeout(() => {
    api.get("/health", { auth: false, timeoutMs: 5000 })
      .then(() => ctx.logger.info("[rpa-bridge] 后端健康"))
      .catch((err) => ctx.logger.warn(
        `[rpa-bridge] 后端不可达（${err.message}）。RPA 工具将报错；` +
        `请启动后端，或配置 autoStartBackend + backendCommand 自动拉起。`
      ));
  }, 0);

  /* -------- 后端生命周期：adopt-don't-own + 懒启动 --------
   * 桌面版（desktop/main.js）不 spawn 后端，只探测后端就绪后加载同一个 SPA。
   * 懒启动：dsh web 激活时**只做快速健康检查**（后端在跑则 adopt，不回收），
   * 不 spawn —— dsh web 启动不被后端拖慢。真正的启动发生在**首次需要时**：
   *   - 工具调用（ensureStarted，自动拉起）
   *   - RPA 抽屉「启动后端」按钮（startBackendProcess）
   * 端口被非本项目进程占用 → 仅告警，不 spawn。
   */
  let ownedBackend = null;
  let launchErrorShown = false;
  let backendAdopted = false;
  setTimeout(async () => {
    try {
      await api.get("/health", { auth: false, timeoutMs: 1500 });
      backendAdopted = true;
      ctx.logger.info("[rpa-bridge] 后端已在运行，接管现有实例（adopt，不回收）");
    } catch (err) {
      if (!launchErrorShown) {
        ctx.logger.info(
          `[rpa-bridge] 后端未运行（懒启动）：首次使用 RPA 工具或打开控制台时自动拉起；` +
          (config.autoStartBackend ? "" : " 或配置 autoStartBackend 允许自动拉起。")
        );
        launchErrorShown = true;
      }
    }
  }, 0);

  /* 懒启动入口：首次调用（工具/抽屉）时探测 → 未运行则 spawn。失败会重置以便下次重试。 */
  let ensurePromise = null;
  const ensureStarted = () => {
    if (!ensurePromise) {
      ensurePromise = (async () => {
        let alive = false;
        try { await api.get("/health", { timeoutMs: 1500 }); alive = true; } catch {}
        if (alive) return;
        if (!config.autoStartBackend) {
          throw new Error("后端未运行。请在 RPA 控制台点「启动后端」，或开启 autoStartBackend 自动拉起。");
        }
        const r = await startBackendProcess("start");
        if (!r.ok) throw new Error(r.error || "后端启动失败");
      })().catch((e) => { ensurePromise = null; throw e; });
    }
    return ensurePromise;
  };
  /** 工具 execute 包装：调用前惰性确保后端（失败不阻塞，工具自身会报不可达）。 */
  const withEnsure = (fn) => async (args, exec) => {
    try { await ensureStarted(); } catch { /* 留给工具自身的错误路径 */ }
    return fn(args, exec);
  };


  ctx.on("dispose", () => {
    if (!ownedBackend) return;
    ctx.logger.info("[rpa-bridge] 回收托管的后端进程");
    try {
      // shell:true 下 kill() 只杀包装进程，Windows 用 taskkill /T 杀整棵进程树
      if (process.platform === "win32") {
        execFile("taskkill", ["/PID", String(ownedBackend.pid), "/T", "/F"], () => {});
      } else {
        ownedBackend.kill();
      }
    } catch { /* ignore */ }
  });

  /* -------- 启动/重启后端（client 抽屉按钮触发，经 dsh web 同源 HTTP） -------- */
  /** 通过 netstat 找监听某端口的进程 PID（Windows）。 */
  const findPortPid = (port) => new Promise((resolve) => {
    execFile("netstat", ["-ano"], { timeout: 5000 }, (err, stdout) => {
      if (err) return resolve(null);
      const lines = String(stdout).split(/\r?\n/);
      for (const line of lines) {
        const m = line.trim().match(/TCP\s+[^\s]+:(\d+)\s+\S+\s+LISTENING\s+(\d+)/);
        if (m && Number(m[1]) === Number(port)) return resolve(Number(m[2]));
      }
      resolve(null);
    });
  });
  /** 杀掉监听指定端口的进程（外部托管时接管用）。 */
  const killPortOwner = async (port) => {
    const pid = await findPortPid(port);
    if (!pid) return false;
    if (process.platform === "win32") {
      await new Promise((r) => execFile("taskkill", ["/PID", String(pid), "/T", "/F"], () => r()));
    } else {
      try { process.kill(pid, "SIGTERM"); } catch {}
    }
    return true;
  };

  const startBackendProcess = async (action) => {
    const probe = async () => {
      try { await api.get("/health", { timeoutMs: 2000 }); return true; } catch { return false; }
    };
    const alive = await probe();
    if (alive && action !== "restart") {
      return { ok: true, already: true };
    }
    if (alive && action === "restart") {
      // 无论是否插件托管，restart 语义 = 接管：先停掉占用当前端口的进程，再拉起。
      // 外部托管（如 agent/桌面版启动）也会被接管，此后 ownedBackend 归插件，可再次重启。
      let stopped = false;
      try {
        if (ownedBackend) {
          const pid = ownedBackend.pid;
          if (process.platform === "win32") {
            await new Promise((r) => execFile("taskkill", ["/PID", String(pid), "/T", "/F"], () => r()));
          } else {
            ownedBackend.kill();
          }
          ownedBackend = null;
          stopped = true;
        } else {
          // 外部托管：解析端口文件 → 杀端口占用进程
          const base = resolveBackendUrl(config);
          const m = base.match(/:(\d+)$/);
          if (m) {
            stopped = await killPortOwner(m[1]);
            ctx.logger.info(`[rpa-bridge] 接管重启：停止外部后端（端口 ${m[1]}）`);
          }
        }
        if (!stopped) {
          return { ok: false, error: "未找到后端进程，可能已停止（尝试直接启动）" };
        }
        await new Promise((r) => setTimeout(r, 2000));
      } catch (e) {
        return { ok: false, error: `停止后端失败: ${e.message}` };
      }
    }
    const launch = await resolveBackendLaunch(config, (m) => ctx.logger.info(m));
    if (!launch) {
      return { ok: false, error: "无可用的后端启动方式（本地形态请配置 backendCommand 指向仓库 venv）" };
    }
    const env = { ...process.env, ...launch.env };
    // 优先无 shell 启动（argv 直连可执行文件，彻底隐藏 cmd 窗口）；
    // argv 不可用（命令含 shell 语法）才回退 shell + windowsHide。
    const child = launch.argv
      ? spawn(launch.argv[0], launch.argv.slice(1), {
          cwd: launch.cwd || undefined,
          detached: true,
          stdio: "ignore",
          windowsHide: true,
          env,
        })
      : spawn(launch.command, {
          cwd: launch.cwd || undefined,
          detached: true,
          stdio: "ignore",
          shell: true,
          windowsHide: true,
          env,
        });
    child.on("error", (e) => ctx.logger.warn(`[rpa-bridge] 后端启动失败: ${e.message}`));
    child.unref();
    ownedBackend = child;
    ctx.logger.info(`[rpa-bridge] 已托管启动后端 ${launch.command}`);
    const ready = await waitForBackendReady(config, 30000);
    if (!ready) return { ok: false, error: "后端 30s 内未就绪" };
    // 读端口文件返回实际端口
    let port;
    try {
      const base = resolveBackendUrl(config);
      const m = base.match(/:(\d+)$/);
      if (m) port = m[1];
    } catch {}
    return { ok: true, port };
  };

  const readRequestBody = (req) => new Promise((resolve) => {
    let body = "";
    req.on("data", (c) => { body += c; if (body.length > 1e5) req.destroy(); });
    req.on("end", () => {
      try { resolve(body ? JSON.parse(body) : {}); } catch { resolve({}); }
    });
    req.on("error", () => resolve({}));
  });

  try {
    ctx.webServer.register({
      kind: "exact",
      path: "/rpa-bridge/start-backend",
      handler: async (req, res) => {
        const send = (obj, status = 200) => {
          res.writeHead(status, { "Content-Type": "application/json" });
          res.end(JSON.stringify(obj));
        };
        if (req.method !== "POST") return send({ ok: false, error: "method not allowed" }, 405);
        let action = "start";
        try { action = (await readRequestBody(req)).action || "start"; } catch {}
        try {
          send(await startBackendProcess(action));
        } catch (e) {
          send({ ok: false, error: e.message });
        }
      },
    }, "rpa-bridge: start-backend route");
    ctx.logger.info("[rpa-bridge] 已注册 /rpa-bridge/start-backend（RPA 控制台可一键启动/重启后端）");
  } catch (e) {
    ctx.logger.warn(`[rpa-bridge] 注册 start-backend 路由失败: ${e.message}`);
  }

  /* -------- RPA 流程工作区探测（client 判断普通/流程会话，经 dsh web 同源 HTTP） -------- */
  const RPA_MARKER = "rpa.json"; // 目录内存在该文件 = RPA 流程工作区（与 client.js 约定一致）
  try {
    ctx.webServer.register({
      kind: "exact",
      path: "/rpa-bridge/project-check",
      handler: async (req, res) => {
        const send = (obj, status = 200) => {
          res.writeHead(status, { "Content-Type": "application/json" });
          res.end(JSON.stringify(obj));
        };
        if (req.method !== "GET") return send({ ok: false, error: "method not allowed" }, 405);
        let path = "";
        try {
          const u = new URL(req.url, "http://localhost");
          path = u.searchParams.get("path") ?? "";
        } catch {}
        if (!path) return send({ ok: false, error: "missing path" }, 400);
        try {
          const marker = join(path, RPA_MARKER);
          const isRpa = existsSync(marker);
          let meta = null;
          if (isRpa) {
            try { meta = JSON.parse(readFileSync(marker, "utf8")); } catch { meta = {}; }
          }
          send({ ok: true, path, isRpa, meta });
        } catch (e) {
          send({ ok: false, error: e.message }, 500);
        }
      },
    }, "rpa-bridge: project-check route");
    ctx.logger.info("[rpa-bridge] 已注册 /rpa-bridge/project-check（RPA 流程工作区探测）");
  } catch (e) {
    ctx.logger.warn(`[rpa-bridge] 注册 project-check 路由失败: ${e.message}`);
  }

  /* -------- RPA 流程工作区文件读写（编辑免后端：node 侧 fs 代理） --------
   * workflow-editor 在 :8100（后端）加载，但编辑持久化经 dsh web（:3080）同源 HTTP，
   * 跨源 → 响应必须带 CORS 头 + 处理 OPTIONS 预检。
   * 白名单与 project_router.py 一致；写要求目录含 rpa.json（防任意目录写入）。
   */
  const PROJECT_READABLE = ["rpa.json", "workflow.json", "elements.json", "data.json"];
  const PROJECT_WRITABLE = ["workflow.json", "elements.json", "data.json"];
  const CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, PUT, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
  /** 统一 CORS 响应（跨源：dsh web :3080 被 :8100 iframe 调用）。 */
  const corsSend = (res, obj, status = 200) => {
    res.writeHead(status, { ...CORS_HEADERS, "Content-Type": "application/json" });
    res.end(JSON.stringify(obj));
  };
  const projectRoot = (path) => resolve(path || "");

  try {
    // 读：GET /rpa-bridge/project/read?path=<dir>&file=<白名单>
    ctx.webServer.register({
      kind: "exact",
      path: "/rpa-bridge/project/read",
      handler: async (req, res) => {
        if (req.method === "OPTIONS") return corsSend(res, {}, 204);
        if (req.method !== "GET") return corsSend(res, { ok: false, error: "method not allowed" }, 405);
        let path = "", file = "";
        try {
          const u = new URL(req.url, "http://localhost");
          path = u.searchParams.get("path") ?? "";
          file = u.searchParams.get("file") ?? "";
        } catch {}
        if (!path || !file) return corsSend(res, { ok: false, error: "missing path/file" }, 400);
        if (!PROJECT_READABLE.includes(file)) {
          return corsSend(res, { ok: false, error: `file 必须在白名单内: ${PROJECT_READABLE.join("/")}` }, 400);
        }
        const root = projectRoot(path);
        try {
          const target = join(root, file);
          const isRpa = existsSync(join(root, RPA_MARKER));
          if (!existsSync(target)) {
            return corsSend(res, { ok: true, path: root, file, exists: false, isRpa, data: null });
          }
          let data = null;
          try { data = JSON.parse(readFileSync(target, "utf8")); } catch { data = null; }
          corsSend(res, { ok: true, path: root, file, exists: true, isRpa, data });
        } catch (e) {
          corsSend(res, { ok: false, error: e.message }, 500);
        }
      },
    }, "rpa-bridge: project read route");

    // 写：PUT /rpa-bridge/project/write?path=<dir>&file=<白名单>（body=JSON）
    ctx.webServer.register({
      kind: "exact",
      path: "/rpa-bridge/project/write",
      handler: async (req, res) => {
        if (req.method === "OPTIONS") return corsSend(res, {}, 204);
        if (req.method !== "PUT") return corsSend(res, { ok: false, error: "method not allowed" }, 405);
        let path = "", file = "";
        try {
          const u = new URL(req.url, "http://localhost");
          path = u.searchParams.get("path") ?? "";
          file = u.searchParams.get("file") ?? "";
        } catch {}
        if (!path || !file) return corsSend(res, { ok: false, error: "missing path/file" }, 400);
        if (!PROJECT_WRITABLE.includes(file)) {
          return corsSend(res, { ok: false, error: `file 必须在白名单内: ${PROJECT_WRITABLE.join("/")}` }, 400);
        }
        const root = projectRoot(path);
        try {
          if (!existsSync(join(root, RPA_MARKER))) {
            return corsSend(res, { ok: false, error: "该目录不是 RPA 流程工作区（缺少 rpa.json），拒绝写入" }, 403);
          }
          const body = await readRequestBody(req);
          const raw = JSON.stringify(body, null, 2);
          const target = join(root, file);
          const tmp = target + ".tmp";
          writeFileSync(tmp, raw, "utf8");
          renameSync(tmp, target); // 原子写
          corsSend(res, { ok: true, path: root, file, written: true });
        } catch (e) {
          corsSend(res, { ok: false, error: e.message }, 500);
        }
      },
    }, "rpa-bridge: project write route");
    ctx.logger.info("[rpa-bridge] 已注册 /rpa-bridge/project/read|write（流程编辑免后端）");
  } catch (e) {
    ctx.logger.warn(`[rpa-bridge] 注册 project 读写路由失败: ${e.message}`);
  }

  /* -------- workflow-editor 静态托管（页面免后端：dsh web serve 编辑器） -------- */
  try {
    const editorRoot = editorStaticRoot();
    ctx.webServer.register({
      kind: "prefix",
      path: "/rpa-editor/",
      handler: async (req, res) => {
        if (req.method !== "GET" && req.method !== "HEAD") {
          res.writeHead(405, { "Content-Type": "text/plain" });
          res.end("method not allowed");
          return;
        }
        serveStatic(editorRoot, new URL(req.url ?? "/", "http://x").pathname, res);
      },
    }, "rpa-bridge: workflow-editor static");
    ctx.logger.info(`[rpa-bridge] 已托管 workflow-editor（/rpa-editor/，源 ${editorRoot}）—— 编辑页免后端`);
  } catch (e) {
    ctx.logger.warn(`[rpa-bridge] 注册 workflow-editor 静态托管失败: ${e.message}`);
  }


  /* -------- 系统提示段：教模型正确使用 RPA 工具 -------- */
  ctx.systemPrompt.section({
    name: "rpa:system",
    order: 112,
    text: [
      "RPA 浏览器自动化系统可用（工具前缀 rpa_）。用法约定：",
      "- 构建工作流：先 rpa_commands 看指令目录，把完整定义写入工作区 JSON 文件（节点含 parent_id/order/extra），再 rpa_import_workflow 一次性导入 —— 不要逐节点多次调用。",
      "- 运行：rpa_run_start 异步启动 → rpa_run_wait 等结果（可中断）。不要在同一工具调用里长时间阻塞。",
      "- 元素定位：页面操作优先用元素库 —— 先 rpa_elements(workflow_id) 查已捕获元素，用其 name 对应的选择器（css/xpath）精确定位；没有现成元素时才推断选择器。",
      "- 标准验证模式（每个操作后必须补验证节点）：导航后 → 用 waitForElement / ifUrlContains 核对落地页；点击后 → 若触发导航/加载/面板，紧跟 waitForElement（目标或结果元素，timeout 5~15s）；输入后 → getText 回读目标元素并与期望比对（ifTextContains / ifVarEquals）；验证失败 → 用 if 条件分支或 onError=continue 兜底，不要静默继续。",
      "- 浏览器扩展连接是单实例：工作流运行中调 rpa_browser_exec 会 409，除非 allow_during_run=true。",
      "- 桌面指令（Win32/UIA）仅 Windows；后端需常驻且扩展已连接，先 rpa_status 确认。",
      "- 流程工作区：一个 RPA 流程 = 一个目录 = 一个 DSH 工作区（会话自动绑定该目录）。开始新流程时先 rpa_project_create（默认用当前会话工作目录），之后该目录下会话会出现「流程」编辑 tab，流程数据存于目录内。",
    ].join("\n"),
  });

  /* ================= 1. 健康检查 ================= */
  ctx.tools.register(defineTool({
    name: "rpa_status",
    description: "RPA 系统健康检查：后端是否可达、浏览器扩展是否在线、活跃连接与活跃运行。执行 RPA 工作流前先调用。",
    parameters: {},
    output: { schema: { type: "object", additionalProperties: true }, render: toText },
    isConcurrencySafe: () => true,
    execute: withEnsure(async (_args, exec) => {
      const [health, ext] = await Promise.allSettled([
        api.get("/health", { auth: false, signal: exec.signal }),
        api.get("/api/extension/status", { auth: false, signal: exec.signal }),
      ]);
      return {
        backend: health.status === "fulfilled" ? health.value : { ok: false, error: String(health.reason) },
        extension: ext.status === "fulfilled" ? ext.value : { error: String(ext.reason) },
      };
    }),
  }));

  /* ================= 1b. RPA 流程工作区（会话 = 目录 = workspace） ================= */
  ctx.tools.register(defineTool({
    name: "rpa_project_create",
    description: "创建一个 RPA 流程工作区：在指定目录（默认当前会话工作目录）下初始化 RPA 标记文件 rpa.json，并把该目录注册为 DSH 工作区。之后该目录下的会话会自动出现「流程」编辑 tab，RPA 流程数据（workflow.json/elements/表格）将存放于此目录。重复调用对同一目录幂等。",
    parameters: {
      path: { type: "string", description: "流程目录绝对路径；缺省用当前会话的工作目录" },
      name: { type: "string", description: "流程显示名；缺省用目录名" },
    },
    output: { schema: { type: "object", additionalProperties: true }, render: toText },
    isConcurrencySafe: () => true,
    // 注意：不走 withEnsure —— 初始化工作区是纯 node fs + workspaceRegistry，不依赖 Python 后端
    execute: async (args, exec) => {
      const cwd = exec?.agent?.session?.header?.cwd;
      const dir = (args.path || "").trim() || cwd;
      if (!dir) throw new Error("无法确定流程目录：未提供 path 且当前会话没有工作目录");
      mkdirSync(dir, { recursive: true });
      const name = (args.name || "").trim() || dir.split(/[\\/]/).filter(Boolean).pop() || "RPA 流程";
      const marker = join(dir, RPA_MARKER);
      if (!existsSync(marker)) {
        writeFileSync(marker, JSON.stringify({
          name,
          version: 1,
          created_at: new Date().toISOString(),
        }, null, 2), "utf8");
      }
      // 注册为 DSH 工作区（服务就绪时；失败不阻断 —— 目录与标记已就位）
      let workspaceId = null;
      try {
        const registry = ctx.workspaceRegistry;
        if (registry && typeof registry.create === "function") {
          const ws = await registry.create(dir, name);
          workspaceId = ws?.id ?? null;
        }
      } catch (e) {
        ctx.logger.warn(`[rpa-bridge] 注册工作区失败（目录本身已就绪）: ${e.message}`);
      }
      return { ok: true, path: dir, name, isRpa: true, workspaceId };
    },
  }));

  /* ================= 2. 指令目录（按需拉取，不常驻全量） ================= */
  ctx.tools.register(defineTool({
    name: "rpa_commands",
    description: "列出 RPA 指令目录：editor=工作流编辑器全量指令（含控制流 if/for/try，带参数 schema）；browser=浏览器扩展可执行指令。构建工作流前先调用。",
    parameters: {
      side: {
        type: "string",
        enum: ["editor", "browser"],
        description: "editor=全量编辑器目录；browser=扩展可执行指令",
      },
    },
    output: { schema: { type: "object", additionalProperties: true }, render: toText },
    isConcurrencySafe: () => true,
    execute: withEnsure(async (args, exec) => {
      const browser = (args.side ?? "editor") === "browser";
      const data = await api.get(browser ? "/api/extension/commands" : "/api/workflows/commands", {
        auth: !browser,
        signal: exec.signal,
      });
      // 后端返回 {commands, ...} 对象（browser）或 {categories, commands, containerTypes, branchTypes}（editor）；
      // 兼容裸数组，统一按对象返回，避免 dsh-tools 输出 schema 校验失败。
      return Array.isArray(data) ? { commands: data } : data;
    }),
  }));

  /* ================= 2b. 元素库（按元素名索引的选择器库，工作流绑定） ================= */
  ctx.tools.register(defineTool({
    name: "rpa_elements",
    description: "列出指定工作流的元素库：每个元素含名称、类型与定位数据（webSelector / cssCandidates / xpathCandidates / pageUrl）。操作已捕获过元素的页面时，先调本工具拿元素名对应的选择器精确定位，不要猜 CSS；运行工作流时元素名由扩展端解析。",
    parameters: {
      workflow_id: { type: "integer", required: true, description: "工作流 id（rpa_import_workflow 的返回值，或 /rpa list 查看）" },
    },
    output: { schema: { type: "object", additionalProperties: true }, render: toText },
    isConcurrencySafe: () => true,
    execute: withEnsure(async (args, exec) => {
      const data = await api.get(`/api/extension/elements?workflow_id=${args.workflow_id}`, {
        auth: false,
        signal: exec.signal,
      });
      const items = Array.isArray(data) ? data : (data.elements ?? []);
      return {
        workflow_id: args.workflow_id,
        count: items.length,
        elements: items.map((el) => ({
          name: el.name,
          elementType: el.elementType ?? "",
          elementKind: el.elementKind ?? "",
          css: el.webSelector ?? "",
          cssCandidates: Array.isArray(el.cssCandidates) ? el.cssCandidates : [],
          xpathCandidates: Array.isArray(el.xpathCandidates) ? el.xpathCandidates : [],
          pageUrl: el.pageUrl ?? "",
        })),
      };
    }),
  }));

  /* ================= 3. 文件式工作流导入（一次原子创建） ================= */
  ctx.tools.register(defineTool({
    name: "rpa_import_workflow",
    description: "用一份完整 JSON 定义原子创建工作流。nodes 为节点列表（[{cmd, action?, element_name?, parent_id?, order?, extra?}]，容器指令含 parent_id 层级）；elements 为元素库（[{name, selector, selector_family}]）。建议先用文件工具把定义写入工作区 JSON 再传入，便于审查与复用。",
    parameters: {
      name: { type: "string", required: true, description: "工作流名称" },
      description: { type: "string", description: "工作流描述" },
      url: { type: "string", description: "起始 URL" },
      parameters: { type: "array", description: "[{name, default, direction: in|out}] 流程参数" },
      nodes: { type: "array", required: true, description: "工作流节点（见描述）" },
      elements: { type: "array", description: "元素库（见描述）" },
    },
    output: { schema: { type: "object", additionalProperties: true }, render: toText },
    execute: withEnsure(async (args, exec) => {
      const body = {
        name: args.name,
        description: args.description ?? "",
        url: args.url ?? "",
        parameters: args.parameters ?? [],
        nodes: args.nodes,
        elements: args.elements ?? [],
      };
      const r = await api.post("/api/workflows/import", { body, signal: exec.signal });
      return { workflow_id: r.workflow_id ?? r.id, ...r };
    }),
  }));

  /* ================= 4. 异步启动运行 ================= */
  ctx.tools.register(defineTool({
    name: "rpa_run_start",
    description: "异步启动工作流（浏览器扩展执行），立即返回 run_id，不阻塞。用 rpa_run_wait 等结果、rpa_run_status 查进度、rpa_run_stop 停止。",
    parameters: {
      wf_id: { type: "integer", required: true, description: "工作流 id（rpa_import_workflow 的返回值）" },
      parameters: { type: "object", additionalProperties: true, description: "{\"变量名\": \"值\"} 覆盖流程参数默认值" },
      initial_table_data: { type: "object", additionalProperties: true, description: "{\"columns\": [...], \"rows\": [...]} 预置表格数据" },
    },
    output: { schema: { type: "object", additionalProperties: true }, render: toText },
    execute: withEnsure(async (args, exec) => {
      // 后端 async 模式：body 带 async:true → 立即返回 run_id；进度走 run/stream 或 log 接口
      const body = { async: true };
      if (args.parameters) body.parameters = args.parameters;
      if (args.initial_table_data) body.initialTableData = args.initial_table_data;
      const r = await api.post(`/api/workflows/${args.wf_id}/run/extension`, { body, signal: exec.signal });
      return { run_id: r.runId ?? r.run_id ?? "", ...r };
    }),
  }));

  /* ================= 5. 等待运行结束（可中断） ================= */
  ctx.tools.register(defineTool({
    name: "rpa_run_wait",
    description: "轮询等待一次运行结束（可被用户中断）。返回最终结果（success/error/outputs/步骤统计）或超时时的最新进度。",
    parameters: {
      wf_id: { type: "integer", required: true },
      run_id: { type: "string", required: true },
      timeout_ms: { type: "integer", description: "最长等待毫秒数，默认 300000" },
    },
    output: { schema: { type: "object", additionalProperties: true }, render: toText },
    timeoutMs: 360000,
    execute: withEnsure(async (args, exec) => {
      const deadline = Date.now() + (args.timeout_ms ?? 300000);
      const path = `/api/workflows/${args.wf_id}/runs/${args.run_id}/log`;
      for (;;) {
        const log = await api.get(path, { signal: exec.signal });
        if (isTerminal(log)) return { ...log, finished: true };
        if (Date.now() >= deadline) return { ...log, timeout: true };
        await abortableSleep(config.waitPollMs, exec.signal);
      }
    }),
  }));

  /* ================= 6. 运行状态 / 停止 ================= */
  ctx.tools.register(defineTool({
    name: "rpa_run_status",
    description: "查询一次运行的状态与进度（不等待）。",
    parameters: {
      wf_id: { type: "integer", required: true },
      run_id: { type: "string", required: true },
    },
    output: { schema: { type: "object", additionalProperties: true }, render: toText },
    isConcurrencySafe: () => true,
    execute: withEnsure(async (args, exec) => {
      return await api.get(`/api/workflows/${args.wf_id}/runs/${args.run_id}/log`, { signal: exec.signal });
    }),
  }));

  ctx.tools.register(defineTool({
    name: "rpa_run_stop",
    description: "停止 / 暂停 / 恢复一次运行。",
    parameters: {
      wf_id: { type: "integer", required: true },
      run_id: { type: "string", required: true },
      action: { type: "string", required: true, enum: ["stop", "pause", "resume"] },
    },
    output: { schema: { type: "object", additionalProperties: true }, render: toText },
    execute: withEnsure(async (args, exec) => {
      return await api.post(`/api/workflows/${args.wf_id}/run/${args.run_id}/${args.action}`, {
        body: {}, signal: exec.signal,
      });
    }),
  }));

  /* ================= 7. 浏览器实时指令（单条，免认证） ================= */
  ctx.tools.register(defineTool({
    name: "rpa_browser_exec",
    description: "在已连接的浏览器扩展上执行单条指令并等待结果（实时操作，不属于工作流）。type 用 rpa_commands(side=browser) 查。注意：有工作流运行时返回 409，allow_during_run=true 可强制（会与运行争用同一 WebSocket 连接）。",
    parameters: {
      type: { type: "string", required: true, description: "指令类型（clickElement/getText/navigate/getCurrentUrl/checkElementExists/inputElement 等）" },
      locator: { type: "string", description: "CSS 选择器或 XPath（selector_family=xpath）" },
      selector_family: { type: "string", enum: ["css", "xpath"] },
      action: { type: "string", description: "动作参数（部分指令需要）" },
      extra: { type: "object", additionalProperties: true, description: "指令参数（如 navigate 的 {\"url\": ...}、inputElement 的 {\"text\": ...}）" },
      timeout: { type: "number", description: "单指令超时秒数，默认 30" },
      allow_during_run: { type: "boolean", description: "工作流运行中仍强制执行" },
    },
    output: { schema: { type: "object", additionalProperties: true }, render: toText },
    execute: withEnsure(async (args, exec) => {
      return await browserExec(api, config, args, exec.signal);
    }),
  }));

  /* ================= 8. 高频便捷封装 ================= */
  const wrappers = [
    {
      name: "rpa_browser_navigate",
      description: "当前标签页导航到指定 URL。",
      parameters: { url: { type: "string", required: true, description: "完整 URL（含协议）" } },
      toArgs: (a) => ({ type: "navigate", extra: { url: a.url } }),
    },
    {
      name: "rpa_browser_click",
      description: "点击页面元素。",
      parameters: {
        locator: { type: "string", required: true, description: "CSS 选择器或 XPath" },
        selector_family: { type: "string", enum: ["css", "xpath"] },
      },
      toArgs: (a) => ({ type: "clickElement", locator: a.locator, selector_family: a.selector_family ?? "css" }),
    },
    {
      name: "rpa_browser_input",
      description: "向输入框输入文本（默认先清空；模拟键盘输入）。",
      parameters: {
        locator: { type: "string", required: true },
        text: { type: "string", required: true, description: "要输入的文本" },
        clear_first: { type: "boolean", description: "先清空再输入，默认 true" },
        press_enter: { type: "boolean", description: "输入后回车" },
      },
      toArgs: (a) => ({
        type: "inputElement",
        locator: a.locator,
        extra: { text: a.text, clearFirst: a.clear_first ?? true, pressEnter: a.press_enter ?? false },
      }),
    },
    {
      name: "rpa_browser_get_text",
      description: "获取页面元素文本。",
      parameters: {
        locator: { type: "string", required: true },
        selector_family: { type: "string", enum: ["css", "xpath"] },
      },
      toArgs: (a) => ({ type: "getText", locator: a.locator, selector_family: a.selector_family ?? "css" }),
    },
    {
      name: "rpa_browser_screenshot",
      description: "对当前标签页截图（保存到后端 data/ 目录，返回路径）。",
      parameters: {},
      toArgs: () => ({ type: "takeScreenshot" }),
    },
  ];
  for (const w of wrappers) {
    ctx.tools.register(defineTool({
      name: w.name,
      description: w.description,
      parameters: w.parameters,
      output: { schema: { type: "object", additionalProperties: true }, render: toText },
      execute: withEnsure(async (args, exec) => {
        return await browserExec(api, config, w.toArgs(args), exec.signal);
      }),
    }));
  }

  /* ================= 9. 斜杠命令（独立页面跳转 + 快速查询） =================
   * web profile 由 dsh-commands 提供命令平面；结果只进 UI，不进模型上下文。
   */
  ctx.inject(["commands"], (commandCtx) => {
    const apiErr = (e) => ({ kind: "error", text: `RPA 后端不可达：${e.message}` });
    const listWorkflows = async () => {
      const wfs = await api.get("/api/workflows", { timeoutMs: 8000 });
      return Array.isArray(wfs) ? wfs : (wfs.workflows ?? []);
    };

    commandCtx.commands.register({
      name: "rpa",
      description: "RPA 控制台与状态：/rpa 状态、/rpa console 打开控制台（流程列表/图像元素注册/运行）、/rpa open 编辑器、/rpa list 工作流、/rpa run <名称|id>、/rpa image <工作流id> 注册截图",
      input: { hint: "[console|open|list|image <id>|run <名称|id>]" },
      async handler({ rawInput }) {
        const line = rawInput.trim();
        if (!line) {
          try {
            const s = await api.get("/api/extension/status", { auth: false, timeoutMs: 5000 });
            return {
              kind: "success",
              text: `RPA 后端在线，扩展 ${s.online ? "已连接" : "未连接"}（${s.count} 连接）。\n` +
                `控制台：${config.backendUrl}/tools/rpa-console\n` +
                `编辑器：${config.backendUrl}/workflow-editor/\n` +
                `/rpa console ｜ /rpa open ｜ /rpa list ｜ /rpa run <名称|id>`,
            };
          } catch (e) { return apiErr(e); }
        }
        const [cmd, ...rest] = line.split(/\s+/);
        const arg = rest.join(" ");
        if (cmd === "console") {
          return { kind: "success", text: `打开 RPA 控制台：${config.backendUrl}/tools/rpa-console\n（流程列表 · 图像元素注册截图 · 一键运行）` };
        }
        if (cmd === "image") {
          const wf = rest[0] || "";
          return { kind: "success", text: `注册图像元素：打开 ${config.backendUrl}/tools/rpa-console，在「图像元素」区填入工作流 ID${wf ? `（${wf}）` : ""}后上传截图。\n或直接访问 ${config.backendUrl}/api/extension/image-upload-page` };
        }
        if (cmd === "open") {
          return { kind: "success", text: `打开 RPA 编辑器：${config.backendUrl}/workflow-editor/（指令定义页在左侧导航）` };
        }
        if (cmd === "list") {
          try {
            const rows = await listWorkflows();
            if (!rows.length) return { kind: "success", text: "暂无工作流。可直接在 DSH 对话里用自然语言创建（rpa_import_workflow）。" };
            return { kind: "success", text: rows.map((w) => `${w.id}\t${w.name}${w.url ? `  (${w.url})` : ""}`).join("\n") };
          } catch (e) { return apiErr(e); }
        }
        if (cmd === "run" && arg) {
          try {
            const rows = await listWorkflows();
            const hit = rows.find((w) => String(w.id) === arg) ?? rows.find((w) => w.name === arg);
            if (!hit) return { kind: "error", text: `未找到工作流：${arg}` };
            const r = await api.post(`/api/workflows/${hit.id}/run/extension`, {
              body: { async: true }, timeoutMs: 10000,
            });
            const runId = r.runId ?? r.run_id ?? "";
            return {
              kind: "success",
              text: `已异步启动 #${hit.id}「${hit.name}」 runId=${runId}。` +
                `进度：在 DSH 对话中说"查看 ${hit.name} 的运行进度"，或打开 ${config.backendUrl}/workflow-editor/。`,
            };
          } catch (e) { return apiErr(e); }
        }
        return { kind: "error", text: "用法：/rpa [open|list|run <名称|id>]" };
      },
    });
  });
}

export { Config, apply, inject, name };
