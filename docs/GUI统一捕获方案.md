# GUI 统一捕获方案

## 目标

GUI 工具成为唯一的元素捕获入口，同时覆盖桌面控件和浏览器 DOM。
Chrome Extension 的捕获功能降级为辅助工具。

## 架构

```
┌─ GUI 统一捕获 ─────────────────────────────────────────────┐
│                                                              │
│  WindowFromPoint(x, y)                                       │
│    │                                                         │
│    ├─ _is_browser_window(class_name) == False                │
│    │   → Win32 + UIA 路径                                    │
│    │   → 高亮: UIA Leaf rect / HWND rect                     │
│    │   → 捕获: ElementInfo(desktop)                          │
│    │                                                        │
│    └─ _is_browser_window(class_name) == True                 │
│        → 计算视口坐标                                         │
│        → WS → 插件: {action: "pickElement", x, y}            │
│        → 插件返回: {css, xpath, drission, rect, screenshot}   │
│        → 高亮: DOM rect                                      │
│        → 捕获: ElementInfo(web) + selectors                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## 组件分工

| 组件 | 职责 |
|------|------|
| **GUI (capture_gui)** | 主入口，统一交互界面，处理所有类型元素 |
| **Win32 + UIA** | 桌面控件定位和捕获 |
| **WS 桥接 (native_host)** | GUI ↔ Extension 通信中继 |
| **Extension (content_capture.js)** | 浏览器内 DOM 拾取和选择器生成 |
| **后端蓝图 (element_picker)** | 可选：为未来 WebSocket 远程拾取预留 |

## data/models.py 新增模型 ScreenToCapture

| 字段 | 类型 | 说明 |
|------|------|------|
| global_x | int | 屏幕 X 坐标 |
| global_y | int | 屏幕 Y 坐标 |
| window_title | str | 窗口标题 |
| element_type | str | win32 / uia / web |
| class_name | str | 控件类名 |
| control_type | str | UIA 控件类型 |
| rect | JSON | 元素矩形 {left, top, right, bottom} |
| win32_path | JSON | HWND 祖先链 |
| uia_path | JSON | UIA 祖先链 |
| css_selector | str | CSS 选择器 (web) |
| xpath | str | XPath 选择器 (web) |
| screenshot | str | base64 截图 |
| captured_at | datetime | 捕获时间 |

## 实现清单

| 文件 | 改动 | 量 |
|------|------|-----|
| `scripts/capture_gui/ws_client.py` | **新**: GUI 连 WS，发 pickElement，收结果 | ~80行 |
| `extension/content_capture.js` | 加 pickElement 消息处理器 | ~60行 |
| `scripts/capture_gui/overlay.py` | 检测浏览器 → WS 路径 → DOM rect 高亮 | ~40行 |
| `data/models.py` | 新建 `ScreenToCapture` 表 | ~30行 |

## 坐标转换

```
屏幕坐标 → 视口坐标:
  viewportX = screenX - winRect.left
  viewportY = screenY - winRect.top - tabBarHeight

tabBarHeight: 通过 UIA 查找浏览器标签栏高度
```

## 前提条件

- Chrome 已安装 RPA Extension
- Extension 已连接 WS 服务
- Native Messaging 正常工作 (native_host.py)
