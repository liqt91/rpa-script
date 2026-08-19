# 统一捕获层改造 + 独立捕获服务 实施计划（v2 · DSH 插件语境）

> v2 变更：按 DSH 插件化诉求重盘——一目录一流程（`rpa.json` 标记）、流程编辑器
> DSH 托管只读写本目录、后端资源管理功能搁置、捕获是独立重模块、入口走 DSH 最短路径。
> v1（Electron 语境）的 resolver 链设计不变，入口与写回路径重做。

---

## 1. 诉求对齐后的设计取舍

| 诉求 | 对方案的影响 |
|---|---|
| ① 一目录一流程，编辑器 DSH 托管、只读写本目录 | **捕获结果直接写工作区目录**（`workflow.json` 的 `elements[]` + `images/`），不经后端、不进 SQLite。`project_router.py:project_save_element` 的目录化写回逻辑搬到捕获服务内（`normalize_element_capture` 是纯函数可直接 import） |
| ② 后端精简（资源管理搁置） | 后端收缩为四个角色：**扩展 WS 枢纽**、指令目录、运行引擎、**capture 转发**（resolveAtPoint 中继）。捕获写回、元素库 IO 全部移出后端 |
| ③ 捕获是独立重模块，入口走 DSH 最短路径 | 捕获服务独立进程；入口见 §3（agent 工具为主、抽屉按钮为辅、全局热键可选） |
| ④ 指令体系不动 | 本计划零触碰 `src/runtime/commands/` |

## 2. 目标架构

```
┌─ DSH 宿主进程 ──────────────────────────────────────────────┐
│ rpa-dsh-plugin server 半（lib/index.js）                     │
│   新工具 rpa_capture ──┐  agent 语境调起（"帮我捕获xx按钮"） │
│                        │  spawn（P0）/ HTTP（P3 常驻化）     │
│ client 半（lib/client.js）│  抽屉「捕获元素」按钮            │
└────────────────────────┼─────────────────────────────────────┘
                         │ {workspace: <当前工作区目录>}
┌────────────────────────▼─────────────────────────────────────┐
│ 捕获进程（独立 Python 进程，DSH 宿主 spawn）                  │
│   P0: 每次 spawn 现有 capture_once.py 模式（零新服务）        │
│   P3: 可选常驻化 server.py（127.0.0.1:8765，条件见 §4.1）     │
│   ・遮罩 + 钩子常驻（无模式切换，按帧路由 resolver）           │
│   ・resolver 链: ①扩展DOM → ②UIA web → ③UIA → ④Win32         │
│   ・结果写回: workflow.json elements[] + images/ + 剪贴板      │
│   ・toast 反馈（"已保存 登录按钮 → <工作区名>"）               │
└──────────────┬───────────────────────────────────────────────┘
               │ 仅 web DOM 解析时 HTTP（resolve-at-point）
┌──────────────▼────────────┐   WS（现有通道）  ┌──────────────┐
│ 精简后端 :81xx             │◄────────────────►│ 浏览器扩展    │
│ 扩展 WS 枢纽 + 指令运行时  │  resolveAtPoint  │ content 脚本  │
└───────────────────────────┘                  └──────────────┘
```

**进程模型决策（v2.1 修正）**：捕获 GUI 是 Python + Win32 消息泵，跑不进 DSH 宿主的
Node 进程，所以独立进程省不掉；但**常驻服务不是必须的**——入口收敛到 DSH 后，
agent 工具/斜杠命令都跑在插件 server 半身（Node），它可以直接 spawn 现有的
`capture_once.py`。常驻服务推迟到三个触发条件任一成立时再做（§4.1），届时只是把
同一套捕获代码包一层 HTTP 壳，前期工作零浪费。不选"塞进主后端线程"：钩子/遮罩
崩溃会带崩运行引擎，且违背"捕获是独立模块"的诉求。

与 v1 的本质差异：**写回不再回后端**（资源管理已搁置），捕获服务直接落盘工作区
目录——这恰好与"编辑器只读写本目录文件"同构，捕获服务和编辑器之间零耦合，
编辑器重新读目录即看到新元素。

