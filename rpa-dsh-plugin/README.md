# rpa-dsh-plugin

RPA Script 的 DSH 原生工具插件（Cordis v4 格式，纯 ESM，无构建步骤）。

让 DSH 用自然语言**构建 + 运行** RPA 流程：健康检查、按需指令目录、文件式工作流导入、
异步运行控制、浏览器实时指令。直接 fetch 调后端 REST（**不经 MCP 双跳**），
后端**免认证**（本机单人工具，登录/密码功能已移除；`RPA_AUTH_DISABLED=0` 可恢复认证）。

## 工具集（13 个）

| 工具 | 用途 |
|---|---|
| `rpa_status` | 后端可达性 + 扩展在线状态（运行前先调） |
| `rpa_commands` | 按需拉指令目录（editor 全量 / browser 可执行），不常驻全量 schema |
| `rpa_import_workflow` | **一次原子导入**完整工作流定义（nodes + elements） |
| `rpa_run_start` | 异步启动运行，立即返回 `run_id` |
| `rpa_run_wait` | 可中断轮询等待结束（默认 5 分钟上限） |
| `rpa_run_status` / `rpa_run_stop` | 查进度 / stop·pause·resume |
| `rpa_browser_exec` | 单条浏览器实时指令（409 互斥感知） |
| `rpa_browser_navigate / click / input / get_text / screenshot` | 高频便捷封装 |

另注册 `rpa:system` 系统提示段，教模型：文件式构建、异步运行、单连接 409 互斥、Windows-only 桌面指令；
以及 `/rpa` 斜杠命令（状态 / `open` 跳转编辑器 / `list` 列工作流 / `run` 定位工作流）。

## 已确认的产品决策（访谈结论）

| 决策点 | 结论 |
|---|---|
| 后台服务 | **T1**：插件托管 Python 后端（激活时拉起、配置 `autoStartBackend`），用户无感 |
| 并行 | 先单流程（默认容量 1），并行后置 |
| 认证 | **已移除密码功能**：后端免认证（本机单人工具）；`RPA_AUTH_DISABLED=0` 可恢复（对外部署） |
| 端口 | **随机 8100-8199**（`RPA_PORT` 可固定），写 `data/backend.port`；插件/扩展自动发现 |
| 页面 | 独立页面（随机端口）+ **DSH 内嵌抽屉**（client 半身，侧边栏 ⚙ 展开 iframe 内嵌 workflow-editor，端口自动发现）+ `/rpa` 跳转 |
| NL 生成 | 模型直接产出节点 JSON，C1–C4 向量匹配不做 |
| 扩展安装 | 桌面安装器自动注入（External Extensions JSON） |

## 与现有桌面版（Electron）共存

桌面版（`desktop/main.js`）不 spawn 后端，只探测后端就绪后加载同一个
`/workflow-editor/` SPA。因此本插件采用 **adopt-don't-own** 生命周期策略：

- 后端已在跑（含桌面版用户手动起的）→ 接管（adopt），**不 spawn、dispose 不回收**
- 未就绪且开启 `autoStartBackend` → 本插件 spawn 并标记 owned，dispose 时
  taskkill 整棵进程树回收
- 端口被非本项目进程占用 → 仅告警

效果：**桌面版零改动、功能零影响**；反而省掉"手动起后端"步骤（DSH 开着即可）。
唯一注意：DSH 与桌面版共享同一后端实例 → 容量锁（`MAX_CONCURRENT_WORKFLOWS`）、
认证、SQLite 全部共享，与"并行后置"的决策一致。

产品分工变化：桌面版保留"人工编辑/执行"角色；NL 生成入口（TODO C4）由 DSH 承担，C1–C4 可删。

## 安装（web profile）— 双形态

插件是 **dsh bundle**（`package.json` 声明 `dsh.bundle.patch`）：`dsh plugin add` 后
自动加入 `dsh.profile.bundles` 并应用插件自带的 `cordis.patch.yml`（insert rpa 实例），
**无需手写 profile 配置**。两种安装形态：

### 形态 A：本地仓库安装（开发/单机，推荐）

插件直接 `file:./` 链接仓库目录——仓库更新插件代码后 profile 自动同步，无需重装。

```powershell
# 一键安装（自动检查 pnpm → dsh plugin add → 写机器路径覆盖 → 验证）
powershell -ExecutionPolicy Bypass -File scripts/install-dsh-plugin.ps1

# 或手动（等价）：
dsh plugin --profile web add file:./rpa-dsh-plugin
```

### 形态 B：npm 发布安装（分发/其他机器）

```powershell
dsh plugin --profile web add rpa-dsh-plugin
```

npm 形态下用户没有仓库，**Python 后端由插件自举**：激活时若
`backendCommand` 未配置，自动在包内 `python/` 建 venv（uv 优先，pip 兜底）
并安装 `requirements.txt`，然后启动后端。数据目录落到
`~/.dsh/rpa-data/`（`RPA_DATA_DIR` 可改）。

### 安装后

