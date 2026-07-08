# 参数类型处理逻辑

## 命名规则

`运行时类型-编辑器控件`

| 拆开看 | 含义 |
|--------|------|
| 前半截 | handler 执行时拿到的 Python 类型 |
| 后半截 | 工作流编辑器中用什么控件填写 |

---

## 完整类型表

| 参数类型标识 | 运行时类型 | 编辑器控件 | `${}` | 处理流水线 | 失败兜底 |
|------------|:--------:|----------|:-----:|-----------|---------|
| `str-input` | `str` | 单行文本 | ✅ | `resolve_vars` | 字符串原文 |
| `str-textarea` | `str` | 多行文本 | ✅ | 同上 | 字符串原文 |
| `str-var` | `str` | 变量名输入 | ✅ | 同上 | 字符串原文 |
| `str-dropdown` | `str` | 下拉选择 | — | 控件直接写入，不经过 `${}` | — |
| `str-element` | `str` | 元素库选择 | — | 控件直接写入，不经过 `${}` | — |
| `int-number` | `int` | 数字输入 | ❌ | `int(float(值))` | `0` |
| `bool-check` | `bool` | 复选框 | ❌ | `"true"/"1"/"yes"` → True | `False` |
| `list-input` | `list` | 单行文本 | ✅ | `resolve_vars_json` → `json.loads` | `[]` |
| `dict-input` | `dict` | 单行文本 | ✅ | 同上 | `{}` |
| `any-expr` | 任意 | 代码编辑器 | ❌ | `eval(值, {}, vars)` | 原始文本 |
| `any-input` | 任意 | 单行文本 | ✅ | `resolve_vars` → `eval` → `json.loads` → 兜底 | 字符串 |

> **为什么 str-dropdown / str-element 没有 `${}` 列？**  
> 下拉框和元素库的值由编辑器直接写入 extra，用户没有机会在这个字段里输入 `${...}`，所以不经过变量替换。

---

## 各类型处理流程

### str-input / str-textarea / str-var

三者共享同一流水线，差异仅在编辑器控件外观。

```
用户填写的文本
    │
    ▼
resolve_vars(text, vars)        ← 扫描 ${var}，用 vars[var] 的值替换
    │                              变量不存在 → 保留 ${var} 原文
    ▼
返回字符串
```

**str-var 与 str-input 的区别**：

str-var 填的是**变量名**，后续 handler 用它去 `vars` 里取值；str-input 填的是**值本身**。

```
str-var 场景:  用户填 name1  → handler 执行 vars["name1"] → "张三"
str-input 场景: 用户填 ${name1} → resolve_vars 替换为 "张三" → handler 拿到 "张三"
```

---

### str-dropdown / str-element

```
编辑器控件选中值 → 直接写入 extra → handler 读取
```

不经过 `${}` 替换，因为用户只能从列表/元素库里选，没有输入框。

---

### int-number

```
用户填的数字字符串
    │
    ▼
有小数点？→ float(值) → int(截断)    例: "3.14" → 3.14 → 3
无小数点？→ int(值)                   例: "42"   → 42
    │
    ▼
失败 → 返回 0                        例: "abc"  → 0
```

> ⚠️ `"3.14"` 会先转 float 再截断为 `3`，不是四舍五入。如果填的不是数字（如 `"abc"`），静默返回 `0`。

---

### bool-check

```
"true" / "1" / "yes" → True
其他所有值          → False
```

---

### list-input

```
用户填写的模板  如: [${a}, ${b}]
    │
    ▼
resolve_vars_json(text, vars)   ← ${} 替换时自动处理各类型：
    │                              字符串  → json.dumps 加引号包裹
    │                              数字/布尔 → str() 不加引号
    │                              列表/字典 → json.dumps 序列化
    │                              变量不存在 → 保留 ${var} 原文
    ▼
["知乎", "如何学习", "内容"]
    │
    ▼
json.loads(上面)                ← 解析成 Python 列表
    │                              例: ["知乎", "如何学习", "内容"]
    ▼
返回 list

解析失败 → 返回 [] 并带警告
```

