---
name: new-command
description: 创建新的 RPA 指令（command），包括 JSON 定义、handler 代码生成和注册验证。四类指令：extension（扩展端）、backend（本地执行）、desktop（桌面操作）、control（控制流）。
---

# 新增指令开发流程

> **本 skill 的首要目标是"源头防错"**：按标准生成，生成后必跑质量门禁自检，
> 避免把规范问题留给事后逐一排查。**新增/修改指令的每一步都必须对照
> 「生成质量标准」与「生成后自检」执行。**

## 0. 生成质量标准（源头防错 · 硬性）

生成 instruction 定义或实现代码时，必须同时满足以下全部。任何一条不满足都不算完成。

### 0.1 JSON 定义规范

```
□ cmd        非空、camelCase（小写开头驼峰，如 clickElement / deepseekChat），
            且与文件名一致（xxx.json → cmd: "xxx"）
□ label      非空、中文显示名
□ runtime    必须是 "extension" | "backend" | "control"
□ params     数组，可为空；每个 param 至少有 name/label/type
□ handler.kind 必须是 "extension" | "backend" | "control"，且与 runtime 相等
□ handler.source 指向的目录与 kind 一致：
  extension → src/runtime/commands/extension_commands/
  backend   → src/runtime/commands/backend_commands/ 或 desktop_commands/
  control   → src/runtime/commands/control_commands/
□ category（中文分组名）与 categories（slug 数组）都填，二者对应
```

### 0.2 Python handler 规范（backend/desktop/control）

```
□ 文件含 @register_handler(...) 装饰器，cmd/label/category/runtime/icon 与 JSON 一致
□ params 列表每个 Param 的 name/label/type 与 JSON params[].name 一一对应
□ 必须有 async def execute(runner, cmd_type, step_id, instr)
□ 读取参数统一用 extra.get("paramName")（参数名与 JSON params[].name 完全一致）
□ execute 成功路径必须：
    runner.completed += 1
    runner.vars[输出变量] = 结果        # 若有输出变量
    runner.results.append({...})        # 结构化结果
    await runner._emit({"type": "stepComplete", ...})
□ 不得残留 AUTO-GENERATED 哨兵注释（手写文件不该有）
□ 声明支持 {{变量}} 的 string/text/str-var 参数，execute 里必须 resolve_vars(...)
```

### 0.3 变量支持约定

- **`{{变量}}` 引用**：string/text/str-var 参数若 placeholder 或 description 里写了
  `{{变量}}`，则 execute 读取该参数时**必须**用 `resolve_vars(str(extra.get("x") or ""), runner.vars)`。
- **`str-var` 输出**：读取用 `clean_var_ref(...)` 去掉引用残渣，写回 `runner.vars[name] = value`。

### 0.4 结果上报约定（运行日志可见）

- 成功 → `runner.completed += 1` + `runner.results.append({...})` + `await runner._emit({"type":"stepComplete", ...})`
- 失败 → 抛异常（runner 会捕获转 stepError），或 `await runner._emit({"type":"stepError", "error": ...})`
- **每个指令务必提供 `summary_tpl`**（如 `"{filePath} → PDF"`），否则运行日志只显示指令名。

## 1. 生成后必跑自检（质量门禁）

**新增或修改任何指令后，必须运行质量门禁脚本，直到全部通过。**

```bash
# 单个/多个指令（推荐——严格管你生成的指令）
python skills/scripts/check_command_quality.py <cmd> [<cmd2> ...]
# 全量扫描（看存量趋势，不阻断：存量有历史格式差异）
python skills/scripts/check_command_quality.py --all
```

规则覆盖：`def_required / def_fields / impl_exists / reg_params / extra_refs /
resolve_vars / sentinel / execute / emit / summary_tpl`。全绿才算完成。

> **单查 vs 全量**：以 `--all` 或单查都能用，但**门禁判定以单查为准**（你要管的是
> 自己生成的指令）。`--all` 会把 repo 里历史遗留的指令标红（旧 handler 格式 / 无
> source / control 容器无 execute 等），这些是存量差异，不是本次生成的问题。

## 2. 推荐执行路径（确定性命令 + LLM 分工）

现代流程建议直接用 `rpa_new_command` 命令编排（确定性动作零 LLM）：

```
给 definition（JSON 对象）→ rpa_new_command 命令：
  ① 写 commands/<cmd>.json
  ② 跑 generate_commands.py 生成桩（extension → py + js）
  ③ 跑 build_content_js.py 拼装 content.js
  ④ 校验注册
```