验证（不起服务即可检查配置树）：`dsh --profile web --dump-config | findstr rpa`。
然后**重启 `dsh web`** 激活插件（运行中的实例会在写入 patch 后经 HMR 热应用）。

headless 同样可用：首次使用会自动初始化 profile，把实例加到
`~/.dsh/profiles/headless/cordis.patch.yml`，然后一条命令端到端：

```bash
dsh --profile headless "打开百度，搜索 RPA，把第一页标题存成工作流并运行"
```

### 发布 npm 包

```powershell
# 构建后端源码集 + 前端产物到 python/，然后打 tarball（不实际发布）
npm pack --prefix rpa-dsh-plugin

# 实际发布（需 npm 账号）
npm publish --prefix rpa-dsh-plugin
```

`package.json` 的 `prepack` 钩子自动执行 `scripts/build-plugin-package.ps1`
（同步后端最小集 + 构建前端产物）。tarball 内容由 `files` 白名单控制：
`lib/` + `cordis.patch.yml` + `python/`（含后端源码、指令 JSON、前端产物、requirements.txt）。

### 环境变量（bundle patch 默认值）

| 变量 | 默认 | 说明 |
|---|---|---|
| `RPA_API_TOKEN` / `RPA_USERNAME` / `RPA_PASSWORD` | admin/admin123 | **已弃用**（后端免认证，保留兼容） |
| `RPA_PORT` | 随机 8100-8199 | 固定后端端口（默认随机，写 `data/backend.port`） |
| `RPA_HOST` | 127.0.0.1 | 监听地址（默认仅回环；远程访问设 0.0.0.0） |
| `RPA_AUTOSTART_BACKEND` | 开（非 `'0'`） | 激活时自动拉起后端 |
| `RPA_BACKEND_COMMAND` / `RPA_BACKEND_CWD` | 空（npm 形态自举） | 本地形态指向仓库 venv |
| `RPA_BROWSER_EXEC_TIMEOUT_MS` / `RPA_WAIT_POLL_MS` | 30000 / 1500 | 超时与轮询 |

> 实测要点：
> ① 路径必须带 `./`（`file:./`），否则 dsh plugin 的锚定正则不匹配；
> ② 跨盘符的 `link:`/`file:` 绝对路径会被 pnpm 拼错（URL 解析把 `D:` 当 host），
> 因此本地形态推荐在**仓库根**执行（同盘）；
> ③ **不要**在 profile 里手动加 `@deepseek-ai/cordis` / `@deepseek-ai/dsh-tools`
> 依赖。宿主 dsh 会把整个依赖闭包软链到 `~/.dsh/profiles/node_modules`
> （`healProfilesModuleFallback`，每次启动维护），插件从该 fallback 解析到
> **与宿主完全相同的实例**（cordis / dsh-tools / dsh-scope / dsh-system-prompt 单实例）。
> 若按旧做法在 profile 里 pnpm 装一份 cordis+dsh-tools，进程内会出现**两份
> cordis / dsh-tools 副本**：`Symbol("dsh.scope")` 这类跨模块共享符号错位，
> 作用域解析退化为全局层，会触发
> `prompt section "deployment:persona" is already registered`（standard preset
> 挂载失败，模型选择处报 resume failed）。这是本插件第二次失败的真实根因。

## 后端前置（P0 已完成 ✅）

1. **`POST /api/workflows/import`** — 原子导入 `{name, description, url, parameters,
   nodes, elements}`，temp_id 父引用自动解析，任一步失败整体回滚。
2. **`run/extension` async 模式** — body 带 `async: true` 时立即返回 run_id（容量满
   仍 503）；预写 Result 行，进度走 `runs/{run_id}/log`（新增 `running` 字段）与
   `/run/stream` SSE。

配套：`GET /runs/{run_id}/log` 在运行中返回 `{events, running: true}` 而非 404；
`src/mcp_server/tools/workflow_edit.py` 已加 `import_workflow` 工具（Claude 客户端同享）。

## 配套（非必需）

- **技能**：把仓库 `skills/`（generate-workflow 等 4 个 SKILL.md）拷到
  `~/.dsh/skills/`（DSH `dsh-skill-filesystem` 原生识别该格式），模型即学会
  项目操作惯例。
- **保留 MCP 服务器**：`src/mcp_server/` 继续给 Claude Desktop / Code 用，两者互不干扰。
- **C1–C4（NL→工作流）**：被 DSH 取代，可删除 TODO 中该块。

## 落地路线图

1. ~~**P0 后端接口**~~ ✅ 已完成：`POST /api/workflows/import` + `run/extension` async 模式（含测试 4 个，全量 183 通过）。
2. **P1 插件安装（~1 天）**：`dsh plugin --profile web add file:rpa-dsh-plugin` +
   `cordis.patch.yml` 实例条目（含凭证与 `autoStartBackend`）；跑通
   "打开百度搜索 RPA → 建工作流 → 运行" 端到端。
