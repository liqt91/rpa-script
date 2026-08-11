---
name: generate-workflow
description: 根据预生成流程的产出，将自然语言步骤序列转换为 WorkflowNode[] 并通过 API 写入数据库。依赖 pre-generate-workflow 的产出作为输入。
---

# 生成流程

> **位置：** 本 skill 是 `pre-generate-workflow` 的下游。接收结构化流程描述，生成实际的节点数据并通过 API 写入。

## 职责边界

```
pre-generate-workflow 产出
    │
    ▼
generate-workflow       ← 本 skill
    │
    ├─ 映射步骤 → cmd + extra
    ├─ 构建节点树 (parent_id, order)
    ├─ 校验
    │
    ▼
POST /api/workflows      → 创建 Workflow
PUT  /api/workflows/{id}/nodes/batch  → 写入所有节点
```

## 输入格式

本 skill 接收 `pre-generate-workflow` 产出的结构化描述，包含：

- 流程名称、类型 (browser/desktop)、目标 URL
- 元素依赖表
- 步骤序列（含嵌套结构、参数、变量）

## 已验证真值（2026-08-10 对齐 command-test 技能）

以下是经 E2E 真实运行验证过的领域事实。**与 `commands/*.json` 冲突时，以此为准。**

### setVar 的 valueType（handler 注册值，非 JSON 声明值）

```
str-input / int-number / bool-check / list-input / dict-input / any-expr / any-input
```

- `any-input`：JSON 推断，失败回退字符串
- `any-expr`：value 以 `=` 前缀时受限求值，用于计数器：`setVar` + `valueType=any-expr` + `value="={{n}}+1"`

### 循环/容器参数名（handler 侧真实读取名）

| 指令 | 读什么 | 注意 |
|---|---|---|
| `forList` | `listVar` | **不是** commands/forList.json 声明的 `listName` |
| `forRange` | `start`/`end`/`step`/`itemVar` | |
| `whileCondition` | `conditionType`/`condition` + `maxIterations` | **必须设 maxIterations 防挂**（默认 100） |

### 嵌套与结构标记

- 容器节点（forRange/forList/whileCondition/forEachElement）置顶层，body 子节点 `parent_id` 指向容器
- 同 parent 下 `order` 独立递增：1, 2, 3…
- `endLoop`/`endIf` 是**顶层兄弟结构标记**，非容器子节点

### 通用参数（所有指令的 extra 可携带）

```
onError (stop/continue) / retryCount / timeout / description
浏览器指令额外有: humanLike
```

### 其他

- `openBrowser` 已删除（2026-08-10），用 `launchBrowser`；未注册指令运行时显式 stepError
- child 元素只能在 `forEachElement` 循环内使用
- 同流程 `windowVar` 引用必须一致

## 执行流程

### 步骤 1：读取并解析流程描述

从 pre-generate-workflow 的产出中提取：

- `name` → Workflow.name
- `类型` → 判定是否需要 url/target_browser 字段
- `url` → Workflow.url
- `步骤序列` → 待转换的节点树

### 步骤 2：查询指令参数定义

对流程中引用的每个指令，读取其 JSON 定义获取 params schema：

```bash
python -c "
import json
cmds = ['clickElement', 'inputElement', 'getText', 'launchBrowser', 'navigate', 'waitForElement', 'forEachElement', 'closeBrowser', 'setVar', 'log']
for c in cmds:
    path = f'commands/{c}.json'
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        params = [(p['name'], p['type'], p.get('required',False)) for p in d.get('params',[])]
        print(f'{c}:')
        for n, t, r in params:
            print(f'  {n} ({t}){\" required\" if r else \"\"}')
    except:
        print(f'{c}: NOT FOUND')
"
```

### 步骤 3：映射步骤 → 节点数据

将每个自然语言步骤映射为 WorkflowNode 数据结构：

```json
{
  "temp_id": "step_1",
  "parent_id": null,
  "order": 1,
  "cmd": "launchBrowser",
  "element_name": null,
  "enabled": 1,
  "extra": {
    "browserType": "chrome",
    "windowVar": "browser"
  }
}
```

**映射规则：**

#### 3.1 cmd 映射

```
步骤描述 → JSON cmd 字段
中文描述 "打开浏览器" → launchBrowser
"点击XX"            → clickElement
"输入XX"            → inputElement
"获取文本"          → getText
"等待XX"            → waitForElement
"循环遍历XX"        → forEachElement
"条件判断"          → ifElementExists
"设置变量"          → setVar
...
```

#### 3.2 extra 映射

