## Plan: 指令参数表格化编辑

将 NodeForm.jsx 中 extraFields 的纵向堆叠渲染改为表格布局。每行展示：参数标签（左）、可编辑控件（右）。保留所有现有 SchemaField 类型（text/number/select/bool/textarea/varName/locator）的交互能力，仅改变容器布局。不改动数据流、API 或状态管理。最小改动范围：NodeForm.jsx 的 extraFields 渲染区域 + SchemaField 组件的样式适配。