核心不变量（沿用 v1）：

1. 手势层与解析层解耦：遮罩+钩子常驻，**钩子只在按住 Alt 时吞点击**，普通点击放行
   （可先点开下拉框再捕获）；Esc/取消统一在 Python 侧。
2. 没有"网页模式/桌面模式"状态机——每帧按光标坐标选 resolver，
   `BackToDesktop`/`leaveExitTimer`/`viewport_watch`/`session_holder` 整套删除。
3. 高亮统一由遮罩绘制；hover 与点击确认走同一条 resolver 链（所见即所得）。
4. 解析失败逐层降级（扩展离线/受限页 → UIA web 静默接管），用户无感。

## 3. 入口设计（DSH 最短路径）

| 入口 | 路径 | 直觉性评估 |
|---|---|---|
| **agent 工具 `rpa_capture`**（主） | 用户在 DSH 对话里说"捕获这个页面的登录按钮" → 模型调工具（workspace=当前会话目录，DSH 天然携带）→ 弹遮罩 → 结果自动入库 → 模型回报 | 最 DSH-native；还能编排：先 `rpa_browser_navigate` 打开页面再捕获 |
| **抽屉按钮**（辅） | client 半身在侧边栏 ⚙ 抽屉加「捕获元素」按钮。**P0：单击 = `session.prompt()` 代发消息**（`ISession.prompt` 官方 API，固定模板文案让模型调 `rpa_capture`；零新通道、工作区上下文天然正确；代价是一次 LLM 往返几秒 + 会话留痕）。**P3 常驻化后：单击改直连 fetch 捕获服务**（确定性、秒级；工作区路径由 client runtime `ctx.workspaces` + `resolveWorkspacePath` 解析），代发消息降级为次级入口"让 AI 帮我捕获" | 可视化发现入口；P0 形态即可落地，P3 后体验升级 |
| **全局热键**（可选，P4） | 捕获服务注册 `Ctrl+Alt+E`，任何界面按下即捕 | 路径最短但"当前工作区"需推断（用最近一次 DSH 调用的工作区，toast 里明示落在哪） |
| ~~流程 tab 网页调起~~ | 保留兼容（编辑器内按钮 → 捕获服务），不再是主路径 | v1 方案，降级为兼容层 |

**写回协议（v2.2 修正：写 `elements.json`，不碰 `workflow.json`）**：请求带
`workspace`（绝对路径，须含 `rpa.json`，复用 `_project_root` 校验逻辑）；
服务把元素追加进 **`elements.json`**（同名替换，原子写），截图落 `images/<name>.png`。
元素命名：默认自动生成（tag+文本摘要），toast 展示；命名对话窗后置（P4 打磨项）。

**为什么写 `elements.json`**：竞态的本质是"两个写者碰同一个文件"。编辑器对
`workflow.json` 是整文档读-改-写（`WorkflowContext.jsx:894`），捕获写进去的元素
会被编辑器下次保存用旧内存副本覆盖。拆文件后写入域分离——`workflow.json` 只有
编辑器写（流程定义，高频），`elements.json` 捕获服务为主写者（机器产物，追加式），
竞态被工程性消除，无需编辑器整文档合并逻辑。`elements.json` 本就在读写白名单里
（预留未用），此举是启用其本意。配套：编辑器与运行器的元素读取改为
"`elements.json` 优先 + `workflow.json` 遗留元素合并"（向后兼容，不强制迁移）。

**工作区目录结构（已实证）**：

```
<流程目录>/                 ← 含 rpa.json 即 RPA 工作区（插件/后端/编辑器三方同一约定）
├── rpa.json                ← 标记 {name, version:1, created_at}（rpa_project_create 幂等生成）
├── workflow.json           ← 流程定义：{name, description, url, parameters[], nodes[]}
│                              （legacy: 老项目元素可能还在其 elements[] 内，读取时合并）
├── elements.json           ← 元素库（本方案启用：捕获写回的唯一落点）
├── images/<元素名>.png     ← 元素截图；entry.image 存相对路径
├── data.json               ← 数据表格（DataTableTab）
└── run_logs/<wf_id>/<run_id>/run.log   ← wf_id = sha1(目录路径)前8位hex→int
```