```
步骤参数  →  JSON params 中的对应字段

规则:
  - 参数名 = JSON params[].name
  - ⚠ 但 handler 侧真实读取名优先（见上方"已验证真值"）：
    forList 用 listVar 而非 JSON 声明的 listName
  - 值类型与 params[].type 匹配:
    · string/text   → 直接字符串，支持 {{var}}
    · boolean       → true/false
    · number        → 数字
    · select        → 必须是 options 中的 value
    · str-var       → 变量名字符串或 {{var}} 引用
    · element       → 元素名（与 element_name 字段配合）
  - required=true 的参数必须提供
  - group="output" 的参数值是变量名（引擎会创建/更新该变量）
  - setVar 必须带 valueType（见上方真值清单），计数器用 any-expr + "={{n}}+1"
  - 通用参数 onError/retryCount/timeout/description 可按需附加
```

#### 3.3 element_name 映射

```
步骤中 "操作元素: xxx" → node.element_name = "xxx"
"操作元素: 无"        → node.element_name = null
child 元素只能在 forEachElement 内部使用
```

#### 3.4 parent_id 映射

```
根节点:                   parent_id = null
容器(if/forEach/while)内: parent_id = 容器的 temp_id
else/catch 分支内:        parent_id = 对应 if/try 的 temp_id
结束标记:                 endLoop/endIf 是顶层兄弟节点（parent_id = null），
                          非容器子节点
```

#### 3.5 order 映射

```
同一 parent_id 下的节点按执行顺序递增: 1, 2, 3...
每个容器 body 内独立编号
elseBody 内独立编号
```

### 步骤 4：构建完整节点树

将所有步骤转为节点数组，确保：

```
□ 根节点列表中 launchBrowser 在第一位（browser 流程）
□ 容器节点 body 内的子节点 parent_id 正确指向容器
□ 有 elseBody 的 if 节点，else 分支 parent_id 也指向 if
□ 容器嵌套不超过 3 层（可维护性建议）
□ child 元素不出现在 forEachElement 外部
□ order 无重复、无跳号
□ closeBrowser 在最后（browser 流程）
□ extra 中 windowVar 引用一致
```

**节点数组示例：**

```json
[
  {
    "temp_id": "n1",
    "parent_id": null,
    "order": 1,
    "cmd": "launchBrowser",
    "element_name": null,
    "extra": {"browserType": "chrome", "windowVar": "browser"}
  },
  {
    "temp_id": "n2",
    "parent_id": null,
    "order": 2,
    "cmd": "navigate",
    "element_name": null,
    "extra": {"url": "https://example.com", "windowVar": "{{browser}}"}
  },
  {
    "temp_id": "n3",
    "parent_id": null,
    "order": 3,
    "cmd": "inputElement",
    "element_name": "search_input",
    "extra": {"text": "天气预报", "windowVar": "{{browser}}"}
  },
  {
    "temp_id": "n4",
    "parent_id": null,
    "order": 4,
    "cmd": "clickElement",
    "element_name": "search_btn",
    "extra": {"windowVar": "{{browser}}"}
  },
  {
    "temp_id": "n5",
    "parent_id": null,
    "order": 5,
    "cmd": "forEachElement",
    "element_name": "result_list",
    "extra": {"maxItems": 5, "windowVar": "{{browser}}"}
  },
  {
    "temp_id": "n5_1",
    "parent_id": "n5",
    "order": 1,
    "cmd": "getText",
    "element_name": "result_title",
    "extra": {"saveToVar": "title", "windowVar": "{{browser}}"}
  }
]
```

### 步骤 5：校验

生成节点数组后，逐项检查：

```bash
python -c "
import json, os

# 加载你的节点数组
nodes = json.loads('''[...]''')  # 替换为实际数据

# 加载命令注册表
cmd_registry = {}
for f in os.listdir('commands'):
    if not f.endswith('.json'): continue
    with open(f'commands/{f}', encoding='utf-8') as fp:
        d = json.load(fp)
    cmd_registry[d['cmd']] = d

errors = []

for i, n in enumerate(nodes):
    cmd = n.get('cmd','')
    if cmd not in cmd_registry:
        errors.append(f'节点{i}: 未知指令 {cmd}')
        continue
    
    schema = cmd_registry[cmd]
    schema_params = {p['name']: p for p in schema.get('params', [])}
    extra = n.get('extra', {})
    
    # 检查 required 参数
    for pname, pdef in schema_params.items():
        if pdef.get('required') and pname not in extra:
            errors.append(f'节点{i} ({cmd}): 缺少必需参数 {pname}')
    
    # 检查 select 值
    for k, v in extra.items():
        if k in schema_params:
            pdef = schema_params[k]
            if pdef.get('type') == 'select' and pdef.get('options'):
                valid = [o['value'] for o in pdef['options']]
                if v not in valid:
                    errors.append(f'节点{i} ({cmd}): {k}={v} 不在选项 {valid} 中')
    
    # 容器节点必须有子节点
    if schema.get('isContainer'):
        children = [c for c in nodes if c.get('parent_id') == n.get('temp_id')]
        if not children:
            errors.append(f'节点{i} ({cmd}): 容器节点缺少子节点')

if errors:
    print('校验失败:')
    for e in errors:
        print(f'  ✗ {e}')
else:
    print('校验通过')
"
```

