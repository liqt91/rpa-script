# 网页元素 UIA 捕获与定位 —— 技术方案

> 日期：2026-08-18　状态：待评审（不改代码，先对齐）
> 背景：自研 capture_gui 已能用 UIA 无障碍树框选/捕获网页元素（零扩展/零后端/CDP），
> 但「写入」有解析问题——网页元素存成了 UIA 格式，而系统只认 CSS/XPath 定位器。
> 用户提出三个探讨：① UIA 能否转 CSS/XPath；② 为何自己的工具比 tdSelector 框选范围大；
> ③ 插件捕获是否必须 WebSocket，有没有更优雅的解耦。

---

## 先直接回答三个问题

### Q1：UIA 捕获的网页元素，能否转成 CSS / XPath？

**能。** 而且不止 CSS/XPath，标准属性选择器（`[role]`、`[aria-label]`、`[name]`）也能推导。
关键依据：Chromium 把每个 DOM 节点暴露为 UIA 无障碍树元素，且字段与 DOM 是**可逆映射**：

| UIA 字段（`_uia_node_dict` 已读） | 对应 DOM 语义 | 可生成的选择器 |
|---|---|---|
| `ClassName` | CSS class（空格分隔） | `.card.banner` |
| `AutomationId` | DOM `id` / 生成的可访问 id | `#kw` |
| `ControlTypeName` | ARIA role 映射（Edit/Button/Link/…） | `input` / `button` / `a`（tag） |
| `Name` | 可访问名称（可见文本 / aria-label） | `:has-text()`、`[aria-label=...]` |
| 兄弟 `index` | 同父亲兄弟序号 | `:nth-of-type(n)` / 位置 xpath |
| companion 的 `AriaRole` / `AriaProperties` | `role` / `aria-*` 属性 | `[role]`、`[aria-checked]`、`[name]` |

**限制（重要、如实说明）**：UIA 树是「可访问性树」的 Windows 投影，只暴露**有可访问语义的节点**。
纯视觉 `<div>`（无 role / 无可访问名 / 不可聚焦 / aria-hidden / 屏幕外）会在树里缺失或被过滤，
这类节点就**没有** CSS/XPath 可派生 → 只能 fallback 到：
- 最近一个有语义的祖先（div 内联进祖先选择器，as text）
- 兄弟序号 / 位置
- 图像兜底（现有的 region+截图模板）

tdSelector 同样是这个限制（它也没办法从 UIA 拿到纯 div 的语义选择器）。

> **当前 bug 的根因**：overlay.py `_build_element_info` 的 web 分支把 `css_selector=""`、`xpath=""`、
> `candidates=[]` 硬编码为空（注释「UIA 拿不到 CSS/XPath」——这个注释是**错的**，实则拿得到，只是没写推导）。
> 结果存储后 `normalize_element_capture` 的 web 分支产出 `web_selector=""` → 一个「有 DOM 链、无定位器」的
> 幽灵元素，运行时无法按 CSS/XPath 定位。修复点就落在这里。

---

### Q2：为什么自己的工具比 tdSelector 框选范围大？

**根因已定位到一行短路**。overlay.py 的 hover 高亮路径 `_uia_hit_rect`（第 1078 行附近）：

```python
if hwnd and _is_browserish_hwnd(hwnd):
    return None, None   # ← 浏览器窗口直接放弃 UIA，hover 框整窗
```

以及 `_uia_hit_rect` 里「命中≈整窗 → 深搜」的分支对浏览器窗口也直接接受整窗。

于是 **hover 时**整条路径对浏览器返回空 → 主循环 `_get_best_rect` 回退到 Win32 整窗矩形 → 你看到「只能框更大范围」。

而只有 **Alt+点击真正捕获**时才走 `_build_element_info` → `_uia_web_capture` → `_uia_web_dom_at` 深搜，
说明捕获功能其实已经能下钻到小元素（你验证了「能框选并捕获」）。

> tdSelector hover 时同样实时沿 DOM 无障碍树下钻，所以框的就是小叶子。**我们没有对浏览器窗口做这步**，且 `_is_web_dom_node` 的 `_WEB_DOM_ROLES` 白名单在 hover 路径根本没参与。

**修复方向**：让 hover 路径对浏览器窗口也做「含光标优先的 DOM 深搜」，用紧的 `max_nodes` 预算保证流畅
（复用 `_HoverWorker` 常驻线程，不阻塞主循环）。这正是用户说的「可以 1 试下」。

---

### Q3：插件捕获必须 WebSocket 吗？有没有更优雅的解耦？

