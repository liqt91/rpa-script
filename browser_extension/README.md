# 操作编排器 - 浏览器扩展

将原来 `elements_gen.py` 的注入式操作编排功能，改为 Chrome/Edge 浏览器扩展实现。
无需 Python / DrissionPage 环境，安装扩展后即可在任何网页上使用。

## 功能

- **Alt 模态化捕获** — 平时浏览正常,按住 Alt 鼠标 hover 才高亮元素 + 生成候选 locator
- **DrissionPage 风格 locator** — 自动生成 id/data-attr/aria/text/tag+text/class/xpath 等多种候选,带稳定性评分 + 实时命中数验证
- **Alt + click / Alt + 1 录入** — 一键弹出录入对话框,集中填:元素名、描述、locator 选择、method(ele/eles/s_ele/s_eles)、action(click/getText/input/getAttr/hover/findWithin/waitFor/custom) + action 参数 + 是否同时保存到元素库
- **元素库 + 完整特征** — 保存元素时同时存 tag/id/classes/attrs/direct_text/inner_text/outer_html 等所有特征,以备后期"找回"或重新生成更好的 locator
- **步骤管理** — 调整顺序、删除步骤、单步覆盖 method
- **导出 JSON** — 结构化数据,含完整 locator/method/candidates/features,可复制给程序使用
- **导出自然语言** — 生成 DrissionPage 风格的描述(`tab.ele('@data-testid=xxx').click()`),粘贴给 AI 生成代码
- **数据持久化** — 使用 Chrome 扩展存储,关闭浏览器后数据不丢失

## 安装步骤

### 1. 生成图标(已生成则跳过)

```bash
python generate_icons.py
```

### 2. 加载到 Chrome / Edge

1. 打开 Chrome,地址栏输入 `chrome://extensions/`
2. 右上角打开 **开发者模式**
3. 点击 **加载已解压的扩展程序**
4. 选择本目录 `browser_extension/`
5. 安装完成,工具栏会出现扩展图标

## 使用方式

### 方式一:点击扩展图标

点击浏览器工具栏的扩展图标,弹出控制面板:
- **启动面板** — 在当前页面显示操作编排器浮动面板(平时不打扰浏览)
- **导出 JSON / 自然语言** — 快速导出当前录制的步骤
- **清空步骤 / 清空全部** — 清理数据

### 方式二:键盘快捷键

- `Ctrl+Shift+O` — 切换扩展弹窗(可点击启动面板)

### 方式三:Alt 模态化捕获(主要工作流)

启动面板后,页面右上角出现浮动操作编排器(仅显示步骤列表 + 导出按钮,不干扰浏览)。

| 操作 | 效果 |
|------|------|
| 按住 `Alt` | 进入捕获模式,鼠标 hover 元素显示红框高亮 + 顶部锁定提示 |
| `Alt` + 鼠标点击元素 | 拦截原 click,弹出录入对话框 |
| `Alt` + `1` | 基于当前 hover 元素弹出录入对话框 |
| `Alt` + `E` | 导出自然语言 |
| `Alt` + `J` | 导出 JSON |
| 松开 `Alt` | 粘性保持,直到鼠标离开锁定元素或对话框关闭 |
| `Esc` | 关闭对话框(无对话框时关闭面板) |

录入对话框字段:
- **元素名** / **描述**:自然语言,可选
- **定位 (locator)**:从候选 radio 列表中选,实时高亮命中元素
- **method**:`ele()` / `eles()` / `s_ele()` / `s_eles()`,默认继承上次
- **action**:`click` / `getText` / `input` / `getAttr` / `hover` / `findWithin` / `waitFor` / `custom`
- **action 参数**:根据 action 动态显示(input 的文本、waitFor 的秒数等)
- **同时保存到元素库**:勾选后这个元素以完整特征存入库,跨流程复用
- **切换手动模式**(disabled,v0.3 支持):未来用于手写 DrissionPage 高级语法 (`@!` / `@|` / `:` / `^` / `$` / `@@text()`)

## 已知限制

- **iframe 内元素**:Alt+click 在顶层 document 注册,iframe 内的点击事件无法被拦截。如需处理 iframe,v0.3 待支持
- **shadow DOM 内元素**:同上,因为顶层 document 看不到 shadow 内事件
- **Alt 单按激活浏览器菜单栏**:面板打开时被插件拦截(防止 Alt 时菜单栏抢焦点)— 关闭面板后恢复正常
- **DrissionPage 高级语法**:当前只生成 `=` 精确匹配,模糊/开头/结尾(`:`/`^`/`$`)、否定(`@!`)、或(`@|`)、子树文本(`@@text()`)需手动写,v0.3 提供构造器

## 与原 Python 版的差异

| 对比项 | Python 版 (`elements_gen.py`) | 浏览器扩展版 |
|--------|------------------------------|-------------|
| 环境依赖 | Python + DrissionPage + Chrome | 仅需 Chrome/Edge |
| 启动方式 | 运行 Python 脚本 | 点击扩展图标 |
| 数据存储 | 页面 localStorage(按域名隔离) | 扩展 chrome.storage(全局共享) |
| 适用场景 | 需要 DrissionPage 控制浏览器时 | 任何网页,随时录制 |
| 跨域数据 | 不同网站数据不互通 | 所有网站数据统一在扩展存储中 |
| 干扰浏览 | 鼠标移动持续高亮 | Alt 按住才高亮,平时零干扰 |

## 文件结构

```
browser_extension/
  manifest.json          # 扩展配置
  content.js             # 核心逻辑(注入到页面的编排器)
  popup.html / popup.js  # 扩展图标弹窗
  generate_icons.py      # 图标生成脚本
  icons/                 # PNG 图标
  README.md              # 本文件
  xiaohognshu_elements.html  # 小红书 HTML 样本(测试用)
```
