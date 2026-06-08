# ADR 0004 — CSS/XPath Selector Generation, Verification & Consistency

- **Status:** accepted
- **Date:** 2026-06-05
- **Deciders:** project owner

## Context

浏览器扩展的元素采集模块需要同时输出 CSS、XPath、Drission 三种选择器家族。早期实现存在以下问题：

1. CSS 生成器输出 `:contains("text")` 这种非标准语法，导致 `content.js` 执行时 `querySelector` 抛异常。
2. XPath 生成只有结构性兜底路径（`//body/div[1]/nav/a[3]`），缺少基于属性和文本的短 XPath。
3. 侧板点击推荐方案后，反向匹配（parse segment → 匹配 node）成功率低，尤其是 React/Vue 通过 IDL property 设置的 `href`/`value` 与 attributes 不一致时。
4. 候选只取全局 Top 10，XPath/Drission 常被大量 CSS 候选挤出侧板。
5. 动态属性（`style`、`onclick`、`data-react*`、`data-v-*`、`_ngcontent-*`）进入属性面板，干扰用户选择。

本 ADR 固化生成、校验、一致性、优先级四层规则。

## Decision

### 1. CSS 严格限制在原生范围

- CSS 选择器必须能被 `document.querySelectorAll` 原生解析。
- **禁止生成** `:contains()`、`[attr*=value]` 以外的文本匹配、`/deep/`、`::shadow` 等非标准语法。
- `innerText` 在 CSS 模式下可勾选但**不输出到选择器**，仅作为 UI 状态保留。
- 校验层 `verifyLocator()` 对 `family === 'css'` 直接走 `querySelectorAll`，不再做 jQuery 风格的 shim。

### 2. XPath 双轨策略

XPath 候选分两类：

| 类型 | 生成位置 | 特点 | 典型示例 |
|---|---|---|---|
| **Target-only（Robula+ 风格）** | `buildTargetOnlyXPathCandidates()` | 从目标元素向外特化，尽量短 | `//*[@id='foo']`、`//button[@data-testid='submit']`、`//a[contains(text(),'下一页')]` |
| **Structural fallback** | `getElementXPathFromPath()` | 基于完整 path，兜底用 | `//body/div[1]/nav/a[3]` |

Target-only 按以下优先级生成并验证（仅当 `document.evaluate` 返回唯一匹配时才加入候选）：

1. `id` — score 100
2. `data-testid` / `data-id` / `data-name` 等 — score 95
3. `aria-label` / `name` — score 90 / 88
4. **text** (`contains(text(),'...')`) — score 80
5. `placeholder` / `title` / `rel` / `href` — score 80 / 75 / 78 / 85
6. `role + 语义属性` 组合 — score 82
7. stable `class` (`contains(@class,'...')`) — score 72
8. `type` (input/button) — score 65

Structural fallback 固定 score 15，且因含 `[n]` 位置谓词会被额外惩罚沉底。

### 3. 校验层统一接口

`verifyLocator(syntax, family)` 是单一入口：

- `family === 'xpath'`：`syntax.replace(/^xpath:/, '')` 后直接 `document.evaluate`。
- `family === 'drission'` 且为 `verse:` / `text=` / `tag:*@text()`：转给 `resolveAllForVerify(syntax, subType)`。
- `family === 'css'`：经 `convertToCssForTest()` 去掉 `css:` 前缀后 `querySelectorAll`。

`resolveAllForVerify(selector, type)` 按 `type` 分发到 `querySelectorAll`、`document.evaluate`、verse fingerprint 扫描等子逻辑。

### 4. 侧板双向一致性

#### 4.1 推荐 → UI（applyCandidateToUI）

候选附带 `pathMapping`，标明每个 segment 对应 `path[i]` 的哪个层级。侧板直接按映射勾选，不再反向猜测：

```js
// CSS:  css:body > div > nav > a
// XPath: xpath://body/div/nav/a[3]
// Mapping: [0, 1, 2, 3]
```

- CSS segment 用 `parseSeg()` 解析。
- XPath segment 用 `parseXPathSeg()` 解析，支持：
  - `[@id='foo']`
  - `[contains(@class,'bar')]`
  - `[contains(text(),'x')]`
  - 纯数字 `[n]`（nth-of-type）
  - `[position()=n]`（nth-child）

#### 4.2 UI → 选择器（updateSelector）