- **确定性动作**（写文件、跑脚本、落盘、校验）→ 命令 `rpa_new_command`，零 LLM。
- **LLM 只介入两点**：自然语言→JSON 定义、写 `execute()`/JS 回调业务逻辑。
- 之后仍要跑上面的质量门禁自检（命令只管"生成+构建"，不管"质量规范"）。

## 四类指令

| 类型 | 目录 | Python | JS |
|---|---|---|---|
| **extension** | `src/runtime/commands/extension_commands/` | 注册桩（`@register_handler` + `Param`） | `extension/dom_handlers_new/<type>.js` handler 函数 |
| **backend** | `src/runtime/commands/backend_commands/` | 含 `execute()` 实现 | 无 |
| **desktop** | `src/runtime/commands/desktop_commands/` | 含 `execute()`，调 Win32 / UIA API | 无 |
| **control** | `src/runtime/commands/control_commands/` | 含 `execute()` 控制流逻辑 | 无 |

> desktop 在 JSON 中 `runtime` 设为 `"backend"`，`handler.source` 指向 `desktop_commands/` 目录。它是 backend 的子类，因涉及桌面 API 而独立目录。

## 开发流程

### 硬性约束

```
commands/<type>.json（唯一事实来源）
       │
       ▼
python scripts/generate_commands.py   ← 必须运行
       │
       ▼
在生成的桩文件基础上添加实现逻辑
       │
       ▼
python scripts/build_content_js.py    ← extension 指令必须运行
       │
       ▼
重启服务器 → auto_register() 加载 → 验证
```

> **禁止直接创建 handler 文件而不先建 JSON。禁止修改 JSON 后不运行 generate_commands.py。**

## 生成指令步骤（总览，快速走一遍）
1. 定 `runtime` / `handler.kind` / 目标目录（判断标准见「四类指令」）。
2. 定 `cmd`（小驼峰，= JSON 文件名）。
3. 定参数 Schema + 数据流向 + 分类 slug（见「生成前必须确认的输入知识」）。
4. 写 `commands/<cmd>.json`（唯一事实来源；`handler.source` 指向 `src/runtime/commands/<目录>/<cmd>.py`）。
5. `python scripts/generate_commands.py` → 生成 extension 桩（会被覆盖）/ backend 脚手架（首次生成一次，此后 KEEP）。
6. 填实现：backend/desktop/control 在脚手架的 `execute()` 里写；extension 编辑 `extension/dom_handlers_new/<cmd>.js`。
7. （仅 extension）`python scripts/build_content_js.py`。
8. 注册：重启服务器 `auto_register()`，或 `POST /api/commands/reload` 热加载。
9. 验证：`POST /api/commands/validate`（应 PASSED）+ `sync-check`；`get_handler(cmd)` / `load_new_catalog()` 确认；用 mock 跑 `execute()` 校验数据流与错误分支。
10. 入库：启动/重载时 `seed_commands_to_db()` upsert，编辑器指令面板可见。

> 每一步能碰/不能碰的文件，以及 glob 收窄规则，见 `## 0. 工作区文件发现与排除` 与 `## 文件边界`。

## 0. 工作区文件发现与排除（必读，防 glob 超时）

### glob 超时根因
本仓库根目录内嵌多棵**巨大且被 `.gitignore` 忽略**的目录树：`.venv/`（约 1.8 万文件）、`src/`（约 1.1 万，含 `__pycache__` 与 workflow-editor 构建产物）、`webrpa/`（第三方整仓）、`dist/`、`build/`、`tdSelector_1.2.7/` 等。harness 的 `glob` **不读 `.gitignore`**，只排除 `.git` 这类 VCS 元数据目录，且默认以工作区根为起点做整树遍历 → 即便是 `commands/*.json` 这种带"/"的 pattern 也会先全树扫一遍再过滤 → 30s 超时。`Get-ChildItem -Recurse` 做全树统计同理会超时。

### 规则
- **用 `glob` 必须显式传 `path` 收窄到目标目录**（`path` = 只遍历该子树的开关）：
  - `glob(path:"<repo>/commands", pattern:"*.json")`
  - `glob(path:"<repo>/src/runtime/commands/backend_commands", pattern:"*.py")`
  - 已验证：`path=commands` + `*.json` 即时返回 71 个文件；同一 pattern 不带 `path` 则 30s 超时。
