# 指令一致性改造方案：一处配置，全链路生效

## 一、现状诊断

当前指令系统存在**“定义分散、执行硬编码”**的问题。新增一条指令往往要改 4～6 处：

| 环节 | 当前做法 | 改动成本 |
|------|----------|----------|
| 指令元数据 | `src/runtime/workflow/commands.py` 的 `COMMAND_REGISTRY` 硬编码 | 中 |
| 数据持久化 | 启动时 `commands.py → DB` 单向同步，已存在的不覆盖启停状态 | 低 |
| 前端展示 | 通过 `/api/commands` 读取数据库字段，已 schema-driven | 低 |
| 后端代码生成 | `src/runtime/workflow/emitters/*.py` 每个指令一个 emit 函数 | 高 |
| 后端本地执行 | `extension_runner._handle_local()` 中 `if cmd_type == "xxx"` 硬编码 | 高 |
| 扩展端执行 | `extension/content.js` 中每个 handler 单独 `registerHandler` | 高 |

结果是：**改字段容易，改行为难；新增指令必须动代码+重启服务+重载扩展**。

### 关键瓶颈

1. **执行语义与元数据分离**。`commands.py` 管“长什么样”，`emitters/`、`extension_runner.py`、`content.js` 管“怎么跑”。元数据里的 `handler` 字段虽然存在，但只被当作路由名，具体逻辑仍散落各处。
2. **本地/扩展双端都硬编码**。`_handle_local()` 里为 `setVar`、`log`、`appendToList` 等写了大量 `if` 分支；content.js 里 `click`、`input`、`extract` 等也各写一套。
3. **容器/分支/结构标记语义强依赖代码**。`if/for/try/else/catch/endIf` 等容器的括号匹配、子节点展开逻辑在前后端多处重复（`extension_emitter._match_brackets`、`WorkflowContext.matchBrackets` 等）。

## 二、目标

> 在后台（管理界面 / 数据库）一处完成指令的**新增、修改、删除、启停**，前端表单、后端代码生成、扩展端执行尽量**少改动甚至不改动**即可生效。

具体指标：

- 新增一条“普通”指令（基于已有元素动作或本地计算），**零代码改动**即可上线。
- 修改指令字段、默认值、图标、排序、启停状态，**零代码改动**、无需重启。
- 删除/禁用指令，**零代码改动**，已引用工作流的节点保留兼容提示。
- 容器指令和复杂控制流允许少量代码模板，但元数据可配置。

## 三、可选方案

### 方案 A：纯解释器模式（数据库即唯一事实来源）

把指令的字段、校验、执行语义全部存在数据库。后端和扩展端都改成通用解释器：

- 扩展端只保留 `elementAction` 一个 handler，根据 `action` 字段（`click/input/extract/scroll/hover/...`）+ `extra` 参数统一执行。
- 后端本地执行只保留一个 `localAction` 解释器，根据 `action` 字段（`setVar/log/appendToList/httpRequest/...`）统一执行。
- 容器控制流仍由代码处理，但容器类型、分支类型、结构类型、闭合关系全部来自数据库字段（`isContainer/isBranch/isStructural/closesWith`）。

**优点**：一处配置即可上线普通指令；新增指令无需重启。
**缺点**：解释器必须覆盖全部通用模式，前期抽象工作量大；复杂指令（如 `callAiApp`、自定义 JS）仍需特殊处理。

### 方案 B：注册表 + 插件脚本混合模式

保持数据库作为元数据和简单逻辑的来源，复杂逻辑通过“插件脚本”注入：

- 数据库增加 `runtime_script` 字段，可存放一段 JavaScript（扩展端）或 Python（后端）。
- 普通指令走通用解释器；特殊指令走插件脚本。
- 脚本可热加载，新增复杂指令只需在后台贴脚本。

**优点**：灵活性最高，连复杂指令都能配置上线。
**缺点**：引入 eval/exec 安全风险；脚本调试、版本管理、错误定位成本高；违背“validate at boundaries”原则。

### 方案 C：数据库元数据 + 代码注册表分层模式（推荐）

数据库保留所有**元数据**（字段、图标、排序、启停、handler、local、容器标记等），执行层改为**注册表驱动的通用实现**：

