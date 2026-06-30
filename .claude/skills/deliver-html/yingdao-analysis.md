# 影刀 RPA 浏览器插件 (v3.1.0.0) 架构分析

## 1. 整体架构

影刀插件采用 **Manifest V3** 架构，核心由三部分组成：

| 组件 | 文件 | 职责 |
|------|------|------|
| **Service Worker** | `BackgroundServiceWorker.js` (3028行) | 事件驱动的主逻辑、CDP 通信、Native Messaging |
| **Background Page** | `BackgroundPage.html` + `Background.Static.js` (2522行) | 保持长连接、桥接本地应用 |
| **Content Script** | `Content.Static.js` (21行) | 极简 dispatch，把调用转发给 Background |

**关键设计：Service Worker + Background Page 双架构**

Manifest V3 的 Service Worker 有 **5 分钟休眠**限制。影刀的解决方案是同时维护一个 Background Page（持久页面），通过它来维持与本地应用的 Native Messaging 长连接。SW 负责事件响应，Background Page 负责状态保持。

---

## 2. 权限模型（全量获取）

```json
[
  "cookies", "management", "tabs", "debugger",
  "nativeMessaging", "webNavigation", "downloads",
  "clipboardRead", "clipboardWrite", "scripting", "storage"
]
```

| 权限 | 用途 |
|------|------|
| `debugger` | **CDP 直接控制浏览器**（Runtime/Page/DOM/Input/Network 域） |
| `nativeMessaging` | 与影刀桌面端建立持久管道 |
| `scripting` | 在任意页面注入执行 JS |
| `webNavigation` | 监听页面导航、获取所有 frame |
| `downloads` | 管理下载行为 |
| `clipboardRead/Write` | 读写剪贴板 |
| `cookies` | 跨域 Cookie 操作 |

---

## 3. 核心技术栈

### 3.1 Chrome DevTools Protocol (CDP)

通过 `chrome.debugger` API 直接 attach 到目标 tab，使用 CDP 命令操控浏览器：

- **Runtime** (106次引用) — 在页面执行 JS、获取返回值
- **Page** (68次引用) — 页面导航、截图、打印
- **Debugger** (62次引用) — 断点、代码注入
- **Target** (52次引用) — 多标签/多窗口管理
- **Input** — 模拟键盘鼠标输入
- **DOM** — 元素查询、属性获取

> 影刀不依赖 Content Script 做 DOM 操作，而是通过 CDP 直接控制页面，这让它能穿透 shadow DOM、iframe、跨域限制。

### 3.2 Native Messaging

```
影刀桌面端 ←→ chrome.runtime.connectNative() ←→ Background Page
```

- `connectNative` 建立命名管道
- `postMessage` / `onMessage` 双向通信
- `onDisconnect` 处理断连重连

桌面端通过这条管道发送指令（点击、输入、获取元素），插件翻译为 CDP 命令执行。

### 3.3 Content Script 极简设计

```javascript
function invoke(method, params) {
    if (method === 'init') {
        return { status: 'success' }
    } else {
        if (uiaDispatcher.version != params.contentVersion) {
            return { status: 'needInit' }
        } else {
            return uiaDispatcher.invoke(method, params)
        }
    }
}
```

只有 21 行。核心逻辑全在 Background，Content Script 只做**版本检查**和**调用转发**。

---

## 4. 功能模块

### 4.1 窗口与标签管理
- `chrome.windows.getAll` / `chrome.windows.create` / `chrome.windows.update`
- `chrome.tabs.query` / `chrome.tabs.reload` / `chrome.tabs.get`
- 监听 `tabs.onUpdated` / `tabs.onActivated` / `windows.onCreated` / `windows.onRemoved`

### 4.2 元素定位与操作
- 通过 CDP `Runtime.evaluate` 在页面执行选择器查询
- 支持 xpath / css selector / 文本匹配
- `chrome.webNavigation.getAllFrames` 获取嵌套 iframe 结构
- 处理了 shadow DOM（代码中出现 `shadow` 关键字）

