# rpa-dsh-plugin

RPA Script 的 DSH 原生工具插件（Cordis v4 格式，纯 ESM，无构建步骤）。

让 DSH 用自然语言**构建 + 运行** RPA 流程：健康检查、按需指令目录、文件式工作流导入、
异步运行控制、浏览器实时指令。直接 fetch 调后端 REST（**不经 MCP 双跳**），认证机制与
`src/mcp_server/client.py` 一致（Bearer token + 401 重登一次）。

## 工具集（12 个）

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
| 认证 | 保持后端登录，**DSH 代管凭证**（token 或 username+password，401 自动重登） |
| 页面 | 独立页面（:8000）+ DSH 内 `/rpa` 跳转，不做 UI 嵌入 |
| NL 生成 | 模型直接产出节点 JSON，C1–C4 向量匹配不做 |
| 扩展安装 | 桌面安装器自动注入（External Extensions JSON） |

## 与现有桌面版（Electron）共存

桌面版（`desktop/main.js`）不 spawn 后端，只探测 :8000 就绪后加载同一个
`/workflow-editor/` SPA。因此本插件采用 **adopt-don't-own** 生命周期策略：

- 后端已在跑（含桌面版用户手动起的）→ 接管（adopt），**不 spawn、dispose 不回收**
- 未就绪且开启 `autoStartBackend` → 本插件 spawn 并标记 owned，dispose 时
  taskkill 整棵进程树回收
- 端口被非本项目进程占用 → 仅告警

效果：**桌面版零改动、功能零影响**；反而省掉"手动起后端"步骤（DSH 开着即可）。
唯一注意：DSH 与桌面版共享同一后端实例 → 容量锁（`MAX_CONCURRENT_WORKFLOWS`）、
认证、SQLite 全部共享，与"并行后置"的决策一致。

产品分工变化：桌面版保留"人工编辑/执行"角色；NL 生成入口（TODO C4）由 DSH 承担，C1–C4 可删。

## 安装（web profile）

> 实测要点：① 路径必须带 `./`（`file:./`），否则 dsh plugin 的锚定正则不匹配，
> pnpm 会按 profile 目录解析；② 跨盘符的 `link:`/`file:` 绝对路径会被 pnpm 拼错
> （URL 解析把 `D:` 当 host），且软链会让 Node 按真实路径找依赖 —— 因此推荐
> **把插件实体拷进 profile 目录**再 `file:./` 引用。

```powershell
# 1) 把插件拷进 profile（保持与仓库同步：改动后重新拷贝即可）
Copy-Item rpa-dsh-plugin "$env:USERPROFILE\.dsh\profiles\web\rpa-dsh-plugin" -Recurse

# 2) 声明依赖（peer 显式声明，保证与宿主单一实例）
#    编辑 %USERPROFILE%\.dsh\profiles\web\package.json 的 dependencies 加入：
#      "@deepseek-ai/cordis": "^4.0.1",
#      "@deepseek-ai/dsh-tools": "^0.1.0-rc.6",
#      "rpa-dsh-plugin": "file:./rpa-dsh-plugin"

# 3) 安装
cd "$env:USERPROFILE\.dsh\profiles\web"; pnpm install
```

然后编辑 `%USERPROFILE%\.dsh\profiles\web\cordis.patch.yml`，**新增实例必须用 `insert:`**
（普通 `id` 条目是"修改已有行"，id 不存在会被跳过）：

```yaml
- insert:
    - id: rpa
      name: rpa-dsh-plugin
      config:
        backendUrl: http://127.0.0.1:8000
        token: !!js process.env.RPA_API_TOKEN || ''
        username: !!js process.env.RPA_USERNAME || 'admin'
        password: !!js process.env.RPA_PASSWORD || 'admin123'
        # 可选：激活时自动拉起后端
        autoStartBackend: false
        backendCommand: '"D:\Users\Administrator\Documents\代码\rpa_script\.venv\Scripts\python.exe" -m src.runtime.main'
        backendCwd: 'D:\Users\Administrator\Documents\代码\rpa_script'
```

验证（不起服务即可检查配置树）：`dsh --profile web --dump-config | findstr rpa`。
然后**重启 `dsh web`** 激活插件。

headless 同样可用：首次使用会自动初始化 profile，按同样步骤把实例加到
`~/.dsh/profiles/headless/cordis.patch.yml`，然后一条命令端到端：

```bash
dsh --profile headless "打开百度，搜索 RPA，把第一页标题存成工作流并运行"
```

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

## 风险备忘

- 扩展连接单实例容量 1：运行中 `rpa_browser_exec` 会 409，`allow_during_run=true` 可强制。
- 桌面指令（Win32/UIA）仅 Windows。
- 认证默认种子 `admin/admin123`，首次使用请改。