编辑器项目模式读写 `workflow.json`（`WorkflowContext.jsx:577/894`），元素 entry
结构与 `project_save_element` 一致——**捕获写回格式无需再验证**。
读写通道：DSH web `:3080` `/rpa-bridge/project/read|write`（Node fs 代理，编辑免
后端）与后端 `/api/projects/*` 等价并存；捕获服务走直写文件即可。

## 4. 改动清单

### 4.1 捕获进程（P0 spawn 现有入口；常驻服务 P3 可选）

**P0（不新起服务）**：`capture_once.py` 增加 `--workspace <目录>` 参数，捕获完成后
就地写回 `workflow.json` + `images/` 再输出 JSON；插件工具 spawn 它并透传工作区。
冷启动 +1~3s/次，换取零新组件。

**P3（可选常驻化，`scripts/capture_gui/server.py`）**，触发条件（任一成立才做）：
① 冷启动体感不可接受；② 要做抽屉按钮直连 API；③ 要做全局热键。

**进程归属决策：独立进程，不合入 RPA 后端。** 理由：全局鼠标钩子挂在系统输入
链路上（回调阻塞=全机鼠标冻结，项目已有此类实战记录），是全系统故障率最高的
组件；合入后端则捕获侧崩溃会带崩正在跑流程的运行引擎，且与"后端精简"方向
相悖。独立进程把最坏情况收敛为"捕获失败重试"。成本通过惰性拉起（首次捕获请求
到达才 spawn）+ adopt-don't-own + 端口文件发现压到近零。通信保持 HTTP 而非
stdio——同时覆盖 DSH 宿主调用、抽屉按钮直连、未来独立打包（tdSelector 式 exe）。

| 端点 | 说明 |
|---|---|
| `GET  /api/capture/status` | `{ready, extOnline, backendOnline, browsers[], version}` |
| `POST /api/capture/once`   | `{workspace, mode:"unified", timeout}` → 阻塞至捕获/取消/超时 → 返回元素 JSON 并**同步写回工作区** |
| `POST /api/capture/cancel` | 取消当前会话（供调用方按钮） |
| `GET  /api/capture/hover`  | 当前悬停元素摘要（调用方画自己的悬浮窗用） |
| `POST /api/capture/verify` | flash_element 进程内化（替代 spawn verify_once） |

- stdlib `http.server` 线程模式（捕获主循环要跑消息泵，不引 FastAPI 依赖，
  服务可脱离后端独立存活）；
- 绑定 127.0.0.1，端口 `RPA_CAPTURE_PORT` 默认 8765，被占顺延并写
  `%USERPROFILE%\.rpa_script\capture_port` 供发现；
- **免 token**（与后端既有决策一致：本机单人工具）：CORS 白名单仅回环 origin
  （`http://127.0.0.1:3080` DSH GUI / 81xx 后端 / 8765 自身）+ Host 头校验。
  原 token 方案废弃——token 在磁盘文件里，浏览器侧的抽屉按钮读不到，bootstrap 不通；
- 写回直接复用 `src/service/elements_service.py:normalize_element_capture`
  （纯函数）+ `project_router.py` 的 `_persist_element_screenshot` 等价逻辑
  （抽到 `scripts/capture_gui/store.py` 共享，避免 import runtime 层路由代码）；
- 进程拉起：插件 server 半身激活时探测 `/status`，未跑则 spawn
  （adopt-don't-own，与后端同策略）；开发期 `python scripts/capture_gui/server.py`。

### 4.2 插件（`rpa-dsh-plugin/`）

**server 半身 `lib/index.js`**：
- 新工具 `rpa_capture({mode?, timeout?})`：P0 → spawn `capture_once.py --workspace
  <当前会话工作区>` 并等 JSON 输出；P3 常驻化后 → 发现捕获端口 `POST /once`。
  工具描述写明"用户要求捕获/拾取界面元素时调用，结果自动入库当前工作区"。