- 后端 emitter：普通指令统一走 schema-driven 通用 emitter；只有容器/特殊转换保留专用 emitter。
- 后端本地执行：把 `_handle_local()` 的硬编码 `if` 分支迁移到 `LOCAL_HANDLERS` 注册字典，新增本地指令只需新增一个函数并注册。
- 扩展端执行：content.js 现有 `registerHandler`  already 是注册表，但 handler 函数仍是散的；把元素类 handler 合并为 `elementAction`，通过 `action` 参数内部分发。
- 数据库作为唯一事实来源，启动时只做一次性同步或完全以 DB 为准；`commands.py` 退化为“默认 seed”，不再参与运行时。

**优点**：平衡了配置化和代码可控性；不需要 eval；大部分普通指令可零代码上线；保留复杂指令的代码扩展点。
**缺点**：需要一次中等规模的重构；容器控制流仍需代码维护。

## 四、推荐方案：方案 C 的详细设计

### 4.1 元数据层：数据库为唯一事实来源

`WorkflowCommand` 表已具备大部分字段，补充/明确如下：

| 字段 | 用途 |
|------|------|
| `type` | 唯一标识，如 `click`、`setVar` |
| `label/category/icon/...` | 展示层 |
| `fields` | JSON Schema，驱动前端表单、默认值填充、后端代码生成 |
| `handler` | 扩展端 handler 名，如 `elementAction`、`navigate`、`pressKey` |
| `local` | 是否后端本地执行 |
| `is_container/is_branch/is_structural` | 控制流标记 |
| `closes_with` | 容器闭合指令类型，如 `forEachElement` → `endFor` |
| `enabled` | 启停开关 |
| `builtin` | 是否内置（防误删） |

运行时**只读 DB**，不再从 `commands.py` 加载。`commands.py` 保留为“首次安装 seed”，由 `alembic` 或启动脚本一次性导入后淡出。

### 4.2 后端 emitter：普通指令通用化

当前 `emitters/*.py` 为几乎每个指令写了一个函数，例如 `_emit_click`、`_emit_input`、`_emit_getText`。它们本质上都做同一件事：

```python
loc = _loc_call(node, extra, element_map)
lines.append(f"{prefix}result = await ext_manager.send_step(tab, {loc}, ...)")
```

改造后：

1. 删除大量重复 emitter，只保留：
   - 通用 emitter：`_emit_generic_extension`、`_emit_generic_local`
   - 容器 emitter：`if/else`、`for/while`、`try/catch`、`break/continue/end`
   - 特殊转换 emitter：`extract`（需把 `attrName` 映射为 `attribute`）、`scroll`（需把 `scrollType` 映射为 `scrollType`）等
2. emitter 注册表由 `handler` 字段决定：
   ```python
   _EMIT_HANDLERS[node.type] = _generic_emitter_for(cmd)
   ```
   或运行时从 `EMITTER_REGISTRY[cmd['handler']]` 查找。
3. `_attach_common_advanced` 继续为普通指令附加 `onError/retryCount/timeout/visibilityMode/humanLike`。

### 4.3 后端本地执行：注册表替代 if 分支

把 `extension_runner._handle_local()` 改造为：

```python
LOCAL_HANDLERS: dict[str, Callable] = {}

def register_local(name: str):
    def decorator(fn):
        LOCAL_HANDLERS[name] = fn
        return fn
    return decorator

@register_local("setVar")
async def _local_setVar(runner, cmd_type, step_id, instr): ...

@register_local("log")
async def _local_log(runner, cmd_type, step_id, instr): ...
```

新增本地指令只需：在 `commands.py`（seed）和 DB 中定义元数据 + 新增一个 `@register_local` 函数。**无需修改 `_execute_instruction` 分发逻辑**。

对于简单变量/数据/日志操作，可进一步抽象为“动作模板”：

| action | 语义 |
|--------|------|
| `set` | `vars[name] = coerce(value, type)` |
| `append` | `vars[list].append(value)` |
| `log` | 打印并记录 |
| `http` | 发请求并保存结果 |

这样连 `@register_local` 都不用写，纯配置即可。

### 4.4 扩展端执行：元素动作统一 handler

content.js 已有 `registerHandler`，建议新增一个通用 `elementAction` handler：