### 步骤 6：写入数据库

```bash
# 1. 创建 Workflow
curl -X POST http://localhost:xxxx/api/workflows \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {token}" \
  -d '{
    "name": "流程名称",
    "description": "流程描述",
    "url": "https://target-url.com",
    "parameters": []
  }'
# 返回: {"id": 123, "name": "...", ...}

# 2. 批量写入节点
curl -X PUT http://localhost:xxxx/api/workflows/123/nodes/batch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {token}" \
  -d '[
    {"temp_id":"n1","parent_id":null,"order":1,"cmd":"launchBrowser",...},
    ...
  ]'
# batch API 自动：
#   - 将 temp_id 映射为数据库自增 id
#   - 修复 parent_id 引用（temp_id → 真实 id）
#   - 删除不在 payload 中的旧节点
```

### 步骤 7：强制验证（不可跳过）

生成的工作流必须真实运行一次并全部通过，才算完成。

**前置：**
- 后端已启动（dev 模式 :8000，使用仓库 `data/data.db`）
- 浏览器流程：扩展在线 —— `GET /api/extension/status` → `online:true`（扩展选项端口设为 8000）

**运行：**

```bash
python skills/scripts/run_workflow.py <wf_id>
```

**判定：**
- 输出 `failed=0` 且 `success=true` → 通过
- `failed>0` → 回到步骤 5 修正 extra/节点，重新写入后重跑，直到 `failed=0`
- 深度核对（可选）：`python skills/scripts/read_run.py <logDir>` 逐条查看 run.log

**与 command-test 的区别**：command-test 测试只记录问题不改代码；本 skill 发现问题直接修节点并重跑，直到通过。

## 常见映射参考

### 浏览器操作

| 自然语言 | cmd | extra 关键字段 |
|---------|-----|---------------|
| 打开XX浏览器 | `launchBrowser` | browserType, windowVar |
| 跳转到XXX | `navigate` | url, windowVar |
| 关闭浏览器 | `closeBrowser` | windowVar |
| 新建标签页 | `newTab` | url, windowVar |
| 切换到标签页 | `switchTab` | tabIndex, windowVar |

### 元素操作

| 自然语言 | cmd | extra 关键字段 |
|---------|-----|---------------|
| 点击XX | `clickElement` | windowVar |
| 在XX输入YY | `inputElement` | text, windowVar |
| 鼠标悬停XX | `hover` | windowVar |
| 等待XX出现 | `waitForElement` | timeout, windowVar |
| 滚动到XX | `scrollIntoView` | windowVar |

### 数据提取

| 自然语言 | cmd | extra 关键字段 |
|---------|-----|---------------|
| 获取XX的文本 | `getText` | saveToVar, windowVar |
| 获取XX的链接 | `getElementLink` | saveToVar, windowVar |
| 截图 | `takeScreenshot` | saveToVar, windowVar |

### 变量

| 自然语言 | cmd | extra 关键字段 |
|---------|-----|---------------|
| 设置变量XX=YY | `setVar` | varName, value |
| 打印/记录XX | `log` | message |

### 控制流

| 自然语言 | cmd | extra 关键字段 | 容器 |
|---------|-----|---------------|------|
| 如果XX存在则... | `ifElementExists` | — | ✅ 含 body/elseBody |
| 遍历XX列表 | `forEachElement` | maxItems | ✅ 含 body |
| 循环N次 | `forRange` | start, end, step | ✅ 含 body |
| 遍历列表变量 | `forList` | listVar, itemVar | ✅ 含 body（⚠ 参数名是 listVar，非 listName） |
| 当条件满足时循环 | `whileCondition` | conditionType, condition, maxIterations | ✅ 含 body（⚠ 必须设 maxIterations 防挂） |
| 跳出循环 | `break` | — | 必须在容器内 |
| 跳过本次循环 | `continue` | — | 必须在容器内 |

### 桌面操作

| 自然语言 | cmd | extra 关键字段 |
|---------|-----|---------------|
| 查找XX窗口 | `findWindow` | searchMode, windowTitle, resultVar |
| 打开XX应用 | `openApp` | appPath, windowVar |
| 点击XX控件 | `clickControl` | — |
| 向XX控件输入YY | `inputControl` | text |
| 按键XX | `sendKey` | key, modifiers |
| 等待N秒 | `wait` | seconds |

## 禁止行为

| 禁止 | 原因 |
|------|------|
| 跳过步骤 5 校验直接写入 | extra 字段错误会导致运行失败 |
| 容器节点无子节点 | 空容器运行无意义 |
| child 元素用在 forEachElement 外部 | child 元素依赖循环上下文 |
| temp_id 重复 | batch API 会覆盖 |
| windowVar 引用不一致 | 不同步骤引用不同变量名会导致路由错误 |
| 漏掉 launchBrowser | extension 指令需要浏览器上下文 |
