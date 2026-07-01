# Handoff — 循环内元素引用：捕获-搭建-执行闭环加固 (A+B)

> 跨机续作说明。计划文件原在 `~/.claude/plans/logical-plotting-turtle.md`（不随仓库同步），已完整嵌入本文件末尾。
> 在另一台电脑：`git pull` 后读本文件 → 从 **Phase 4** 继续。

## 一句话目标

`forEachElement` 循环体内子节点引用的元素，其从属关系当前靠运行时启发式重建（全局求值 + `parent.contains` 过滤），失败时静默返回空串。改为**捕获时锚定（B）+ 搭建时声明（A）+ 失败显形（告警继续）**。方向已定，勿重新设计。

已敲定的三选一结论：
- **B 捕获锚定**：自动算相对选择器+锚点，编辑器显示锚点、允许手动改。
- **A 搭建声明**：子节点默认相对**最近外层 forEachElement**（隐式），可覆盖；“引用循环项本身”头等选项。
- **横切**：项内找不到子元素 → **告警 + 运行日志 + 继续**（不静默空串、不硬中止）。
- **向后兼容**：`relative_selector` 为空 → 全部回退旧逻辑，旧流程行为不变。

## 进度总览

| Phase | 内容 | 状态 |
|---|---|---|
| 1 | 数据层：列+迁移+model+schema+service | ✅ 完成 |
| 2 | 运行时相对解析 + 告警化 (emitter/runner/content.js) | ✅ 完成 |
| 3 | 捕获链 + 编辑器锚点预览 (content_capture.js/sidepanel) | ✅ 完成（已过双评审） |
| 4 | 编辑器声明 + Python 导出相对化 | ⬜ **未开始（从这里继续）** |
| 5 | 回填 + 端到端验收 | ⬜ 未开始 |

评审：architecture-reviewer 全过 PASS；reliability-reviewer 对 Phase 3 提 2 BLOCKING + 5 WARN，已修关键项（见下），其余带理由否决。
> 注意：本仓库 `architecture-reviewer`/`reliability-reviewer` **不是**已注册的 subagent 类型，只是 `.claude/agents/*.md`。跑评审时用 general-purpose agent，指令它先读对应 `.claude/agents/<name>.md` 再套用其标准。

---

## 已完成改动（Phase 1–3）逐文件

### Phase 1 — 数据层
- **src/repo/models.py**：`WorkflowElement` 新增三列 `relative_selector`(Text `""`)、`anchor_selector`(Text `""`)、`anchor_mode`(String(16) `"auto"`)。
- **src/repo/migrations.py**：`_migrate_008`（照 `_migrate_007` 模式，`inspect` 列存在性→逐列 `ALTER TABLE workflow_elements ADD COLUMN`）；`_SCHEMA_VERSION=8`；`_MIGRATIONS[8]=_migrate_008`。
- **src/dtypes/schemas.py**：`WorkflowElementIn`/`WorkflowElementOut` 加对应字段（camelCase alias `relativeSelector`/`anchorSelector`/`anchorMode`）。
- **src/service/elements_service.py**：`save_captured_element` 新建/更新两路径都落三字段（缺省 `""`/`"auto"`），读 `payload.get("relativeSelector"/"anchorSelector"/"anchorMode")`。

### Phase 2 — 运行时相对解析 + 告警化
- **src/runtime/workflow/extension_emitter.py**：
  - 新增 `_split_prefixed_selector(value)`（拆 `css:`/`xpath:`/`drission:` 前缀，返回 `(bare, family)`）与 `_inject_relative_fields(extra, el)`（有 `el.relative_selector` 时向 extra 注入 `relativeLocator`/`relativeSelectorFamily`/`anchorSelector`/`anchorSelectorFamily`）。
  - `_emit_instruction` 里解析出 el/locator/family/target_mode 后调 `extra = _inject_relative_fields(extra, el)`。
  - `_build_node` compound dict 加 `"elementName": node.element_name`。
- **src/runtime/workflow/extension_runner.py**：
  - 两个注入点（`_call_extension_handler` ~432、`_send_and_wait` ~1540）在 contextTotal 后加 `if extra.get("relativeLocator"): extra["useRelative"] = True`。
  - forEachElement 的两个 `__loop_ctx` 分支加 `"loopElementName": instr.get("elementName")`。
  - `_send_and_wait` 结果处理加：`result` 带 `warning` 时 `logger.warning` + emit `{"type":"stepWarning", stepId, nodeId, cmdType, warning}`，循环继续。
