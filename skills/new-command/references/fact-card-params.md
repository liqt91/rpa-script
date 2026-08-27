# 参数 type 白名单

只在 JSON `params[].type` 里用这些：

`string` 文本 · `text` 多行 · `select` 下拉(配 options) · `number` 数字 ·
`boolean` 布尔 · `str-var` 变量引用({{var}}) · `element` 元素选择器 ·
`element-list` 元素列表 · `code` 代码块 · `any-input` 任意输入 · `hidden` 隐藏

❌ 禁用：`str-dropdown`、`bool-check`、`int-number`（用 `number`）

✅ group 取值：`主属性` / `advanced` / `output` / `input` / `anchor`

- 元素参数用 `type: "element"`（用户选已捕获元素）；`required: true` 才要求必须选元素。
- 结果写变量用 `type: "str-var"`，`name` 通常叫 `resultVar`，`group: "output"`。