**自建 WebSocket 不是唯一选择，CDP 才是「更优雅 + 最小模型」。**

浏览器扩展能用的 IPC 本质只有三种：
1. **storage 事件**（`chrome.storage.onChanged`）——本地广播，无需自建服务，但**仅限同源扩展内**，后端拿不到。
2. **自建 WebSocket / 长轮询**——需要自己起 WS server，正是当前路径（`src/runtime/.../ws`），耦合在「谁当心跳谁重连」。
3. **CDP（Chrome DevTools Protocol）**——浏览器**自带**一个 WebSocket 服务（`/json` 发现 + `webSocketDebuggerUrl`），无需自建 WS、无需扩展重连心跳。通过 `DOM`/`Runtime` 域能拿到**真实 DOM 结构与 CSS/XPath**（含 shadow DOM、类名、id、文本路径）。

**CDP 即为「最小可测模型」**：起一个带 `--remote-debugging-port=9222` 的 Edge/Chrome，
`GET http://127.0.0.1:9222/json` 拿 target，连 `webSocketDebuggerUrl`，发一条
`Runtime.evaluate`（跑 `getCssPath(el)` / `document.elementsFromPoint(x,y)`）就能拿到真选择器。
**这不需要写一行扩展代码、不需要自建 WS server**——直接验证 CDP 这一端的能力。

**推荐的分层（解耦，按优先级回退）**：
1. **本地 UIA（已能用）**——零依赖，覆盖绝大多数「有语义」的网页控件；写入时补上 CSS/XPath 推导（Q1）。
2. **CDP（新增）**——页面级真 DOM 选择、shadow DOM、elementFromPoint 命中；浏览器自带通道，解耦最干净。
3. **扩展（保留但降级为「可选增强」）**——仅当需要页内注入 / 拦截 / 特殊控件时才启用；不再依赖它做基础捕获。

> tdSelector 本身就是这个思路的现成例证：它在 Windows 端用 `uiautomationExt`（=我们的本地 UIA），
> 又内置整套 **Playwright 驱动**（`playwrightExt`）通过浏览器自动化拿真实 DOM 选择器——两者并存、按需回退。

---

## 数据格式：网页元素到底该存什么

目标：写入后 `normalize_element_capture` 能产出**非空 `web_selector`**，运行时可直接 CSS/XPath 定位，
同时保留 DOM 链 + 图像兜底作为降级。建议 UIA 网页捕获改为产出：

```jsonc
{
  "element_type": "web",
  "name": "搜索框",
  "css_selector": "css:input#kw",
  "xpath": "xpath://input[@id='kw']",
  "candidates": [
    {"family": "css",  "syntax": "css:input#kw",           "score": 90},
    {"family": "css",  "syntax": "css:.s-input-text",      "score": 70},
    {"family": "xpath","syntax": "xpath://input[@id='kw']","score": 85}
  ],
  "dom_path": [ /* UIA 根→目标 的链，供 debug/复核 */ ],
  "elem_attrs": { "role": "textbox", "aria_label": "搜索", "tag": "input" },
  "page_url": "...",
  "region": { /* 图像兜底 */ },
  "threshold": 0.8
}
```

`candidates` 与现有 `css_candidates / xpath_candidates / drission_candidates` 完全兼容
（`_partition_candidates` 已按 family 分类）。存储后 `web_selector` 非空 → 走 `css:input#kw`。
`elem_attrs` 保留 UIA/DOM 特征，必要时运行时可用 `[role]` / `[aria-label]` 补充定位。
`dom_path` 仅作调试参考（运行时不用它做定位主路径，避免又引入 UIA 解析指令）。

---

## 关键改动点（评审通过后再动手）

### A. UIA→选择器生成器（新增 `_uia_dom_selector.py` 或并入 overlay）
输入一棵 DOM 无障碍子链（name/class/automation_id/control_type/index），输出候选列表：
- 优先：`AutomationId` → `#id`；`ClassName` → `.a.b`；tag（由 control_type 映射 + 可选 role）。
- 组合语义：`tag#id`、`tag.class`、`tag[role]`、`tag[aria-label]`。
- 兄弟 `index` → `:nth-of-type(n)` / 位置 xpath。
- 打分排序：唯一性越高（id > 类 > 角色）分越高；返回 top N 存 `candidates`。

### B. 修 `_build_element_info` web 分支（写入 bug）
把 `css_selector=""` 硬编码改为调生成器，填 `css_selector`/`xpath`/`candidates`/`elem_attrs`。
顺带修存储端 `_dict_to_info`/`store.py` 已有字段（`candidates`/`dom_path`/`elem_attrs` 已存在，正常落入）。