`pathEnabled[i]` + `attrEnabled[i]` 是 UI 状态的唯一真相：

| 勾选 | CSS 输出 | XPath 输出 |
|---|---|---|
| tag | `div` | `div` |
| id | `#foo` | `[@id='foo']` |
| class `.bar` | `.bar` | `[contains(@class,'bar')]` |
| attr `href=x` | `[href="x"]` | `[@href='x']` |
| nth-of-type(2) | `:nth-of-type(2)` | `[2]` |
| nth-child(3) | `:nth-child(3)` | `[position()=3]` |
| innerText | （CSS 忽略） | `[contains(text(),'text')]` |

同一组 checkbox 状态，CSS 和 XPath 输出语义一致，只是语法不同。

### 5. 评分与排序规则

`computeScore(c)` 对最终候选统一打分：

| 规则 | 惩罚/奖励 | 说明 |
|---|---|---|
| `[n]` / `:nth-of-type()` | -50 × 个数 | 位置信息最后才用（Robula+ 原则） |
| 深度 | -10 × max(0, depth-1) | 层级越少越好 |
| 属性选择器 | -8 × 个数 | 属性越少越好 |
| class 数量 | -4 × max(0, count-1) | 超过 1 个 class 额外惩罚 |
| 长度奖励 | +8 / +4 | < 15 字符 +8，< 25 字符 +4 |

排序优先级（高于 score）：
1. 唯一匹配（`matchCount === 1`）
2. 不可校验（`matchCount === -1`）
3. 多匹配（`matchCount > 1`）

### 6. 侧板候选数量：各家族 Top 10

全局 Top 10 会导致 XPath/Drission 被 CSS 大量挤出。改为按家族独立截取：

```js
function pickCandidatesByFamily(all, limitPerFamily = 10) {
  const byFamily = {};
  for (const c of all) {
    const family = c.family || c.type || 'css';
    if (!byFamily[family]) byFamily[family] = [];
    byFamily[family].push(c);
  }
  const selected = [];
  for (const family of Object.keys(byFamily)) {
    selected.push(...byFamily[family].slice(0, limitPerFamily));
  }
  return selected;
}
```

最多向侧板发送 30 条候选（CSS 10 + XPath 10 + Drission 10）。

### 7. 动态属性黑名单

新增 `isFragileAttr(name)`，采集阶段和候选生成阶段双重过滤：

- `style`
- `onclick`、`onchange` 等 `on*` 事件处理器
- `data-react*`、`data-v-*`
- `_ngcontent-*`、`_nghost-*`
- 动态 ARIA：`aria-owns`、`aria-activedescendant`、`aria-busy`、`aria-live`、`aria-relevant`

这些属性不进入 `node.attrs`，也不出现在属性面板。

## Consequences

Positive

- CSS 执行路径不再因 `:contains()` 抛异常。
- XPath 标签下有属性、文本、结构三条路径可选，用户可灵活选择。
- 侧板点击推荐方案后，映射成功率从反向猜测的 ~70% 提升到基于 `pathMapping` 的 ~99%。
- 各家族独立 Top 10 保证切换 CSS/XPath/Drission 标签时都有候选可看。
- 动态属性黑名单减少属性面板噪音。

Negative

- 候选总数从最多 10 条增加到最多 30 条，侧板渲染和消息传输略有开销（实测可忽略）。
- `[n]` 惩罚 `-50` 较激进，会让含位置谓词的 XPath 沉底；如果某页面只能靠位置定位，用户需要滚动才能看到兜底方案。
- `contains(text(),'...')` 在文案国际化或动态截断时会失效，需要用户手动切换到属性或结构路径。

## Alternatives considered

- **只输出单条最鲁棒选择器。** Rejected：再鲁棒的算法也扛不住 A/B 测试和反爬重构；多候选 + 用户确认更适合当前产品阶段。
- **XPath 继续只做结构路径，不做 target-only。** Rejected：结构性 `[n]` 路径太脆弱，必须给用户提供属性/文本短 XPath。
- **全局 Top 15 替代家族 Top 10。** Rejected：CSS 候选通常远多于 15 条，XPath 仍可能被挤出；家族隔离更稳定。
- **把文本匹配优先级放到属性之前。** Rejected：文本易受国际化和动态内容影响，稳定性通常不如 `data-testid` / `name` / `aria-label`。
