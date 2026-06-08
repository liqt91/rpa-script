# 待办清单

## 高优先级

- [x] **CSS 推荐方案拆分为“单个 / 列表”两个 tab（已完成）**
  - `sidepanel.html` 增加 `CSS-单个` / `CSS-列表` 两个 tab
  - `sidepanel.js` 按 `isList` 过滤候选；校验/保存时把 tab 映射回 `css` family
  - `content_capture.js` 的 `pickCandidatesByFamily` 对 CSS 按 `isList` 分组，每组最多 10 个

- [x] **列表元素检测算法（已完成）**
  - `content_capture.js` 新增结构指纹 + 祖先投票检测：`makeStructuralFingerprint`、`fingerprintSimilarity`、`detectListFamily`
  - 列表选择器生成：`buildListItemSelector` / `buildListContainerSelector`，优先 data-* > 稳定 class > role > tag
  - `generateListCandidates` 输出 `(列表, N个)` 候选，附带 `listContainer` / `listItem` / `listSize`
  - `sidepanel.js` 透传列表元数据，`elements_service.py` 持久化到 `attributes.__rpa_list_*`
  - 修复嵌套点击场景：以包含目标元素的列表项作为 item 选择器基准

- [x] **元素采集与推荐方案重构（已完成）**
  - 重构 `buildElementPath`：补充 IDL property fallback（href/src/value/checked）
  - 重构 `generateLocators` → 基于已采集 `path` 生成候选，附带 `pathMapping`
  - 新增 `_levelCandidatesFromNode`、`buildFinderCandidatesFromPath`、`buildStructuralCssFromPath`、`getElementCssPathFromPath`
  - 更新 sidepanel `applyCandidateToUI` 直接基于 `pathMapping` 映射，保留 legacy 回退
  - 方案文档：`element-capture-refactor-proposal.html`

- [ ] **setVar/setval 端到端验证**
  - 在真实工作流中测试变量设置、引用、传递
  - 验证 `${var}` / `{{var}}` 在各类节点中的解析
  - 验证 navigate 节点的 `saveToVar` 输出变量

- [ ] **health-endpoint 功能**
  - 见 `.harness/feature_list.json` id=health-endpoint

- [ ] **not-found-page 功能**
  - 见 `.harness/feature_list.json` id=not-found-page

## 中优先级

- [ ] **支持元素内部滚动**
  - 当前所有滚动（scrollToBottom/Top/By/OneScreen）均为整页滚动（`window.scrollBy`）
  - 目标：增加可选的 `scrollContainer`（滚动容器 locator），在元素内部执行滚动
  - 参考：影刀"在指定元素上滚动"开关

- [ ] **节点配置项联动**
  - 当前前端 NodeForm 所有字段平铺显示，无显隐联动
  - 目标：select 切换时动态显示/隐藏关联字段（如 scrollType="intoView" 时才显示 locator）
  - 关联：可先拆分指令作为短期 workaround

- [ ] **影刀 RPA 插件分析**
  - 文件：`3.1.0.0_0.zip`
  - 目标：分析其指令体系、元素捕获方式，作为功能扩展参考

- [ ] **桌面应用 IPC 通信**
  - 当工作流编辑器封装为桌面应用后，替换 smart polling 为原生 IPC
  - 当前方案：元素库/管理后台使用 5 秒轮询（跨浏览器唯一可靠方案）

## 低优先级 / 已记录

- [ ] **循环变量作用域设计**
  - 当前所有循环共享同一个 `self.vars`，循环变量在循环结束后仍全局可见
  - 待决策：保持现状 vs 引入块级作用域隔离 vs 显式作用域控制
  - 关联代码：`src/runtime/workflow/extension_runner.py`

- [x] 捕获元素确认框 + 名称输入（已完成）
- [x] 元素截图裁剪（已完成）
- [x] 元素库智能轮询（已完成）
- [x] workTabId 管理，支持空白页开始执行（已完成）
- [x] 默认扩展模式（已完成）
- [x] 运行结果记入数据库日志（已完成）
