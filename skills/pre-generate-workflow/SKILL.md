---
name: pre-generate-workflow
description: 预生成流程。分析用户的自动化需求，用自然语言拆解为分步骤的流程描述，检查元素库是否就绪，与用户对齐后再交给 generate-workflow 执行。
---

# 预生成流程

> **位置：** 本 skill 产出自然语言流程描述，不写代码。
> 下游 `generate-workflow` skill 读取本 skill 的产出，写入流程目录（一个流程 = 一个目录）。

## 职责边界

```
用户需求
    │
    ▼
pre-generate-workflow   ← 本 skill
    │
    ├─ 分析需求，拆解步骤
    ├─ 检查元素库（目录内 elements.json）
    ├─ 与用户对齐
    │
    ▼
结构化流程描述（自然语言，可被下游消费）
    │
    ▼
generate-workflow       ← 下游 skill
    │
    ▼
写 workflow.json + elements.json → 流程目录 → rpa_run_start 运行
```

> **⚠️ 规划时先核对指令能力面板**：拆解流程时应先 `rpa_commands(side=editor)` 盘现有指令，**尽量落在现有指令能表达的步骤**；若发现某一步现有指令无法满足，**不要默认要去新建指令**——把它作为"待确认的能力缺口"列给用户，说明"缺哪个能力"，经用户确认后才交给下游（新建走 `rpa_new_command`）。参考下游 `generate-workflow` 的「硬性约束」章节。

## 目录模式（主线，取代旧的 /api/workflows 数据库模式）

本 skill 与下游 `generate-workflow` 已切换到 **「一个流程 = 一个目录」** 的主线：

- 流程 = `RPA_HOME/<流程名>/` 目录（内部 `rpa.json` + `workflow.json` + `elements.json` + `images/` + `run_logs/`）
- 不再使用 `curl /api/workflows` 等数据库 CRUD；改为 **DSH 文件工具写目录内 JSON** + **`rpa_*` 工具**
- 运行：`rpa_run_start()`（不带参数，当前会话目录即流程目录）→ `rpa_run_wait(project=目录, run_id)`

### 目录模式下的工具对应

| 旧 DB 模式 | 目录模式 |
|---|---|
| `POST /api/workflows` 建工作流 | `rpa_project_create(path, name)` 建流程目录 |
| `GET /api/workflows/{id}/elements` 查元素 | 读目录内 `elements.json`（`rpa_capture` 写回） |
| `PUT /api/workflows/{id}/nodes/batch` 写节点 | 文件工具写 `workflow.json`（下游 generate-workflow 负责） |
| `python skills/scripts/run_workflow.py <id>` 运行 | `rpa_run_start()` + `rpa_run_wait(project, run_id)` |

## 与用户交互模型

本 skill 与用户有三次关键交互：

```
用户: "帮我做一个百度搜索天气预报的流程"
       │
       ▼
[交互 1] 确认需求范围 ← 只有信息不足时才追问
       │
       ▼
[交互 2] 元素库检查 ← 缺元素时硬中断，等用户补完
       │
       ▼
[交互 3] 流程对齐 ← 呈现步骤描述，用户逐项确认/修改
       │
       ▼
产出 → 交给 generate-workflow
```

### 交互 1 原则：渐进式 —— 先干后补，一次只问一个关键分叉

**核心信条：能推断的不问，会卡住下一步的才问，逐层往下推，不要一次甩一堆问题。**

「一句话生成」的用户通常说得很简略，但**不是所有缺失都值得打断**。按「是否硬前置」分两类：

**硬前置（必须问，否则第一步节点就写不出来）：**

| 缺失信息 | 追问方式 | 为什么硬前置 |
|---|---|---|
| 新建流程 vs 改已有流程 | "是要新建一个流程，还是修改已有的？（新建请给个流程名）" | 目录模式下 `rpa_project_create` 需要目录名，猜错等于白做 |
| 目标站点 URL / 应用名 | "目标网页的 URL 是什么？（或站点名，我来补全）" | `navigate`/`launchBrowser` 的 url 是第二步，几乎必填 |
| 抓哪些字段 / 存到哪 / 抓几条 | "要抓哪些字段？结果存成什么（JSON/表格/仅打印）？抓多少条？" | 直接决定 `getText` 的 element 和结果写回，猜错白跑 |

**非硬前置（尽量推断，不打断）：** 变量名、指令选型、timeout/retryCount 等参数细节、浏览器选 chrome 还是 edge（默认从 `rpa_status` 的在线扩展推断）。

**渐进式算法（先干后补）：**

1. 先只问**一个**最硬的缺口（通常先是「新建 vs 改哪个」）；
2. 拿到答案立即往下推一步——能推断的就推断，能补的补；
3. 推到**真正卡住下一步**（如要写 `navigate` 却没 URL）时，再问**下一个**问题；
4. 重复直到信息足够产出完整流程描述；**不要前置问完所有问题再动工**。

