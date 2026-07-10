# 2026-07-10 改动恢复清单

## 已推送
- `src/runtime/routers/other_routers.py` — AI 3场景重构
- `src/ui/workflow-editor/src/components/AIConfigPage.jsx` — AI配置页重构

## 待恢复

### 1. 构建脚本
**scripts/build_background_js.py**
- 移除 EXTENSION 输出路径，仅输出到 dist/
```python
OUTPUT_PATHS = [
    os.path.join(ROOT, "dist", "desktop", "extension", "background.js"),
]
```

**scripts/build_content_js.py**
- 移除 EXTENSION 输出路径，仅输出到 dist/
```python
OUTPUT_PATHS = [
    os.path.join(ROOT, "dist", "desktop", "extension", "content.js"),
]
```

### 2. commands_router.py
**src/runtime/routers/commands_router.py**
- _HANDLERS_NEW_DIR 改为 _HANDLERS_BASE_DIR
- 新增 _RUNTIME_DIRS = ["backend_commands", "extension_commands", "control_commands"]
- get_handler_source 遍历三个目录
- 新增 GET /definitions/{type_name}/js-source 端点
- 新增 POST /definitions/{type_name}/save-js-handler 端点
- save_handler_code 从 JSON 读取 runtime 决定目标目录

### 3. validation.py
**src/runtime/workflow/validation.py**
- CONTENT_JS 路径改为 dist/desktop/extension/content.js
- 新增 BACKGROUND_JS 路径
- extract_js_handler_names() 合并 content + background handlers
- 新增 _extract_background_handlers() 函数，从 background.js 提取 registerBackgroundHandler 名称

### 4. main.py
**src/runtime/main.py**
- 新增 _read_handler_from_json() 辅助函数
- _seed_commands_to_db 中 handler 字段优先从 JSON 读取

### 5. extension/ 目录清理
- 删除 extension/background.js
- 删除 extension/content.js

### 6. 前端
**src/ui/workflow-editor/src/App.jsx**
- SidebarLayout: min-h-screen -> h-screen overflow-hidden
- 主内容区: 添加 overflow-hidden

**src/ui/workflow-editor/src/api.js**
- 新增 getJsHandlerSource
- 新增 saveJsHandlerCode

**src/ui/workflow-editor/src/components/CommandEditor.jsx**
- PARAM_GROUPS 更新为新名称（输出变量/输入变量/默认属性）
- 新增 loadJsSource() 函数
- selectDef() 中调用 loadJsSource()
- saveDef() 中调用 loadJsSource()
- generateHandlerWithAI() 移除 runtime 限制
- Python handler 面板: {isBackend} -> {!isEmitter}
- JS handler 面板: 新增保存按钮、AI生成按钮、正确路径
- AI 场景标识: Python -> command_backend, JS -> command_extension_js

### 7. 文档（不覆盖远端）
**docs/command-architecture.md** — 远端版本可用，不覆盖