- **禁止**无 `path` 的裸 glob（如 `glob("commands/*.json")`、`glob("**/categories.json")`）。
- 不确定目标目录时，用 `pwsh Get-ChildItem -LiteralPath <绝对路径> -Filter <pattern>`（只给目标目录，勿 `-Recurse`）。
- 全程不要对工作区做 `-Recurse` 全树枚举/统计；找命令目录直接用 `commands/`、`src/runtime/commands/*_commands/` 这类已知定点。

## 生成前必须确认的输入知识
动手前先确认以下各项，缺一项就先补一项：
1. `runtime` + `handler.kind` + 目标包目录。判断：调 Win32/UIA → `desktop_commands/`（runtime 仍写 `"backend"`）；纯 Python → `backend_commands/`；结构控制流 → `control_commands/`；浏览器/页面 → `extension`。
2. 指令名 `cmd`（小驼峰，与 JSON 文件名一致）。
3. 参数 Schema：每个参数 `name/label/type/required/default/group/options/description/placeholder`。type 用表内值（`string/text/select/number/int-number/boolean/str-var/element`），**勿用 `str-dropdown/bool-check`**；group 用 `主属性/advanced/output/input/anchor`。
4. 参数数据流向：哪些进 `extra.get("paramName")`，哪些写回 `runner.vars[...]` / `runner.results[].result`。参考同类 handler（backend 看 `setVar.py`/`log.py`，extension 看 `clickElement.js`/`inputElement.js`）。
5. 分类：slug→中文名映射在 `src/runtime/commands/types/categories.json`；需新分类先补该文件（含 `icon`/`sortOrder`），命令 JSON 里 `category` 写中文、`categories` 写 slug。
6. 验证门禁：`generate_commands.py` → `auto_register()` 注册 → `validate()` 0 错 → `new_catalog.load_new_catalog()` 收录 → 经 `/api/commands/reload` 或重启同步进 DB。

## 文件边界
### 可写 / 应生成
- `commands/<cmd>.json` —— 唯一事实来源，新增指令必建。
- `src/runtime/commands/<dir>/<cmd>.py` —— backend/desktop/control 脚手架（首建后 KEEP，只改 `execute()` 实现）。
- `extension/dom_handlers_new/<cmd>.js` —— 仅 extension。
- `src/runtime/commands/types/categories.json` —— 仅当新增分类 slug。

### 生成期勿碰（由脚本/构建接管）
- extension Python 桩 `src/runtime/commands/extension_commands/<cmd>.py`：带 `DO NOT EDIT` 哨兵，每次运行被覆盖。
- `extension/content.js`、`extension/background.js`：编译产物，由 `build_content_js.py`/构建脚本重生成。
- `src/runtime/static/workflow-editor/`、`src/ui/runtime/static/workflow-editor/`、`src/ui/server/static/workflow-editor/`：vite 产物。

### 绝对不碰（大/敏感/产物）
`webrpa/`、`WebRPA/`、`.venv/`、`node_modules/`、`dist/`、`build/`、`tdSelector_1.2.7/`、`rpa-dsh-plugin/python/`、`data/*`（数据库/运行数据/图片/捕获元素）、`tmp/`、`temp/`、`__pycache__/`、`*.pyc`、`.env`（密钥，不读入对话也不提交）、`.private/`、`.harness/`（会话状态）、`server.log`、`@AutomationLog.txt`、`rpa_uia_debug.log`。

### 1. 创建 JSON 定义

在 `commands/<type>.json` 创建指令定义：

```json
{
  "cmd": "myCommand",
  "label": "我的指令",
  "runtime": "backend",
  "category": "分类名",
  "icon": "fa-cog",
  "iconColor": "text-blue-500",
  "bgColor": "bg-blue-50",
  "categoryOrder": 50,
  "commandOrder": 10,
  "description": "指令描述",
  "enabled": true,
  "isNew": true,
  "params": [
    {"name": "paramName", "label": "参数显示名", "type": "string", "required": true}
  ],
  "handler": {
    "kind": "backend",
    "source": "src/runtime/commands/backend_commands/myCommand.py"
  }
}
```

**handler.kind 取值：**
- `extension` — JS handler。有 `function` → delegate 一行转发；有 `source` → 复制 JS 文件
- `backend` — Python handler。**缺文件时脚本生成脚手架**（含 `@register_handler` + `params` + `execute` 骨架）；已存在则 KEEP 不覆盖
- `control` — 结构指令（容器/分支）由 emitter 展开、脚本 SKIP；非结构 control 缺文件时同样生成脚手架