> ⚠️ 例外：用户描述含糊到连「平台」（浏览器/桌面）、「动作」（搜/抓/填）都分不清时，先补一句澄清，再进入渐进式。

### 交互 2：元素库检查 — 先列清单，用户确认后再捕获

1. 根据步骤拆解结果，列出需要的元素
2. 读流程目录内 `elements.json`（`rpa_capture` 捕获写回的元素库；也可能是 `workflow.json` 内联的遗留 `elements` 数组）
3. 对比得出缺失清单
4. **如果缺元素，先列出缺失清单并问用户「是否现在捕获」，经确认再拉起捕获：**

```
⚠️ 缺以下 N 个元素（当前已有 M 个）：

  □ search_input    — 搜索输入框 (类型: plain)
  □ search_btn      — 搜索按钮 (类型: plain)
  □ result_list     — 搜索结果列表 (类型: anchor)
  □ result_title    — 结果标题，锚定到 result_list (类型: child)

是否现在逐条捕获？
  - "开始捕获" (Recommended) → 我依次拉起 rpa_capture，你在遮罩上 Alt+点击目标元素
  - "稍后再说 / 我先自己捕获"
```

5. 用户确认「开始捕获」后，Agent **逐条**调 `rpa_capture(name=<清单里的名字>)`：
   - 拉起全屏遮罩 → 用户把鼠标移到目标元素上 hover 高亮 → 在目标上 **Alt+点击** 完成捕获
   - 捕获结果自动写回流程目录 `elements.json`（含截图到 `images/`）
6. 全部捕获完，重新读 `elements.json` 确认清单已齐，再进入步骤 4。

> **捕获由 Agent 用 `rpa_capture` 工具完成**（不是让用户去扩展面板手点）：`rpa_capture` 弹全屏遮罩，用户 Alt+点击目标元素即完成一次捕获。桌面元素同理（Win32/UIA）。用户若选「稍后」，则中断等待，不要跳过检查硬往下生成。

### 交互 3：流程对齐 — 呈现 + 修改循环

1. 将完整流程描述呈现给用户
2. 用 `AskUserQuestion` 确认：

```
问题: "流程描述是否正确？"
选项:
  - "确认，继续生成" (Recommended)
  - "需要修改"
```

3. 如果用户选"需要修改"，请用户用自然语言描述要改什么，然后修改流程描述并重新呈现，循环直到确认。

---

## 执行流程

### 步骤 0：确定流程目录（渐进式提问的第一问）

**这是渐进式提问的第一个硬前置**：先问用户「新建流程还是改已有流程」，不要猜。

- 先调 `rpa_project_list` 看当前 `RPA_HOME` 下已有哪些流程目录。
- 若用户描述里没说是新建还是改哪个，用 `AskUserQuestion` 问（选项=已有流程列表 + 「新建」）。

**情况 A：改已有流程，或用户给了流程目录路径 / 当前会话目录已是流程目录**
→ 确认目录内有 `rpa.json`，直接进入步骤 1。

**情况 B：新建流程**
→ 先建流程目录（在 RPA_HOME 下）：

```
rpa_project_create(path=<RPA_HOME>/<流程名>, name="流程名")
# 幂等；在目标目录写 rpa.json，之后该目录会话自动出现「流程」编辑 tab
```

之后流程数据落在 `<目录>/workflow.json` + `<目录>/elements.json`。

> 元素库为空时交互 2 会中断（先列清单→用户确认→再 rpa_capture 捕获）。

### 步骤 1：解析用户需求

从用户的自然语言描述中提取关键信息。**按交互 1 的渐进式原则，硬前置缺口（URL、抓取字段/去向）逐个追问，其余推断：**

- **目标平台**：浏览器自动化 / 桌面自动化？（含糊才问，否则从语境推断）
- **目标页面**：URL 是什么？哪个应用？（**硬前置**，缺则问）
- **操作序列**：用户要做什么？（打开 → 搜索 → 点击 → 抓取 → ...）
- **数据去向**：结果存变量？写表格？输出？（**硬前置**，缺则问）
- **抓取字段**：抓哪些字段、抓几条？（**硬前置**，缺则问）
- **循环/条件**：需要翻页？遍历列表？条件判断？（尽量推断）
- **变量**：哪些中间值需要保存？（Agent 自定，不问）

### 步骤 2：查询可用指令

调用 `rpa_commands(side=editor)` 获取编辑器指令目录（含参数 schema），了解当前可用的指令集合。确认用户的每一步有对应指令可执行。

> **注意**：`commands/*.json` 声明的参数名可能与 handler 实际读取名不一致
> （如 forList 声明 `listName` 但 handler 读 `listVar`）。已验证真值见
> `generate-workflow` skill 的「已验证真值」一节，生成阶段以该节为准。

### 步骤 3：检查元素库

