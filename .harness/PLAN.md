## Plan: 工作流级参数（workflow parameters）

在 Workflow 模型新增 `parameters` JSON 列，定义流程级参数（name/label/type/default）。前端在右侧属性面板无选中节点时展示参数编辑器；Toolbar 运行前若存在参数则弹出输入框收集实际值。运行时通过 `/api/workflows/{id}/run/extension` 的 `parameters` 字段传给后端，`run_workflow_extension` 将其注入 `runner.vars`，复用现有 `${var}` / `{{var}}` 插值，使 navigate URL 等可使用 `${postUrl}`。

后端改动：models.py 加列 + migrations.py 007；dtypes/schemas.py 增加参数 schema 并在 WorkflowCreate/Update/Out 中暴露；workflows_router.py 的运行 endpoint 接收并透传；extension_runner.py 注入 vars；python run 与 exporter.py 也支持初始参数。

前端改动：api.js 两个 run 方法带 parameters；WorkflowContext.jsx 提供参数读写；NodeForm.jsx 无节点时显示参数编辑；Toolbar.jsx 运行前弹出参数输入框。

验证：结构测试、pytest、npm run build、手动运行一个带 postUrl 参数的 navigate 流程。