**runtime 取值：**

| runtime | handler.kind | 生成行为 | 文件目录 |
|---|---|---|---|
| `"extension"` | `"extension"` | 生成 Python 桩 + JS | `extension_commands/` + `dom_handlers_new/` |
| `"backend"` | `"backend"` | 缺文件→生成脚手架；存在→KEEP | `backend_commands/` 或 `desktop_commands/` |
| `"control"` | `"control"` | 结构指令 SKIP；非结构缺文件→脚手架 | `control_commands/` |

> desktop 指令 `runtime` 用 `"backend"`，但 `handler.source` 指向 `desktop_commands/`。
> 判断标准：调用了 Win32 / UIA API → `desktop_commands/`；纯 Python 逻辑 → `backend_commands/`。
> `handler.source` 必须指向 `src/runtime/commands/<目录>/<cmd>.py`，脚手架才会落到正确目录；该树之外或陈旧路径会回退到 runtime 目录。

**字段类型参考（JSON `params[].type` 和 Python `Param("name", ..., "type")` 使用相同的值）：**

| 类型 | 说明 | 示例 |
|---|---|---|
| `select` | 下拉选择（需配 `options`） | `"type": "select"` |
| `string` | 单行文本输入 | `"type": "string"` |
| `text` | 多行文本输入 | `"type": "text"` |
| `boolean` | 复选框 | `"type": "boolean"` |
| `number` | 数字输入 | `"type": "number"` |
| `int-number` | 整数输入 | `"type": "int-number"` |
| `str-var` | 变量引用（支持 `{{var}}` 语法） | `"type": "str-var"` |
| `element` | 元素选择器（已捕获的页面元素） | `"type": "element"` |

> **注意：** 不要使用 `str-dropdown`、`bool-check` 等名称。

**字段分组（`group`）：** `主属性`（默认）、`advanced`（高级）、`output`（输出）、`input`（输入）、`anchor`

### 2. 运行 generate_commands.py 生成桩代码

```bash
python scripts/generate_commands.py
```

**哨兵注释 / 脚手架标记：** 脚本生成的文件首部带标记，行为随类别不同：

- **extension 桩**（标记 `# AUTO-GENERATED from commands/xxx.json — DO NOT EDIT directly.`）→ 每次运行脚本都会**覆盖**，不要手改。
- **backend / desktop / control 脚手架**（标记 `# AUTO-GENERATED scaffold from commands/xxx.json — implement the execute() body.`）→ **只在文件不存在时生成一次**；一旦存在，脚本对它是 KEEP，可直接编辑 `execute()` 实现。

**覆盖规则：**
- **extension 桩**：有哨兵 → 覆盖（脚本安全重新生成）；无哨兵 → KEEP（视为已手写实现）
- **backend / desktop / control**：文件不存在 → 生成脚手架；文件已存在 → KEEP（不覆盖手写实现）

### 3. 在桩文件基础上添加实现逻辑

**extension 指令：**
- Python 桩：脚本已生成 `@register_handler` + `params`。此文件含哨兵注释，**不要直接编辑**（下次运行脚本会被覆盖）。如需 Python 侧前置逻辑，写到独立文件再导入。
- JS handler：首次生成后可直接编辑。在 `registerHandler` 回调中实现浏览器操作。

**backend / desktop / control 指令：**
- **缺文件时**脚本会生成一次脚手架（文件顶部含 `# AUTO-GENERATED scaffold ... implement the execute() body` 标记），自动带出 `@register_handler`、`params` 与标准 `execute` 骨架：
- 在脚手架上**填实现**即可；文件一旦生成，脚本对它的后续运行一律 **KEEP，不会覆盖**。

```python
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="xxx", label="xxx", category="xxx", runtime="backend", ...)
class XxxHandler:
    params = [...]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra", {})
        # TODO: 在这里实现核心逻辑（用 extra.get("paramName") 读取参数）
        runner.vars["resultVar"] = 结果值
        runner.results.append({"stepId": step_id, "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id, "result": result})
        return True
```

- desktop 指令多一步：从 `_win32.py` 或 `_uia.py` 导入底层 API。

### 4. 重新构建 JS（仅 extension）

```bash
python scripts/build_content_js.py
```

### 5. 验证