用户描述的步骤中可能涉及页面元素（按钮、输入框、列表等）。读流程目录内的 `elements.json`（或 `workflow.json` 内联的遗留 `elements` 数组）查已有元素：

每个元素的关键字段：

| 字段 | 含义 |
|------|------|
| `name` | 元素唯一名，node 中通过 `element_name` 引用 |
| `element_kind` | `plain` / `anchor` / `child` |
| `web_selector` | CSS/XPath 选择器 |
| `relative_selector` | 相对选择器（child 元素） |
| `anchor_element_name` | 锚点元素名 |

**检查项：**

```
□ 每个需要交互的页面元素是否已捕获？
  → 缺少的元素需要用户先去捕获（扩展面板 → 元素选取）
□ child 类元素是否有 anchor_element_name？
□ child 元素是否只出现在 forEachElement 循环内？
□ forEachElement 的循环元素是否为 anchor 或 plain？
□ 涉及 setVar 的步骤是否已想好 valueType（str-input/any-expr 等）？
□ whileCondition 循环是否已想好 maxIterations（防挂）？
```

**元素不够 → 按"交互 2"模式硬中断：**

输出缺失清单，等待用户补完。用户回复"好了"/"done"后，重新读 `elements.json` 确认。全部就绪才继续步骤 4。**

捕获由 Agent 用 `rpa_capture` 工具完成（弹遮罩 → 用户 Alt+点击目标元素 → 自动写回 `elements.json`），无需用户去扩展面板手点。
不要跳过检查直接进入步骤 4。

### 步骤 4：拆解为分步骤自然语言描述

将用户需求拆解为线性步骤序列。每步描述包含：

```
步骤 N. [指令名] — 中文描述
   ├─ 前置条件: (需要什么变量/状态)
   ├─ 操作元素: element_name 或 "无"
   ├─ 参数:
   │    · paramName = 值或描述
   │    · ...
   ├─ 输出: (产生什么变量/结果)
   └─ 备注: (特殊说明)
```

对于容器步骤（if/forEach/while），用缩进表示嵌套：

```
步骤 3. forEachElement — 遍历商品列表
   ├─ 操作元素: product_list
   ├─ 参数:
   │    · maxItems = 0（全部）
   │
   步骤 3.1. getText — 获取商品名称
   │  ├─ 操作元素: product_name (child)
   │  └─ 输出: → {{productName}}
   │
   步骤 3.2. getText — 获取商品价格
      ├─ 操作元素: product_price (child)
      └─ 输出: → {{productPrice}}
```

### 步骤 5：与用户对齐（交互 3）

将步骤 4 产出的完整流程描述呈现给用户。然后用 `AskUserQuestion` 确认：

```
问题: "以上流程描述是否正确？"
选项:
  - "确认，继续生成"
  - "需要修改"
```

如果用户选"需要修改"，请用户描述要改什么，修改后重新呈现，循环直到确认。
用户确认后，将产出交给下游 `generate-workflow` skill。

### 步骤 6：输出格式

最终产出一个结构化的流程描述，作为 `generate-workflow` 的输入：

```markdown
## 流程: {流程名称}

- 类型: browser | desktop
- URL: {目标URL或应用名}
- 浏览器: chrome | edge (browser类型时)

### 元素依赖

| 元素名 | element_kind | 用途 |
|--------|-------------|------|
| search_input | plain | 搜索输入框 |
| search_btn | plain | 搜索按钮 |
| result_list | anchor | 搜索结果列表 |
| result_title | child | 结果标题(相对result_list) |

### 步骤序列

步骤 1. launchBrowser — 打开浏览器
   参数: browserType=chrome, windowVar=browser
   输出: → {{browser}}

步骤 2. navigate — 导航到目标页面
   参数: url=https://example.com, windowVar={{browser}}

步骤 3. inputElement — 在搜索框输入关键词
   操作元素: search_input
   参数: text=天气预报, windowVar={{browser}}

步骤 4. clickElement — 点击搜索按钮
   操作元素: search_btn
   参数: windowVar={{browser}}

步骤 5. waitForElement — 等待结果加载
   操作元素: result_list
   参数: timeout=10, windowVar={{browser}}

步骤 6. forEachElement — 遍历搜索结果
   操作元素: result_list
   参数: maxItems=5

   步骤 6.1. getText — 获取标题
      操作元素: result_title (child)
      输出: → saveToVar=title

   步骤 6.2. log — 打印标题
      参数: message={{title}}

步骤 7. closeBrowser — 关闭浏览器
   参数: windowVar={{browser}}
```

## 禁止行为

| 禁止 | 原因 |
|------|------|
| 跳过元素检查直接生成 | 缺少元素会导致运行失败 |
| 不拆解嵌套逻辑 | if/forEach 的 body 必须明确缩进层 |
| 使用不存在的指令 | 步骤 2 已列出了可用指令列表 |
| 不确认就交给下游 | 必须等用户确认步骤 5 |
