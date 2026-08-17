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

const name = "rpa-bridge";
const inject = ["tools", "systemPrompt"];

const Config = z.object({
  backendUrl: z.string().default("http://127.0.0.1:8000"),
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
/* 迷你 REST 客户端（镜像 src/mcp_server/client.py 的认证逻辑）        */
/* ------------------------------------------------------------------ */

function createApi(cfg) {
  const base = cfg.backendUrl.replace(/\/+$/, "");
  let token = cfg.token || "";

  async function ensureToken() {
    if (token) return token;
    const { username, password } = cfg;
    if (!username || !password) {
      throw new Error("RPA 未配置认证：请设置 token 或 username/password");
    }
    const resp = await fetch(`${base}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
      signal: AbortSignal.timeout(10000),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.access_token) {
      throw new Error(`RPA 登录失败 HTTP ${resp.status}: ${JSON.stringify(data).slice(0, 200)}`);
    }
    token = data.access_token;
    return token;
  }

  async function request(method, path, { auth = true, body, signal, timeoutMs } = {}) {
    const headers = {};
    if (auth) headers.Authorization = `Bearer ${await ensureToken()}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs ?? 60000);
    if (signal) {
      signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
    try {
      let resp = await fetch(`${base}${path}`, {
        method,
        headers,
        signal: controller.signal,
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      });
      if (resp.status === 401 && auth && !cfg.token) {
        // 登录拿到的 token 过期 → 重登一次再试
        token = "";
        headers.Authorization = `Bearer ${await ensureToken()}`;
        resp = await fetch(`${base}${path}`, {
          method,
          headers,
          signal: controller.signal,
          ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
        });
      }
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

  /* -------- 后端生命周期：adopt-don't-own（与桌面版共存的关键） --------
   * 桌面版（desktop/main.js）不 spawn 后端，只探测 :8000 并加载同一个 SPA。
   * 因此规则必须是"单一所有者 + 先探测再接管"：
   *   1. 先健康检查：后端已在跑（含桌面版用户手动起的）→ adopt：不 spawn、dispose 不 kill
   *   2. 未就绪且配置了 autoStartBackend → 由本插件 spawn，标记 owned，dispose 时回收
   *   3. 端口被非本项目进程占用 → 仅告警，不 spawn（工具会报错并提示手动启动）
   */
  let ownedBackend = null;
  setTimeout(async () => {
    try {
      await api.get("/health", { auth: false, timeoutMs: 3000 });
      ctx.logger.info("[rpa-bridge] 后端已在运行，接管现有实例（adopt，不回收）");
    } catch (err) {
      if (!config.autoStartBackend || !config.backendCommand) {
        ctx.logger.warn(`[rpa-bridge] 后端不可达（${err.message}）。请启动后端，或在配置中开启 autoStartBackend。`);
        return;
      }
      try {
        const child = spawn(config.backendCommand, {
          cwd: config.backendCwd || undefined,
          detached: true,
          stdio: "ignore",
          shell: true,
        });
        child.on("error", (e) => ctx.logger.warn(`[rpa-bridge] 后端启动失败: ${e.message}`));
        child.unref();
        ownedBackend = child;
        ctx.logger.info("[rpa-bridge] 已托管启动后端（owned，dispose 时回收）");
      } catch (e) {
        ctx.logger.warn(`[rpa-bridge] 后端启动异常: ${e.message}`);
      }
    }
  }, 0);

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

  /* -------- 系统提示段：教模型正确使用 RPA 工具 -------- */
  ctx.systemPrompt.section({
    name: "rpa:system",
    order: 112,
    text: [
      "RPA 浏览器自动化系统可用（工具前缀 rpa_）。用法约定：",
      "- 构建工作流：先 rpa_commands 看指令目录，把完整定义写入工作区 JSON 文件（节点含 parent_id/order/extra），再 rpa_import_workflow 一次性导入 —— 不要逐节点多次调用。",
      "- 运行：rpa_run_start 异步启动 → rpa_run_wait 等结果（可中断）。不要在同一工具调用里长时间阻塞。",
      "- 浏览器扩展连接是单实例：工作流运行中调 rpa_browser_exec 会 409，除非 allow_during_run=true。",
      "- 桌面指令（Win32/UIA）仅 Windows；后端需常驻且扩展已连接，先 rpa_status 确认。",
    ].join("\n"),
  });

  /* ================= 1. 健康检查 ================= */
  ctx.tools.register(defineTool({
    name: "rpa_status",
    description: "RPA 系统健康检查：后端是否可达、浏览器扩展是否在线、活跃连接与活跃运行。执行 RPA 工作流前先调用。",
    parameters: {},
    output: { schema: { type: "object", additionalProperties: true }, render: toText },
    isConcurrencySafe: () => true,
    async execute(_args, exec) {
      const [health, ext] = await Promise.allSettled([
        api.get("/health", { auth: false, signal: exec.signal }),
        api.get("/api/extension/status", { auth: false, signal: exec.signal }),
      ]);
      return {
        backend: health.status === "fulfilled" ? health.value : { ok: false, error: String(health.reason) },
        extension: ext.status === "fulfilled" ? ext.value : { error: String(ext.reason) },
      };
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
    output: { schema: { type: "array", items: { type: "object", additionalProperties: true } }, render: toText },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const browser = (args.side ?? "editor") === "browser";
      return await api.get(browser ? "/api/extension/commands" : "/api/workflows/commands", {
        auth: !browser,
        signal: exec.signal,
      });
    },
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
    async execute(args, exec) {
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
    },
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
    async execute(args, exec) {
      // 后端 async 模式：body 带 async:true → 立即返回 run_id；进度走 run/stream 或 log 接口
      const body = { async: true };
      if (args.parameters) body.parameters = args.parameters;
      if (args.initial_table_data) body.initialTableData = args.initial_table_data;
      const r = await api.post(`/api/workflows/${args.wf_id}/run/extension`, { body, signal: exec.signal });
      return { run_id: r.runId ?? r.run_id ?? "", ...r };
    },
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
    async execute(args, exec) {
      const deadline = Date.now() + (args.timeout_ms ?? 300000);
      const path = `/api/workflows/${args.wf_id}/runs/${args.run_id}/log`;
      for (;;) {
        const log = await api.get(path, { signal: exec.signal });
        if (isTerminal(log)) return { ...log, finished: true };
        if (Date.now() >= deadline) return { ...log, timeout: true };
        await abortableSleep(config.waitPollMs, exec.signal);
      }
    },
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
    async execute(args, exec) {
      return await api.get(`/api/workflows/${args.wf_id}/runs/${args.run_id}/log`, { signal: exec.signal });
    },
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
    async execute(args, exec) {
      return await api.post(`/api/workflows/${args.wf_id}/run/${args.run_id}/${args.action}`, {
        body: {}, signal: exec.signal,
      });
    },
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
    async execute(args, exec) {
      return await browserExec(api, config, args, exec.signal);
    },
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
      async execute(args, exec) {
        return await browserExec(api, config, w.toArgs(args), exec.signal);
      },
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
      description: "RPA 状态与页面入口：/rpa 状态、/rpa open 打开编辑器、/rpa list 列工作流、/rpa run <名称|id>",
      input: { hint: "[open|list|run <名称|id>]" },
      async handler({ rawInput }) {
        const line = rawInput.trim();
        if (!line) {
          try {
            const s = await api.get("/api/extension/status", { auth: false, timeoutMs: 5000 });
            return {
              kind: "success",
              text: `RPA 后端在线，扩展 ${s.online ? "已连接" : "未连接"}（${s.count} 连接）。\n` +
                `编辑器：${config.backendUrl}/workflow-editor/\n` +
                `/rpa open ｜ /rpa list ｜ /rpa run <名称|id>`,
            };
          } catch (e) { return apiErr(e); }
        }
        const [cmd, ...rest] = line.split(/\s+/);
        const arg = rest.join(" ");
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