### C. hover 细化（Q2）
去掉 `_uia_hit_rect` 里「浏览器窗口短路 + 整窗接受」两处，对浏览器走 `_uia_web_dom_at`
的含点下钻（紧 `max_nodes`），并让 hover 高亮用深搜返回的细矩形。接入现有 `_HoverWorker` 常驻线程。

### D. 分层捕获抽象（Q3，可选分步）
- 现状：UIA（本地）→ 扩展 fallback。
- 目标：UIA（本地）→ **CDP（新增，浏览器自带通道）** → 扩展（保留，可选增强）。
  CDP 端做「elementFromPoint + getCssPath 注入」，产出与 A 同构的 candidates。

---

## 验收

1. capture_gui 框选网页输入框 → 写入后 `web_selector` 非空（`css:input#kw` 之类），且用扩展指令能按它点击/输入。
2. hover 网页时能框到小元素（与 tdSelector 观感一致），Alt+点击捕获即所见。
3. 无扩展、关后端、不开 CDP 端口时，仅本地 UIA 即可捕获并完成一次网页自动化（图像兜底兜底）。
4. 网页元素的 CSS/XPath `candidates` 在元素库面板可查看/可编辑选择。

---
**状态更新（2026-08-19）：A 已完成 + 路线 B 决策落地**

## 实测验证（UIA→CSS/XPath 可行性已确认）

`probe_uia_web.py` 在 Edge 上连续捕获多类控件，覆盖矩阵：

| 控件 | control_type | 生成选择器 | 质量 |
|---|---|---|---|
| 搜索输入框 | EditControl | `#search-input` / `//*[@id='search-input']` | 🟢 id+role/class/aria 多候选 |
| 筛选容器 | GroupControl | `section.filter.active` | 🟢 双 class 精确 |
| 顶部容器 | GroupControl | `section.ai-header-container.compact.with-side-bar-collapse` | 🟢 多 class |
| 导航按钮「主页」 | ButtonControl | `#view_1004` | 🟢 id |
| 纯视觉 div | GroupControl | 空 | 🔴 无定位线索 → 图像/父级兜底 |

结论：交互控件（input/button/link）都能转出高可用选择器；纯视觉容器无语义 → 预期边界，与 tdSelector 一致。
**网页捕获可以不依赖扩展。**

## 路线决策：元素编辑做在「流程编辑器」（路线 B）

评估两条路后选 B（用户确认）：
- 路线 A（改造 GUI 对齐 tdSelector）代价大：tkinter 做层级树/属性勾选吃力，且元素库两套并存割裂。
- 路线 B（流程编辑器内嵌编辑）：捕获产物选择器生成已在 overlay 层，前端直接消费 `candidates`；项目模式写目录 + 运行时读目录已闭环；React 做推荐方案 UI 优于 tkinter；GUI 保留为独立工具。

**关键发现：前端骨架（CaptureToolModal）早已存在**——`desktop_mask` 一直走本地遮罩，
overlay 的选择器生成恰好补上它消费的 `candidates`。三块（前端 UI + overlay 生成 + 后端 normalize）已互相对齐。

## 闭环数据契约（已验证）

`capture_once(desktop_mask) → normalize_element_capture → 目录 workflow.json`：

```
web_selector      : '#search-input'（非空 —— 原"写入解析问题"根因已解决）
css_candidates    : [css:#search-input(100), css:[role=textbox].textarea(61)]
xpath_candidates  : [xpath://*[@id='search-input'], ...]
element_type      : web
```

前端 bundle（`index-CFdxP9DV.js`）已含推荐方案/desktop_mask/projectSaveElement，
profile 插件 static 的 index.html 与其一致；dsh web `/rpa-editor/` 服务即最新版。

## 待办（需用户实测闭环）

流程编辑器实际走一遍：捕获网页元素 → 推荐方案选选 → 保存 → 元素库可见 → 流程运行按选择器定位。

---

## 关联
- 代码：`scripts/capture_gui/overlay.py`（_build_element_info / _uia_web_dom_at / _uia_web_capture）、`scripts/capture_gui/web_selector.py`（选择器生成）
- 存储：`scripts/capture_gui/store.py`；`src/service/elements_service.py::normalize_element_capture`；`src/runtime/routers/project_router.py`
- 前端：`src/ui/workflow-editor/src/components/CaptureToolModal.jsx`（推荐方案/手动编辑/保存）
- 参照实现：`tdSelector_1.2.7/`（uiautomationExt + 内置 Playwright 驱动）