**为什么需要 resolve_vars_json？**

| 替换方式 | `${a}=知乎, ${b}=标题` 的结果 | JSON 合法？ |
|---------|---------------------------|:--------:|
| resolve_vars (str) | `[知乎, 标题]` | ❌ 值没引号 |
| resolve_vars_json | `["知乎", "标题"]` | ✅ |

**json.dumps 对不同 Python 类型的输出**：

| 变量类型 | 原值 | json.dumps 结果 |
|---------|------|----------------|
| 字符串 | `hello, world` | `"hello, world"` |
| 数字 | `42` | `42` |
| 布尔 | `True` | `true` |
| 列表 | `["a","b"]` | `["a","b"]` |
| 字典 | `{"k":"v"}` | `{"k":"v"}` |
| None | `None` | `null` |

**失败的例子**：

```
输入: [${name              ← 漏写右括号
替换后: ["张三"             ← 不完整 JSON
json.loads 失败 → 返回 []
```

---

### dict-input

流水线同 `list-input`，仅 `json.loads` 结果预期为 dict。失败返回 `{}`。

---

### any-expr

```
用户填的 Python 代码  如: keywords[0:3]
    │
    ▼
eval(值, {"__builtins__": {}}, vars)   ← 安全求值，可访问工作流变量
    │
    ▼
返回表达式结果。失败返回原始文本
```

**可用的内置函数**：`int`, `float`, `str`, `bool`, `len`, `abs`, `round`, `min`, `max`, `isinstance`

**示例**：
- `keywords[0:3]` → 取列表前 3 个元素
- `len(items) > 5` → `True` 或 `False`

> ⚠️ **安全注意**：eval 可执行任意 Python 表达式（如消耗内存的 `[0]*10**9`），且可访问当前所有工作流变量。仅限受信任的编辑器环境使用。

---

### any-input

```
用户填写的值  如: ${v} 或 [1,2,3] 或 true
    │
    ▼
resolve_vars(text, vars)         ← ① 先 ${} 替换
    │
    ├─ eval(值, {}, vars)         ← ② 尝试 Python 表达式
    │     成功 → 返回结果
    │
    ├─ json.loads(值)             ← ③ 尝试 JSON 解析
    │     成功 → 返回结果
    │
    └─ 返回 resolved              ← ④ 兜底：当字符串
```

**为什么 eval 优先于 JSON？**

因为 `${var}` 替换后，变量值已经内嵌在文本里，eval 可以直接当 Python 字面量识别（如 `True`、`[1,2]`）。JSON 只在 eval 失败后兜底。如果用户想确保字符串不被 eval 误判，可用引号包裹：`"${v}"`。

**示例**：

| 输入 | `${}` 后 | eval | JSON | 最终 |
|------|---------|:--:|:----:|------|
| `[1,2,3]` | — | ✅ → `[1,2,3]` | — | `list` |
| `true` | — | ✅ → `True` | — | `bool` |
| `${name}` | `"张三"` | — | ✅ → `"张三"` | `str` |
| `hello` | `hello` | ❌ | ❌ | `"hello"` |

---

## 变量替换函数对比

| 函数 | 用在 | 字符串值 | 数字/布尔 | 列表/字典 | 变量不存在 |
|------|------|---------|----------|----------|----------|
| `resolve_vars` | str-*, any-input | `str(值)` → `hello` | `str(值)` → `42` | `str(值)` → `['a','b']` | 保留 `${var}` |
| `resolve_vars_json` | list-input, dict-input | `json.dumps(值)` → `"hello"` | `str(值)` → `42` | `json.dumps(值)` → `["a","b"]` | 保留 `${var}` |

核心区别：`str("hello")` = `hello`（无引号），`json.dumps("hello")` = `"hello"`（有引号，JSON 安全）。