```javascript
registerHandler('elementAction', async function elementAction({ locator, selectorFamily, extra }) {
  const action = extra?.action; // 'click' | 'input' | 'extract' | 'scroll' | ...
  switch (action) {
    case 'click': return doClick(...);
    case 'input': return doInput(...);
    case 'extract': return doExtract(...);
    case 'scroll': return doScroll(...);
    case 'hover': return doHover(...);
    case 'clearInput': return doClearInput(...);
    case 'selectOption': return doSelectOption(...);
    default: throw new Error(`Unknown elementAction: ${action}`);
  }
});
```

原 `click`、`input`、`extract`、`scroll`、`hover`、`clearInput`、`selectOption` 等 handler 可保留作为兼容别名，也可以全部迁移到 `elementAction`。

配置时：

- `click` → `handler: "elementAction"`，`extra.action: "click"`
- `input` → `handler: "elementAction"`，`extra.action: "input"`
- 新增 `doubleClick` → `handler: "elementAction"`，`extra.action: "doubleClick"`，扩展端只需在 `switch` 加一行即可。

### 4.5 容器控制流：元数据驱动闭合关系

容器、分支、结构标记的语义无法完全通用化，但闭合关系可以配置：

```json
{
  "type": "forEachElement",
  "isContainer": true,
  "closesWith": "endFor"
}
```

后端 `extension_emitter` 和前端 `WorkflowContext.matchBrackets` 都读取 `closesWith`，不再硬编码类型判断。

### 4.6 同步机制：seed 一次性导入

- 删除 `_load_commands_from_db` 对 `COMMAND_REGISTRY` 的写回。
- 启动时只做：`if DB 为空: 从 commands.py seed 导入`。
- 后续所有修改走 `/api/commands` CRUD + “重新加载 emitter/handler”接口。
- 提供 `/api/commands/reload`：重新加载后端 emitter 注册表；扩展端无需重载（因为 content.js 已经走通用 handler）。

## 五、中文配置界面设计

配置人员不应直接面对英文字段，后台表单必须全部中文包装，英文字段只对系统和 API 可见。

### 5.1 字段中文映射

| 英文字段（系统用） | 配置界面中文标签 | 说明 |
|------------------|----------------|------|
| `type` | 指令标识 | 英文唯一标识，如 `doubleClick` |
| `label` | 显示名称 | 左侧面板显示的中文名，如“双击元素” |
| `category` | 所属分类 | 下拉选择：元素点击、文本输入、数据提取等 |
| `icon` | 图标 | 图标选择器 |
| `iconColor` | 图标颜色 | 颜色选择器 |
| `bgColor` | 背景色 | 颜色选择器 |
| `fields` | 参数配置 | 表单设计器，配置这个指令有哪些参数 |
| `handler` | 执行方式 | 下拉选择：浏览器执行（扩展）/ 后端执行（本地） |
| `local` | 是否本地执行 | 由“执行方式”自动带出，无需用户直接填 |
| `isContainer` | 是否容器指令 | 开关：是否包含子节点 |
| `isBranch` | 是否分支节点 | 开关：如 else/catch |
| `isStructural` | 是否结构标记 | 开关：如 endIf/endFor |
| `closesWith` | 闭合指令 | 容器指令才显示，如 forEachElement → endFor |
| `enabled` | 是否启用 | 开关 |
| `categoryOrder` | 分类排序 | 数字 |
| `commandOrder` | 指令排序 | 数字 |

### 5.2 “新增指令”表单示例

```
┌─────────────────────────────────────┐
│ 新增指令                             │
├─────────────────────────────────────┤
│ 指令标识        [ doubleClick       ] │
│ 显示名称        [ 双击元素           ] │
│ 所属分类        [ 元素点击 ▼        ] │
│ 图标            [ 🖱️ 选择 ]          │
│ 图标颜色        [ 蓝色 ▼ ]           │
│ 背景色          [ 浅蓝 ▼ ]           │
│                                     │
│ 是否容器指令    [ ● 否 ]             │
│ 是否启用        [ ● 是 ]             │
│                                     │
│ 执行方式        [ 浏览器执行（扩展） ▼ ] │
│ 扩展动作        [ 双击 ▼ ]           │
│                                     │
│ 参数配置：                          │
│ ┌───────────────────────────────┐   │
│ │ 参数名  显示名  类型    必填  │   │
│ │ element_name  元素  元素选择  是 │   │
│ │ timeout      超时  数字     否 │   │
│ └───────────────────────────────┘   │
│                                     │
│ [ 分析 ]  [ 测试 ]  [ 保存 ]         │
└─────────────────────────────────────┘
```