3. **P2 扩展安装器（1–2 天）**：桌面安装器把扩展拷贝到稳定目录 + 写
   `<User Data>/External Extensions/<id>.json` + 提示重启浏览器；检测
   （复用 `scan_installed_extensions`）与兜底提示（Chrome 版本兼容风险）。
4. **P3 打磨**：skills 入 `~/.dsh/skills/`；可选 headless profile 一条命令跑流程。

## DSH Web UI 集成（client 半身）

插件带 **client 半身**（`lib/client.js`）：在 dsh web 侧边栏底部注册"RPA 控制台"入口，
点击展开右侧抽屉，**iframe 内嵌现有 workflow-editor SPA**（打开时探测 8100-8199 自动发现端口），
不重新写前端。头部提供"新窗口打开"兜底。

机制（DSH client-module 系统）：

- `package.json` 声明 `dsh.client: { platform: "web", inject: ["@deepseek-ai/dsh-client-runtime", "@deepseek-ai/dsh-client-locale"] }`
  + `exports["./client"] → lib/client.js`。dsh 启动扫描到声明后，把该包注入
  `window.__DSH_BOOT__` 入口图，并 serve `/plugins/rpa-dsh-plugin/client.js`。
- `lib/client.js` 是**浏览器直接执行的 bundle**（`window.__ModuleLoader__.load({id, factory})`），
  保持 ES5 风格；`require("react")` 等解析到前端 staticModules（react / react/jsx-runtime /
  react-dom / @deepseek-ai/cordis 等，**无需自己打包**）。
- `factory` 导出 `apply(ctx)` + `inject`（cordis 插件惯例）：`ctx.slots.inject("sidebar.footer.action", ...)`
  注册组件到侧边栏底部（与 cordis-panel 同 slot，不同 id 共存）。

改动后生效（重要）：

```powershell
# 1) 同步到 profile 的两处（workspace 源 + pnpm 安装副本，二者都要）
Copy-Item rpa-dsh-plugin\lib\client.js "$env:USERPROFILE\.dsh\profiles\web\rpa-dsh-plugin\lib\client.js" -Force
Copy-Item rpa-dsh-plugin\lib\client.js "$env:USERPROFILE\.dsh\profiles\web\node_modules\rpa-dsh-plugin\lib\client.js" -Force
Copy-Item rpa-dsh-plugin\package.json "$env:USERPROFILE\.dsh\profiles\web\rpa-dsh-plugin\package.json" -Force
Copy-Item rpa-dsh-plugin\package.json "$env:USERPROFILE\.dsh\profiles\web\node_modules\rpa-dsh-plugin\package.json" -Force
# 2) 重启 dsh web（client 元数据/bundle 变化需重启；页面刷新加载新 bundle）
```

> 注意：loader 实际解析的是 `node_modules/rpa-dsh-plugin`（pnpm 安装副本），
> 只拷 workspace 源会报 `client bundle not found`（`MissingClientBundleError`）。

## 启动失败恢复

如果 `dsh web` 启动崩溃（插件树加载失败），一条命令回到无插件状态：

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.dsh\profiles\web\rollback-rpa.ps1"
```

脚本先备份当前 profile 配置与插件实体到 `~/.dsh/profiles/web-backup-<时间戳>/`，
再把 profile 还原为纯 bundles（清空 `cordis.patch.yml`、移除插件、剪除依赖），
随后重启 `dsh web` 即恢复。备份目录保留出问题的配置，排查时可对照。

## 风险备忘

- **工具参数 schema（dsh-tools 硬性要求）**：`type: "object"` 的参数必须显式声明
  `additionalProperties: true/false`，否则插件树加载直接失败
  （`unsupported JSON schema: <tool>.<param>.additionalProperties must be explicitly true or false`）。
  当前代码已全部合规（`rpa_run_start.parameters / initial_table_data`、
  `rpa_browser_exec.extra` 均带 `additionalProperties: true`）；新增/修改工具时保持。
- **禁止在 profile 里重复安装 cordis 生态包**：只允许 `rpa-dsh-plugin` 一个依赖，
  cordis/dsh-tools/schemastery 由 `~/.dsh/profiles/node_modules` fallback 提供宿主单实例。
  若进程内出现第二份 `@deepseek-ai/cordis` / `@deepseek-ai/dsh-tools` 副本，
  会表现为 standard preset 挂载失败：
  `prompt section "deployment:persona" is already registered (for a per-agent override, ...)`，
  模型选择处报 `resume failed`。恢复：跑 rollback 脚本或把 package.json 的 dependencies
  只留 `rpa-dsh-plugin` 后 `pnpm install`。
- 扩展连接单实例容量 1：运行中 `rpa_browser_exec` 会 409，`allow_during_run=true` 可强制。
- 桌面指令（Win32/UIA）仅 Windows。
- 免认证（本机工具）：默认绑定 127.0.0.1 + 随机端口 + CORS 仅本机 + Host 头校验；
  对外部署设 `RPA_HOST=0.0.0.0`、`RPA_AUTH_DISABLED=0` 并配置强 `SECRET_KEY`。