- schema 合规红线：`object` 参数必须显式 `additionalProperties`（README 风险备忘）。

**client 半身 `lib/client.js`**：
- 抽屉工具栏加「捕获元素」按钮 → 经 server 半身或直接 HTTP 调捕获服务；
  捕获中按钮变「取消」（调 `/cancel`）。
- 改动后须同步两处 profile 副本并重启 `dsh web`（README 已记录该机制）。

### 4.3 后端（`src/runtime/`，只做加法）

- 新增 `POST /api/extension/resolve-at-point`：`{x,y,browser}` → future 转发扩展 →
  2s 超时。写法和 `_gui_capture_futs` 同构。
- **不删**任何资源管理代码（诉求②是搁置）；仅把 `commands_router.py:/gui-picker`
  改为薄代理转发捕获服务（旧调用方零改动，过渡期保留 spawn 回退，P3 删）。
- 层级自检：改动限于 runtime 层，`npm run harness:check` 须过。

### 4.4 扩展端（`extension/`）

**`content_capture.js`**：
- 新增 `resolveAtPoint` 处理器（纯查询，不动捕获状态）：
  `elementsFromPoint` → `resolveCaptureTarget`（SVG/use 规则复用）→
  finder 打分/候选/list 检测 → 返回 `{found, rect, css, xpath, candidates, attrs,
  domPath, name, innerText, listFamily}`；
- iframe 递归：命中 iframe 时按 `getBoundingClientRect` 偏移换算后经 background
  转发子 frame 二次命中（rect 逐帧累加偏移，返回顶层 viewport 坐标）；
- **P3 删除**：捕获模式 DOM 事件组、`onCaptureMouseLeave`、`leaveExitTimer`、
  `webOnlyCapture`、`finishGuiCapture`、页内 highlight canvas、`launchBrowserCapture`。

**`background_base.js`**：
- 新增 `resolveAtPoint` 转发：复用 `verifySelector`（:354）的可见 tab 筛选
  选目标 tab → `sendMessage` → 回传 `resolveAtPointResult`；
- **P3 删除**：`launchBrowserCapture`/`exitBrowserCapture`/`guiCapture` 会话管理。

### 4.5 编辑器 + 运行器（elements.json 读取合并，P0 必做）

- **编辑器**（`WorkflowContext.jsx`）：项目模式元素加载改为
  `elements.json` 优先 + `workflow.json` 遗留 `elements[]` 合并（legacy fallback，
  不强制迁移）；元素的增删改（重命名/编辑选择器/删除）保存到 `elements.json`
  （读最新盘→改→原子写），`workflow.json` 保存不再携带 `elements` 字段；
- **运行器**（`extension_runner.load_project_workflow` / `project_router.run_project_extension`）：
  元素来源同样改为合并读取，保证"捕获入库即可运行"；
- **后端 `project_save_element`**（兼容层）：写入目标改 `elements.json`（与捕获服务一致）。

### 4.6 捕获层重构（`scripts/capture_gui/`）

- **新增 `resolvers.py`**：
  ```python
  CHAIN = [WebDomResolver(),   # 扩展在线 + 光标在渲染宿主内容框（overlay._browser_viewport）
           UiaWebResolver(),   # 包装 overlay._uia_web_capture
           UiaResolver(),      # 包装 _try_uia_capture / hover worker 结果
           Win32Resolver()]    # 兜底
  ```
  `WebDomResolver`：屏幕坐标 → viewport CSS px（内容框原点 + DPR，
  `overlay.py:2128` 现有换算）→ 调后端 resolve-at-point → rect 映回屏幕 →
  组装 ElementInfo（抽出 `_capture_via_extension` :2370-2410 的组装逻辑共用）；
- **`overlay_mask.py` 主循环改造**：删 `session_holder`/`_cursor_in_viewport`/
  网页会话双路路由；hover 与 Alt+点击统一走 CHAIN；钩子改"仅 Alt 吞"；
