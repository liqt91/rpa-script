---
name: new-command
description: 创建新的 RPA 指令（command），一次命令生成+校验+热重载。四类：extension（扩展端）、backend（本地执行）、desktop（桌面操作）、control（控制流）。
---

# 新增指令

> ## ⚠️ 第 0 步（不可跳过，先做这个）：调用生成命令
>
> **生成任何指令前，第一步必须调用 `rpa_new_command`（DSH 工具）或
> `python scripts/command_builder.py <cmd> --definition-file <json>`。**
>
> 这是**唯一**的生成方式。它一次调用就完成：写定义 → 生成桩 → 构建 JS → 质量门禁 →
> **后端热重载 + 校验**。
>
> **如果你发现自己做了下面任一件事，说明你走错了，立刻停下并回到第 0 步：**
> - ❌ 在读示例指令文件（setVolumeWin32/_win32/registry/utils/categories…）
> - ❌ 在手工跑 `generate_commands.py` / `build_content_js.py`
> - ❌ 在写临时测试脚本（_tmp*.py / _validate*.py）
> - ❌ 在手工编辑 `commands/<cmd>.json` 之外的 handler 文件
>
> 下面所有内容只是**参数/目录参考**，先调用命令，再回头看这些。

## 参数 type 白名单（只用这些）

`string` 文本 · `text` 多行 · `select` 下拉(配 options) · `number` 数字 ·
`boolean` 布尔 · `str-var` 变量引用({{var}}) · `element` 元素选择器 ·
`element-list` 元素列表 · `code` 代码块 · `any-input` 任意输入 · `hidden` 隐藏

❌ 禁用：`str-dropdown`、`bool-check`、`int-number`（用 `number`）
✅ group：`主属性` / `advanced` / `output` / `input` / `anchor`

## 5 类指令：放哪（最小模板照抄改）

| 类别 | runtime | kind | 实现文件 | JS? |
|---|---|---|---|---|
| 浏览器/页面 | `extension` | `extension` | `dom_handlers_new/<cmd>.js` | 有 |
| Python 逻辑 | `backend` | `backend` | `backend_commands/<cmd>.py` | 无 |
| 桌面 Win32/UIA | `backend` | `backend` | `desktop_commands/<cmd>.py`（helper 放 `_win32.py`） | 无 |
| Electron 应用 | `backend` | `backend` | `electron_commands/<cmd>.py` | 无 |
| 流程控制 | `control` | `control` | `control_commands/<cmd>.py`（`evaluate()` 非 execute） | 无 |

> desktop/electron 指令 `runtime:"backend"`、`handler.source` 指向各自目录。
> 判断：调 Win32/UIA → `desktop_commands/`；纯 Python → `backend_commands/`。

**最小 JSON**（backend 示例；desktop 时 source 换 `desktop_commands/`）：
```json
{
  "cmd": "myCommand", "label": "我的指令", "runtime": "backend",
  "category": "分类中文名", "categories": ["slug"], "icon": "fa-cog",
  "iconColor": "text-blue-500", "bgColor": "bg-blue-50",
  "categoryOrder": 50, "commandOrder": 10, "description": "指令描述",
  "params": [{"name": "paramName", "label": "参数显示名", "type": "string", "required": true}],
  "handler": {"kind": "backend", "source": "src/runtime/commands/backend_commands/myCommand.py"}
}
```

**最小 handler**（backend/desktop，`generate_commands` 会在缺文件时自动生成脚手架——直接在其上填实现）：
```python
@register_handler(cmd="myCommand", label="我的指令", category="分类名", runtime="backend",
    icon="fa-cog", icon_color="text-blue-500", bg_color="bg-blue-50",
    category_order=50, command_order=10, description="指令描述", summary_tpl="{paramName}")
class MyCommandHandler:
    params = [Param("paramName", "参数显示名", "string", required=True)]
    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra", {})
        val = extra.get("paramName")
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                               "status": "success", "result": {"myCommand": True}})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": {"myCommand": True}})
        return True
```

## 生成步骤（第 0 步 = 命令，先做）