### 5.3 保存前自动分析与中文提示

保存指令时后台自动判断简单/复杂，并以中文展示：

**普通指令示例：**

```
分析结果：
✅ 该指令可被扩展端通用模板支持（动作：双击）
✅ 参数 schema 校验通过
✅ 无需新增代码，保存后即可在工作流中使用

[确认保存]
```

**复杂指令示例：**

```
分析结果：
⚠️ 当前扩展端暂不支持“长按”动作
👉 需要开发人员在 extension/content.js 的 elementAction 中增加一行代码
✅ 参数 schema 校验通过

[保存为草稿]  [通知开发]
```

### 5.4 能力矩阵中文页面

后台提供“模板支持矩阵”页面，配置人员可自行查阅：

**浏览器端支持的动作：**
[双击] [单击] [右击] [输入] [清空输入] [输入并回车]
[提取文本] [提取属性] [提取HTML] [提取值]
[滚动到顶部] [滚动到底部] [滚动一屏] [滚动到元素]
[悬停] [取消悬停] [选择下拉项] [按键]

**后端本地支持的动作：**
[设置变量] [追加到列表] [设置字典值]
[打印日志] [数值自增] [字符串拼接]
[HTTP请求] [截图]

不在矩阵中的动作，保存时自动标红提示“需开发支持”。

## 六、实施路径

建议分 3 个阶段，每阶段都可独立验证：

### 阶段 1：元数据单一来源化（1～2 天）

1. 确认 `WorkflowCommand` 表字段齐全，补充 `closes_with`。
2. 修改 `src/runtime/main.py`：
   - 启动时仅在 DB 为空时从 `commands.py` seed 导入。
   - 删除 `_load_commands_from_db` 写回 `COMMAND_REGISTRY` 的逻辑。
3. 修改 `commands.py`：保留 `get_command/list_commands_by_category` 等工具函数，但运行时从 DB 读取；`COMMAND_REGISTRY` 仅作为 seed。
4. 验证：后台修改指令字段/排序/启停，前端即时生效，无需重启。

### 阶段 2：后端执行层通用化（2～3 天）

1. 重构 `emitters/*.py`：
   - 引入 `EMITTER_REGISTRY`，普通指令走 `_emit_generic_extension` / `_emit_generic_local`。
   - 保留容器 emitter 和少量特殊转换。
2. 重构 `extension_runner._handle_local()`：
   - 引入 `LOCAL_HANDLERS` 注册表。
   - 把现有 `setVar/log/appendToList/...` 迁移为 `@register_local` 函数。
3. 提供 `/api/commands/reload-emitters` 和 `/api/commands/reload-handlers`（或合并）。
4. 跑已有工作流回归测试，确保生成代码等价。

### 阶段 3：扩展端通用化（1～2 天）

1. content.js 新增 `elementAction` handler，内部统一分发 click/input/extract/scroll/hover/clearInput/selectOption。
2. 数据库中对应指令的 `handler` 改为 `elementAction`，`extra` 中保留/注入 `action` 字段。
3. 保留旧 handler 别名 1～2 个版本，平滑过渡。
4. 新增一条测试指令（如 `doubleClick`），不改动后端代码，只配置 DB + 扩展端加一行 case，验证“一处配置生效”。

## 七、风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 重构 emitter 破坏现有工作流生成代码 | 高 | 阶段 2 必须跑端到端回归；保留旧 emitter 作为 fallback |
| 数据库成为唯一来源后误改内置指令 | 中 | `is_builtin=1` 的指令限制可改字段；提供“恢复默认”按钮 |
| 通用 handler 覆盖不了未来复杂指令 | 中 | 保留 `@register_local` 和 `registerHandler` 作为扩展出口 |
| content.js 通用化后性能/调试变差 | 低 | 每个 action 仍是独立函数，只是入口统一；日志保留 action 名 |
| 多人同时改 DB 配置冲突 | 低 | MVP 阶段单用户；后续可加版本/审计字段 |

## 七、Next Actions

1. 确认是否采纳方案 C，以及是否分阶段实施。
2. 若采纳，先补 `WorkflowCommand.closes_with` 字段并调整启动同步逻辑（阶段 1）。
3. 选定一条“新增普通指令”作为试点（如 `doubleClick` 或 `getCurrentUrl`），用来验证阶段 3 的“零代码上线”目标。