- **`overlay.py`**：`_web_capture_target`/`_browser_viewport`/`_uia_web_capture`
  抽为公共件；P3 删 `_capture_via_extension`/`BackToDesktop`/`run_capture` web 分支/
  `ws_client.py`。

## 5. 分阶段实施

| 阶段 | 内容 | 验收 |
|---|---|---|
| **P0** 入口+写回（不新起服务） | `capture_once.py` 加 `--workspace` 写回 **`elements.json`**；编辑器+运行器改合并读取（§4.5）；插件注册 `rpa_capture` 工具（spawn 透传工作区）；抽屉按钮先做"让 AI 帮我捕获"（`session.prompt` 代发，零新通道） | 在 DSH 对话里说"捕获xx元素"端到端跑通，元素出现在工作区 `elements.json` 且编辑器元素 tab/运行器可见 |
| **P1** resolver 链 | `resolvers.py`（②③④），遮罩主循环按帧路由；web 暂留旧 `_capture_via_extension` 分支 | 桌面捕获回归；hover 高亮=点击结果 |
| **P2** WebDomResolver | 扩展 `resolveAtPoint` + 后端中继 + 链接入①；钩子仅 Alt 吞 | 浏览器⇄桌面滑动零切换感；受限页落②；多浏览器/多屏/150% DPI 抽查 |
| **P3** 清理 + 常驻化决策 | 删 v1 遗留；按 §4.1 触发条件决定是否把 spawn 换成常驻 `server.py`（若做：抽屉按钮单击切直连 API、二次捕获 <200ms、具备热键前提） | grep 无残留；`harness:check` 通过 |
| **P4** 打磨 | 全局热键（依赖 P3 常驻化）、命名小窗、verify 端点 | 热键捕获落盘正确工作区 |

每阶段：`npm run harness:check` + `pytest src/runtime/tests/test_capture_*`；
对应 feature_list 条目端到端过后再置 `passes: true`。

## 6. 测试矩阵（P2 重点）

- 浏览器：Chrome / Edge（水平+垂直标签页）/ Firefox（无渲染宿主启发式）
- 页面：普通 / iframe 嵌套 / shadow DOM / chrome:// 受限页 / PDF / 新标签页
- 环境：多显示器、DPI 100%/150%、提权目标（UIPI）、慢 XAML 应用（Terminal）
- 手势：Alt+点击 / 普通点击放行 / Esc / API 取消 / 捕获中切标签页 / 扩展重载
- DSH 集成：工作区无 `rpa.json` 报错路径、同名元素替换、写回后编辑器刷新可见

## 7. 风险与对策

| 风险 | 对策 |
|---|---|
| resolveAtPoint 往返延迟 | 节流 30~50ms、光标移动作废在途请求、200ms 降级② |
| ~~编辑器整文档读-改-写覆盖捕获元素~~ | **已由 elements.json 拆分消除**（§3 写回协议：捕获服务是 elements.json 主写者，完全不碰 workflow.json）。剩余小窗口：用户正编辑元素属性的同时捕获新元素 → elements.json 读-改-写毫秒级窗口 + 原子写兜底，可接受；编辑器元素保存仍走"读最新盘→改→原子写" |
| 主后端不在 → 无 web DOM 解析 | 降级②；status 暴露 `extOnline` 供入口提示"装扩展获得精准选择器" |
| 工作区路径来源不可靠 | server 半身从 DSH 会话上下文取；全局热键用"最近工作区"+toast 明示 |
| 端口冲突 | 8765 顺延 + 端口文件发现（同后端 `data/backend.port` 惯例） |
| 扩展 context invalidated | resolver 异常当帧降级②；`_extension_online` 2s 缓存心跳 |

## 8. 待确认决策点

1. ~~**写回格式**~~ ✅ 已闭环（§3 工作区结构实证）。
2. ~~**编辑器覆盖竞态**~~ ✅ 已由 elements.json 拆分消除（§3 写回协议 v2.2）。
3. **元素命名**：自动生成+toast（推荐，路径最短）还是弹命名小窗？
4. **全局热键**是否要做（P4 可选，依赖 P3 常驻化），快捷键位偏好。