1. 定 `cmd`(小驼峰=文件名) / runtime / kind / 目录 / params（上表）。
2. **第 0 步：调 `rpa_new_command`（DSH 工具）或 `python scripts/command_builder.py <cmd>
   --definition-file <临时json>`** → 自动写定义+生成桩+构建JS+质量门禁+热重载。
   返回 `ok=true`（骨架就绪）、`quality_pass=false`（实现未填，正常）。
3. 填 `execute()` 实现（编辑命令生成的 `<cmd>.py`；extension 填 `<cmd>.js`）。
4. **再调一次命令**（不传 definition，复用已建 JSON）→ 复验到 `quality_pass=true`。

> 找 `command_builder.py` / 用 DSH 工具时，等价入口是 `rpa_new_command`（同一编排）。

## 质量标准（硬性 · 生成时对照）

**JSON**：`cmd` 非空小驼峰=文件名 · `runtime∈{extension,backend,control}` ·
`handler.kind==runtime` · `source` 指向对应目录 · `category`(中文)+`categories`(slug)均填。

**Python handler**：含 `@register_handler`(与 JSON 一致) · `Param` 与 JSON params 一一对应 ·
`async def execute(runner, cmd_type, step_id, instr)` · 读参用 `extra.get("paramName")` ·
成功路径 `runner.completed += 1` + `runner.results.append({...})` +
`await runner._emit({"type":"stepComplete",...})` · 提供 `summary_tpl` ·
不残留 AUTO-GENERATED 哨兵 · 变量已由 runner 统一 resolve（execute 内勿再调 resolve_vars）。

> 验证信号：`command_builder.py` 返回 `quality_pass:true`（实现合规）+
> `reload_pass:true`（已热加载）。不过时用 `python skills/scripts/check_command_quality.py <cmd>` 看哪条。

## 修改已有指令

改 JSON 后跑 `command_builder.py <cmd>`：extension 桩被覆盖、backend/desktop 已存在则
KEEP（保留手写实现）。**改 JSON 后参数不会自动回填到手写文件**，需手动保持 JSON 与
`@register_handler` 一致（generate_commands 对已存在文件 KEEP）。

## 文件边界（防 glob 超时 · 必读）

**glob 必须显式传 `path` 收窄**（裸 glob 从仓库根整树扫会踩 `.venv/`(1.8万文件)、`src/`、
`webrpa/` 等巨大目录而 30s 超时）：
- `glob(path:"<repo>/commands", pattern:"*.json")`
- `glob(path:"<repo>/src/runtime/commands/backend_commands", pattern:"*.py")`
- 禁止无 `path` 的裸 glob、禁止 `Get-ChildItem -Recurse` 全树统计。

**可写**：`commands/<cmd>.json`（唯一事实来源）· `src/runtime/commands/<dir>/<cmd>.py`
（脚手架首建后 KEEP）· `extension/dom_handlers_new/<cmd>.js`（仅 extension）·
`src/runtime/commands/types/categories.json`（仅新增分类 slug）。

**勿碰**：extension Python 桩（`DO NOT EDIT` 哨兵，每次被覆盖）· `extension/content.js`、
`background.js`（编译产物）· 前端 `static/workflow-editor/`（vite 产物）。

**绝对不碰**：`webrpa/` `WebRPA/` `.venv/` `node_modules/` `dist/` `build/`
`tdSelector_1.2.7/` `rpa-dsh-plugin/python/` `data/*` `tmp/` `__pycache__/` `*.pyc`
`.env`(密钥) `.private/` `.harness/` `*.log`。

## 架构约束

- `@register_handler` 注册到 `_HANDLER_REGISTRY`；`auto_register()` 在 lifespan 中自发现导入。
- **JSON 是唯一事实来源**：先改 JSON，再跑 `command_builder.py`/`generate_commands.py`。
- handler 参数名必须与 JSON `params[].name` 一致（execute 经 `extra.get("paramName")` 读）。
- 不要编辑含 `AUTO-GENERATED`/`DO NOT EDIT` 哨兵的 Python 文件（会被覆盖）。