### 4.3 输入模拟
- CDP `Input.dispatchMouseEvent` / `Input.dispatchKeyEvent`
- 不依赖元素触发事件，而是直接发送底层输入事件（更真实，反检测能力更强）

### 4.4 Cookie 与下载
- `chrome.cookies.getAllCookieStores` — 获取所有 Cookie 存储
- `chrome.downloads.search` — 查询下载状态

### 4.5 剪贴板
- `clipboardRead` / `clipboardWrite` — 直接读写系统剪贴板

---

## 5. 可借鉴的设计

<div class="card good">
<strong>1. Service Worker + Background Page 双架构</strong><br>
Manifest V3 下保持长连接的标准解法。我们的扩展目前只有 Content Script，可以借鉴这个模式来支持持久通信。
</div>

<div class="card good">
<strong>2. CDP 优先，DOM 次之</strong><br>
影刀的核心操作都走 CDP 而非 Content Script DOM API。CDP 能穿透 iframe/shadow DOM、跨域、甚至操作还没渲染出来的元素。我们目前用 DrissionPage 的 `ele()` / `eles()`，本质也是 CDP 封装，方向一致。
</div>

<div class="card good">
<strong>3. 输入模拟走底层 Input 事件</strong><br>
`Input.dispatchMouseEvent` 比 `element.click()` 更难被检测为自动化。DrissionPage 的 `click()` 内部也是走 CDP Input 域，这一点我们已经对齐。
</div>

<div class="card info">
<strong>4. 全量权限策略</strong><br>
影刀申请了几乎所有可用权限。我们的扩展目前权限较保守，如果未来需要支持下载、剪贴板、跨域 Cookie 等场景，可以参考这个清单补全。
</div>

<div class="card warn">
<strong>5. Content Script 只做 dispatch</strong><br>
21 行的 Content Script 是一个好设计——越薄越好，核心逻辑集中在 Background。我们当前的扩展如果 Content Script 里放太多逻辑，可以考虑抽薄。
</div>

---

## 6. 与现有架构的对比

| 维度 | 影刀插件 | 我们的 rpa_script |
|------|----------|-------------------|
| 浏览器控制 | CDP (debugger API) | DrissionPage (CDP 封装) |
| 元素定位 | Runtime.evaluate + 自定义选择器 | DrissionPage 内置选择器 |
| 输入模拟 | Input.dispatchMouseEvent/KeyEvent | DrissionPage 底层封装 |
| 本地通信 | Native Messaging (命名管道) | 子进程 (`subprocess.run`) |
| 跨 iframe | webNavigation.getAllFrames + CDP | DrissionPage 自动处理 |
| 扩展架构 | SW + Background Page + Content Script | 无扩展，纯后端驱动 |
| 页面注入 | scripting.executeScript | 无（直接操作浏览器） |

---

## 7. 结论与建议

影刀插件的核心优势在于**浏览器扩展层与桌面应用层的紧密耦合**——扩展作为"代理"，把桌面端的指令翻译成 CDP 命令执行。

我们的架构（FastAPI + DrissionPage）是**后端直接驱动浏览器**，不经过扩展层，路径更短、延迟更低，但缺少了一些扩展层能做的事：

1. **监听页面事件**（导航、弹窗、下载开始）— 需要扩展
2. **跨域 Cookie 操作** — 需要扩展的 `cookies` API
3. **剪贴板读写** — 需要扩展的 `clipboard` 权限
4. **多浏览器实例管理** — 影刀通过扩展可以同时 attach 多个浏览器

**建议**：
- 当前阶段：继续用 DrissionPage 直接驱动，路径最短
- 中期：如果需要监听页面事件或跨域操作，可以借鉴影刀的"扩展作为 CDP 代理"模式，把扩展做成轻量级命令转发层
- 长期：如果支持多浏览器并发或多用户隔离，扩展层的窗口/标签管理能力会有价值
