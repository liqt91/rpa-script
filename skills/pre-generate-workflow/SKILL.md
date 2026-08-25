---
name: pre-generate-workflow
description: 预生成流程。分析用户的自动化需求，用自然语言拆解为分步骤的流程描述，检查元素库是否就绪，与用户对齐后再交给 generate-workflow 执行。
---

# 预生成流程

> **位置：** 本 skill 产出自然语言流程描述，不写代码。
> 下游 `generate-workflow` skill 读取本 skill 的产出，生成实际的节点数据。

## 职责边界

```
用户需求
    │
    ▼
pre-generate-workflow   ← 本 skill
    │
    ├─ 分析需求，拆解步骤
    ├─ 检查元素库
    ├─ 与用户对齐
    │
    ▼
结构化流程描述（自然语言，可被下游消费）
    │
    ▼
generate-workflow       ← 下游 skill
    │
    ▼
WorkflowNode[] → API → 数据库
```

> **⚠️ 规划时先核对指令能力面板**：拆解流程时应先 `rpa_commands(side=editor)` 盘现有指令，**尽量落在现有指令能表达的步骤**；若发现某一步现有指令无法满足，**不要默认要去新建指令**——把它作为"待确认的能力缺口"列给用户，说明"缺哪个能力"，经用户确认后才交给下游（新建走 `rpa_new_command`）。参考下游 `generate-workflow` 的「硬性约束」章节。

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

### 交互 1 原则：宁可推断，少问

用户通常给出足够清晰的描述。只在以下情况追问：

| 缺失信息 | 追问方式 |
|---------|---------|
| 没说是浏览器还是桌面 | "这个流程是在浏览器里操作还是桌面应用？" |
| 没给 URL | "目标网页的 URL 是什么？"（仅浏览器流程） |
| 描述模糊（如"帮我自动化XX网站"） | "具体要做什么？比如搜索、抓取数据、填表单？" |

**不要问的**：变量名（Agent 自己起）、指令选型（Agent 自己判断）、参数细节（generate-workflow 阶段处理）。

### 交互 2：元素库检查 — 硬中断

1. 根据步骤拆解结果，列出需要的元素
2. 调 API 查现有元素
3. 对比得出缺失清单
4. **如果缺元素，输出清单并中断，不继续后续步骤：**

```
⚠️ 元素缺失 — 请先在浏览器扩展面板中捕获以下元素，完成后回复"好了"：

  □ search_input    — 搜索输入框 (类型: plain)
  □ search_btn      — 搜索按钮 (类型: plain)
  □ result_list     — 搜索结果列表 (类型: anchor)
  □ result_title    — 结果标题，锚定到 result_list (类型: child)

当前已有元素: 0 个
```

5. 用户补完后，重新查询确认，全部就绪再继续。

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

### 步骤 0：确定 Workflow

用户可能已有 workflow（含已捕获的元素），也可能是全新开始。

**情况 A：用户提供了 workflow_id**
→ 直接进入步骤 1。

**情况 B：用户没有 workflow**
→ 先创建一个空 workflow：

```bash
curl -X POST http://localhost:xxxx/api/workflows \
  -H "Content-Type: application/json" \
  -d '{"name": "新流程", "description": "", "url": "", "parameters": []}'
# 记录返回的 id
```

> 元素库为空时交互 2 会中断。让用户在新 workflow 下捕获元素后再继续。

### 步骤 1：解析用户需求

从用户的自然语言描述中提取关键信息。信息不足时参照交互 1 原则追问。

- **目标平台**：浏览器自动化 / 桌面自动化？
- **目标页面**：URL 是什么？哪个应用？
- **操作序列**：用户要做什么？（打开 → 搜索 → 点击 → 抓取 → ...）
- **数据去向**：结果存变量？写表格？输出？
- **循环/条件**：需要翻页？遍历列表？条件判断？
- **变量**：哪些中间值需要保存？

### 步骤 2：查询可用指令

遍历 `commands/` 目录下所有 JSON，了解当前可用的指令集合。确认用户的每一步有对应指令可执行。

> **注意**：`commands/*.json` 声明的参数名可能与 handler 实际读取名不一致
> （如 forList 声明 `listName` 但 handler 读 `listVar`）。已验证真值见
> `generate-workflow` skill 的「已验证真值」一节，生成阶段以该节为准。

```bash
# 快速列出所有可用指令
python -c "
import json, os
for f in sorted(os.listdir('commands')):
    if not f.endswith('.json'): continue
    with open(f'commands/{f}', encoding='utf-8') as fp:
        d = json.load(fp)
    cats = d.get('categories', [d.get('category','')])
    print(f'{d[\"cmd\"]:<28} [{d[\"runtime\"]}] {d[\"label\"]}')
"
```

### 步骤 3：检查元素库

用户描述的步骤中可能涉及页面元素（按钮、输入框、列表等）。通过 API 查询当前 workflow 已有的元素：

```bash
curl http://localhost:xxxx/api/workflows/{wf_id}/elements
```

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

输出缺失清单，等待用户补完。用户回复"好了"/"done"后，重新调 API 确认。全部就绪才继续步骤 4。**

不要替用户捕获元素（Agent 无法操作浏览器扩展面板）。
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