重启服务器 → `auto_register()` 自动发现新 handler。

```bash
curl -X POST http://localhost:xxxx/api/commands/sync-check
curl -X POST http://localhost:xxxx/api/commands/validate
```

## 修改已有指令

| 指令类型 | 改 JSON 后 | 需手动同步 |
|---------|-----------|-----------|
| extension | 运行脚本 → Python 桩自动覆盖；JS KEEP | JS 参数变化需手动同步 |
| backend | 脚本对已存在文件 KEEP（不覆盖） | `@register_handler` 参数手动同步 |
| desktop | 脚本对已存在文件 KEEP（不覆盖） | `@register_handler` 参数手动同步 |
| control | 同左（结构性指令 SKIP） | `@register_handler` 参数手动同步 |

> 注意：脚手架只在首建时生成一次；改 JSON 后**参数不会自动回填到手写文件**，需保持 JSON 与 `@register_handler` 参数一致（由 `validate` 的 backend 一致性检查兜底）。

之后运行 `build_content_js.py`（extension）并验证。

## 禁止行为

| 禁止 | 原因 |
|------|------|
| 直接创建 handler 文件而不先建 JSON | JSON 是唯一事实来源 |
| 修改 JSON 后不运行 `generate_commands.py` | `@register_handler` 不会自动同步 |
| 手写 `@register_handler(...)` + `Param` boilerplate | 应由脚本生成，手写易遗漏（backend 脚手架已自动带出） |
| 编辑含 `DO NOT EDIT` 哨兵的 extension Python 桩 | 下次运行脚本会被覆盖 |
| 在生成脚手架前就手写 handler | 会绕过脚手架、重复 boilerplate（backend 脚手架应直接在其上实现） |
| 用无 `path` 的裸 `glob`（如 `glob("commands/*.json")`、`glob("**/categories.json")`） | 从仓库根整树遍历会踩到 `.venv/`/`webrpa/`/`src` 等巨大目录而 30s 超时；必须显式传 `path` 收窄 |
| 对工作区做 `Get-ChildItem -Recurse` 全树统计 | 同上，会卡死 |
| 读 `.env` / 把 API Key 等密钥内容带进对话或提交 | 密钥只应经 `os.getenv(...)` 在运行时读取，不落日志不动输出 |

## 现有 handler 参考

### extension
| 指令 | 特点 |
|---|---|
| `clickElement` | 注册桩，JS delegate 到 doClick |
| `inputElement` | 注册桩，JS delegate 到 doInput |
| `waitForElement` | 注册桩，JS 自定义实现 |
| `launchBrowser` | 完整 execute，浏览器启动 + 扩展通信 |

### backend
| 指令 | 特点 |
|---|---|
| `setVar` | 变量操作，含值类型转换 |
| `httpRequest` | HTTP 请求 |
| `excelRead` | 读取 Excel(.xlsx)，单格→标量 / 区域→二维列表（含 openpyxl 单列/单行扁平返回处理） |
| `deepseekChat` | 调用 DeepSeek Chat Completions API，返回正文写入变量（HTTP + `os.getenv` 取密钥） |

### desktop（runtime=backend，调用 Win32/UIA API）
| 指令 | 特点 |
|---|---|
| `findWindow` | 查找窗口，Win32 API |
| `clickControl` | 点击控件 |
| `inputControl` | 控件输入，WM_SETTEXT + keybd_event 降级 |
| `clickMenu` | 点击菜单项，Win32 菜单 API |
| `openApp` | 打开软件，subprocess 启动 |
| `sendKey` | OS 级按键，keybd_event |
| `findChild` | 查找子控件 |
| `findSibling` | 查找兄弟控件 |
| `findParent` | 查找父窗口 |

### control
| 指令 | 特点 |
|---|---|
| `forEachElement` | 循环遍历元素 |

## 架构约束

- `@register_handler` 装饰器注册到 `_HANDLER_REGISTRY`
- `auto_register()` 在服务器 lifespan 中调用 → 触发 `__init__.py` 自发现导入（含 `desktop_commands`）
- **JSON 是唯一事实来源。** 变更指令定义必须先改 JSON，再运行 `generate_commands.py`
- handler 参数名必须与 JSON `params[].name` 一致（`execute` 中通过 `extra.get("paramName")` 读取）
- **不要编辑含哨兵注释（`AUTO-GENERATED`）的 Python 文件**，它们会被脚本覆盖