- **extension/content.js**：
  - 新增 `resolveAllRelativeInContext(relLocator, relFamily, rootElement)`：xpath 强制相对（`.//`/`./`/前置 `.`）、css 用 `rootElement.querySelectorAll`、drission 委托 `resolveAllLocatorsInContext`，全 try/catch 返回 `[]`。
  - `isSoftNotFound(e)`：`!!(e?.contextNotFound || e?.message?.includes('按循环序号对齐失败'))`。
  - `waitForElementWithContext` / `reResolveWithContext`：找到 parent 后先处理 `extra.referenceItemItself`（解析为 parent），再 `extra.useRelative && extra.relativeLocator`（相对查询，未命中 `addRunLog` 告警），最后回退旧“全局+contains”。**parent 存在但项内无子元素时仍立即 reject 且 `err.contextNotFound=true`（故意保留，见下方 reliability 决定）**。
  - `doExtract/doClick/doInput/doHover/doUnhover/doClearInput/doSelectOption`：包 `waitForElementWithContext` 于 try/catch，`isSoftNotFound(e)` → `addRunLog('警告: …')` + 返回带 `warning`+`contextNotFound:true` 的空/skip 结果；否则 `throw e`（走节点 onError）。

### Phase 3 — 捕获链 + 编辑器锚点预览
- **extension/content_capture.js**：
  - `buildRelativeXPath(item, el)`：从 el 向上到 item 建位置型 xpath（`./…`），>8 段或 parent 缺失/未达 item 返回 null。**修复后**：`indexOf===-1`（shadow/slot 边界）返回 null；用 `document.evaluate` 自校验 `snapshotLength===1 && ===el`。
  - `buildRelativeCss(item, el)`：试 stable id/class/data-*/tag，`item.querySelectorAll` 验证 `length===1 && [0]===el`。
  - `computeRelativeSelector(el, listFamily)`：定位含 el 的 listItem（`.find` 谓词**已加 `it && it.nodeType===1` 守卫**）；item===el 或无 list 返回 null；先 css 后 xpath；anchor 取 `buildListItemSelector` 或 `buildXPathForElement`；返回 `{relative, anchor, family}`。
  - `performCapture`：payload 加 `anchorMeta`（`relativeSelector`/`anchorSelector`/`anchorMode='auto'`），**调用包 try/catch**——锚定失败绝不破坏捕获（仅 `console.warn`）。`...anchorMeta` 跟在 `...listMeta` 后展开。
- **extension/sidepanel.html**：preview-bar 内加 `anchorBox` 面板（默认 `display:none`）：勾选框 `useRelativeChk`（默认勾）、只读 `anchorSelectorInput`、可编辑 `relativeSelectorInput`、`anchorMode` 标签。
- **extension/sidepanel.js**：元素引用 + `let relativeManuallyEdited=false`；`loadAnchorData(data)`（据 `data.relativeSelector` 显隐 anchorBox、填值、置 mode 标签，`relativeSelectorInput` 的 input 事件置 `relativeManuallyEdited=true` 且标签改“手动”）；`loadElementData` 末尾调用；`btnSave` payload 追加三字段（勾选且有值→带 relative/anchor/`manual|auto`；否则 relative/anchor 空 + `none|auto`）；`btnCancel` 复位。
  - 确认：`sidepanel.js` 才是当前捕获预览；`element-editor.html/js` 无任何注入方，是死代码。

**Reliability 对 Phase 3 的处理**：已修 ①捕获调用 try/catch（最关键，否则锚定异常会炸掉整个捕获）②`.find` nodeType 守卫 ③`buildRelativeXPath` idx===-1 守卫 ④xpath `document.evaluate` 自校验。**否决**（带理由）：`tagName`/`getAttribute` 非 Element 不可能发生（`parentElement` 只返 Element/null 且已守卫，`el` 恒为捕获 Element）；`querySelectorAll` 宽 catch 正确（是“试下一个候选”循环）；`'none'` 模式 Phase 2 已处理（空 relative→不注入→回退）。

**Phase 2 保留的争议决定**：`waitForElementWithContext` 中“parent 存在但项内无子元素 → 立即 reject”是**原逻辑，非回归，故意保留**。异质列表（本特性核心场景，如部分评论无子回复）若每个缺失项都重试满超时会拖垮循环（50 张无回复卡 ×10s = 500s）。已归类为软找不到 → 告警跳过。

**回归门（本机已验证通过）**：`python .harness/scripts/ast_structural_check.py` → PASSED；4 个 JS 文件 `node --check` OK；Python 模块全 import OK；schema v8 + `_migrate_008` 就位。

---

## Phase 4 — 编辑器声明 + Python 导出相对化（下一步，未开始）

节点侧用现有自由 `extra`（无需迁移）：
- `loopAnchor: string`（空=最近外层循环；填某 forEachElement 的 element_name 显式覆盖）
- `referenceItemItself: bool`（true=解析为循环项本身，取代 content.js 那个“子选择器==循环选择器”的脆弱兜底）
- 复用 `scope`（local/global）作总开关：`global` 完全走旧全局逻辑。

要改：
1. **src/runtime/workflow/commands.py**：给带元素的指令补 `referenceItemItself`(bool, advanced) 与 `loopAnchor`(select, advanced) 字段（可在 `_attach_common_advanced` 统一附加）。
2. **src/ui/workflow-editor/src/components/NodeForm.jsx**：选中元素若有 `relative_selector` → 展示“锚点>相对”徽标、“使用相对解析”开关（→`extra.useRelative`，默认开）、`loopAnchor` 下拉（从树中祖先 forEachElement 节点动态填充）、`referenceItemItself` 勾选。`buildPayload`(~82-93) 写进 `extra`。
3. **src/runtime/workflow/emitters/loop.py**：向子节点传 `in_loop=True`。
4. **src/runtime/workflow/emitters/_registry.py**：`_loc_call_by_name`(~73-107) 在 `in_loop` 且元素有 `relative_selector` 时生成 `item.ele/eles(相对选择器)` 而非 `tab.ele(...)`，使导出 Python 脚本同样相对解析。
5. **src/ui/workflow-editor/src/components/Toolbar.jsx**(~97-223)：元素 `{...e}` 展开已自动带新字段，无需改；仅回归测试确认导入导出往返保真。

> 跨 ≥2 层，实现后过 architecture-reviewer；找不到分支/onError 交互过 reliability-reviewer。

## Phase 5 — 回填 + 端到端验收

- 可选 best-effort 回填：对有 `dom_path`+list 元数据的旧元素，从 `web_selector` 去 `listContainer` 前缀推导相对选择器，`anchor_mode='backfill'`；推不出维持旧逻辑。**非必须**。
- 验收（用桌面库 `C:\Users\liqt91\AppData\Roaming\RPA Script\data.db` 的小红书嵌套评论流程；**只读/临时库验证，勿改生产库**）：
  1. 捕获“作者名”→ 编辑器显示 anchor=评论卡、relative=卡内作者名，可改。
  2. 单层执行：`forEachElement` 评论卡→getText 作者名，无静默空白；缺字段卡出现“警告: …返回空值并继续”。
  3. 嵌套：内层子回复相对当前卡解析，不跨卡。
  4. 原 18/19/21/22（主/子评论 getText）改相对后能取到内容。
  5. Python 导出循环体生成 `item.ele(...)`。
  6. 导入导出往返 `relative_selector`/`anchor_selector` 保真。
  7. 一个未锚定旧流程行为与改前完全一致。

## 常驻约束（CLAUDE.md）

- commit/push 仅在被明确要求时。
- 跨 ≥2 层改动过 architecture-reviewer；错误路径/异步改动过 reliability-reviewer。
- 桌面生产库 `C:\Users\liqt91\AppData\Roaming\RPA Script\data.db`——验证用临时库，勿改它。
- baseline 只减不增；勿禁结构测试；CLAUDE.md 勿超 200 条指令。
- 手写 SQLite 迁移（非 Alembic），`schema_migrations` 版本表。

---

## 原始计划全文（logical-plotting-turtle.md，仓库外，嵌入存档）

见 git 历史与本文件上半部；核心矩阵：{循环项本身 / 单子元素 / 子元素组(嵌套)} × {取数 / 点击} × {xpath / css / 混合} × {单个 / 列表}。根因：元素与循环的从属关系靠运行时重建而非捕获/搭建时确定。分阶段按风险先稳后险（数据层→运行时→捕获链→声明+导出→回填验收）。
