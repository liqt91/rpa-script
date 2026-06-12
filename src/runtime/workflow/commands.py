"""
Workflow command registry — schema-driven instruction catalog.

Design philosophy (影刀-style granularity):
- Each command is a specific use-case, not a generic action + parameters.
- Commands declare their own form fields via a schema; the frontend renders dynamically.
- Container commands (if/for/try) can hold child nodes.
"""

import copy
from typing import Any

# ─── Field type helpers ───────────────────────────────────────────

def _element_name_field(required: bool = True) -> dict:
    return {"name": "element_name", "label": "元素", "type": "elementName", "required": required, "isPrimaryElement": True}

def _timeout_field(default: int = 10) -> dict:
    return {"name": "timeout", "label": "超时(秒)", "type": "number", "default": default, "group": "advanced"}

def _var_field(name: str = "varName", label: str = "保存到变量") -> dict:
    return {"name": name, "label": label, "type": "varName", "required": False, "group": "output"}

def _window_var_field() -> dict:
    return {"name": "windowVar", "label": "窗口变量", "type": "varName", "required": False, "default": "browser1", "placeholder": "如 browser1", "group": "input"}

def _scope_field() -> dict:
    return {
        "name": "scope",
        "label": "匹配范围",
        "type": "select",
        "options": [
            {"label": "按循环序号对齐", "value": "local"},
            {"label": "全页面匹配", "value": "global"},
        ],
        "default": "global",
        "group": "advanced",
        "description": "“按循环序号对齐”表示与当前 forEachElement 的第 N 个元素对齐：系统会先用当前选择器在整个页面搜索所有匹配元素，然后取第 N 个。要求页面匹配数量 ≥ 循环元素数量。",
    }

def _on_error_field(default: str = "stop") -> dict:
    return {
        "name": "onError",
        "label": "执行失败时",
        "type": "select",
        "options": [{"label": "停止", "value": "stop"}, {"label": "继续", "value": "continue"}, {"label": "重试", "value": "retry"}],
        "default": default,
        "group": "advanced",
    }

def _retry_count_field(default: int = 3) -> dict:
    return {
        "name": "retryCount",
        "label": "重试次数",
        "type": "number",
        "default": default,
        "group": "advanced",
    }

def _attach_common_advanced(fields: list[dict]) -> list[dict]:
    """为指令字段列表附加通用高级参数（如果不存在）。"""
    result = copy.deepcopy(fields)
    names = {f.get("name") for f in result}
    has_element = "element_name" in names
    if "onError" not in names:
        result.append(_on_error_field())
    if "retryCount" not in names:
        result.append(_retry_count_field())
    if "timeout" not in names:
        result.append(_timeout_field())
    if has_element and "visibleOnly" not in names:
        result.append(
            {
                "name": "visibleOnly",
                "label": "只操作可见元素",
                "type": "bool",
                "default": True,
                "group": "advanced",
            }
        )
    if "humanLike" not in names:
        result.append(
            {
                "name": "humanLike",
                "label": "拟人化操作",
                "type": "bool",
                "default": True,
                "group": "advanced",
            }
        )
    return result

# ─── Command registry ─────────────────────────────────────────────
#
# Runtime 映射标准（content.js handlers ↔ 指令类型）
#
# 【一对一】指令行为与 handler 完全对应，直接映射：
#   navigate, click, input, clearInput, pressKey, selectOption,
#   goBack, goForward, refresh, newTab, hover, executeJs
#
# 【多对一】多个指令共享一个通用 handler，通过 extra 字段区分行为：
#   extract → getText(None), getAttr(attrName), getHtml(innerHTML), getValue(value)
#   scroll  → scrollToBottom, scrollToTop, scrollOneScreen, scrollIntoView, scrollBy
#   wait    → sleep(seconds), waitForElement(timeout) — 待扩展
#
# 【后端本地】不操作页面 DOM，由 extension_runner._handle_local 直接执行：
#   setVar, appendToList, stringConcat, increment,
#   log, pushItem, saveToFile, httpRequest,
#   callWorkflow, return, callAiApp
#
# 【不需要 runtime】容器/结构标记/自定义代码，emitter 自动跳过：
#   容器: ifElementExists~ifVarGreaterThan, forEachElement~whileCondition, try, catch, else
#   结构: endIf, endFor, endTry
#   自定义: custom
#
# 【待实现】content.js 暂无对应 handler，后续需补充：
#   doubleClick, rightClick, clickByIndex, clickIfExists,
#   closeTab, switchTab, switchToFrame, switchToMain,
#   getCurrentUrl, getPageTitle, getElementCount, getElementList,
#   takeScreenshot, keyCombo, infiniteScroll,
#   waitForElementHide, waitForLoad, waitForText, waitForUrl

COMMAND_REGISTRY: dict[str, dict[str, Any]] = {
    # ═══════════════════════════════════════════════════════════════
    # 1. 页面导航 (Navigation)
    # ═══════════════════════════════════════════════════════════════
    "openBrowser": {
        "label": "打开浏览器",
        "categoryOrder": 10,
        "commandOrder": 10,
        "enabled": True,
        "category": "页面导航",
        "icon": "fa-chrome",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "openBrowser", "local": False}},
        "fields": [
            {"name": "browserType", "label": "浏览器", "type": "select", "options": [{"label": "Chrome", "value": "chrome"}, {"label": "Edge", "value": "edge"}], "default": "chrome"},
            {"name": "url", "label": "启动后打开网址", "type": "text", "required": False, "placeholder": "留空则打开 about:blank"},
            {"name": "windowState", "label": "窗口状态", "type": "select", "options": [{"label": "正常", "value": "normal"}, {"label": "最大化", "value": "maximized"}], "default": "normal"},
            {"name": "saveToVar", "label": "保存窗口对象到", "type": "varName", "required": False, "default": "browser1", "group": "output"},
        ],
    },
    "navigate": {
        "label": "打开网页",
        "categoryOrder": 10,
        "commandOrder": 50,
        "enabled": True,
        "category": "页面导航",
        "icon": "fa-globe",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "navigate", "local": False}},
        "fields": [
            {"name": "url", "label": "网址", "type": "text", "required": True, "placeholder": "https://..."},
            _window_var_field(),
            {"name": "waitLoad", "label": "等待加载完成", "type": "bool", "default": True},
            _timeout_field(30),
            _var_field("saveToVar", "保存网页对象到"),
        ],
    },
    "newTab": {
        "label": "新建标签页",
        "categoryOrder": 10,
        "commandOrder": 30,
        "enabled": True,
        "category": "页面导航",
        "icon": "fa-plus",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "newTab", "local": False}},
        "fields": [
            _window_var_field(),
            {"name": "url", "label": "网址(可选)", "type": "text", "required": False, "placeholder": "https://..."},
        ],
    },
    "closeTab": {
        "label": "关闭当前标签页",
        "categoryOrder": 10,
        "commandOrder": 40,
        "enabled": False,
        "category": "页面导航",
        "icon": "fa-xmark",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            _window_var_field(),
        ],
    },
    "closeBrowser": {
        "label": "关闭浏览器窗口",
        "categoryOrder": 10,
        "commandOrder": 20,
        "enabled": True,
        "category": "页面导航",
        "icon": "fa-window-close",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "closeBrowser", "local": False}},
        "fields": [
            _window_var_field(),
        ],
    },
    "getCurrentUrl": {
        "label": "获取当前URL",
        "categoryOrder": 10,
        "commandOrder": 60,
        "enabled": True,
        "category": "页面导航",
        "icon": "fa-link",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "getCurrentUrl", "local": False}},
        "fields": [
            _window_var_field(),
            _var_field()],
    },
    "getPageTitle": {
        "label": "获取页面标题",
        "categoryOrder": 10,
        "commandOrder": 70,
        "enabled": False,
        "category": "页面导航",
        "icon": "fa-heading",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            _window_var_field(),
            _var_field()],
    },

    # ═══════════════════════════════════════════════════════════════
    # 2. 元素点击 (Click)
    # ═══════════════════════════════════════════════════════════════
    "click": {
        "label": "点击元素",
        "categoryOrder": 20,
        "commandOrder": 10,
        "enabled": True,
        "category": "元素点击",
        "icon": "fa-mouse-pointer",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "click", "local": False}},
        "fields": [
            _window_var_field(),
            _element_name_field(),
            _scope_field(),
            {
                "name": "forceJs",
                "label": "强制JS点击",
                "type": "bool",
                "default": False,
                "description": "开启后直接调用元素的 el.click()，不触发鼠标移动和 mousedown/mouseup/click 事件序列。适合被反自动化拦截时使用。若同时开启，优先级高于“拟人化操作”。",
            },
            {
                "name": "humanLike",
                "label": "拟人化操作",
                "type": "bool",
                "default": True,
                "group": "advanced",
                "description": "开启时模拟鼠标移动轨迹，并依次触发 mousedown → mouseup → click 事件；关闭后跳过鼠标移动和事件间隔。若“强制JS点击”同时开启，本选项被忽略。",
            },
        ],
    },
    "rightClick": {
        "label": "右键点击",
        "categoryOrder": 20,
        "commandOrder": 40,
        "enabled": False,
        "category": "元素点击",
        "icon": "fa-mouse-pointer",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            _window_var_field(),
            _element_name_field(),
            _scope_field(),
        ],
    },
    "clickIfExists": {
        "label": "如果存在则点击",
        "categoryOrder": 20,
        "commandOrder": 20,
        "enabled": False,
        "category": "元素点击",
        "icon": "fa-hand-point-up",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            _window_var_field(),
            _element_name_field(),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 3. 文本输入 (Input)
    # ═══════════════════════════════════════════════════════════════
    "input": {
        "label": "输入文本",
        "categoryOrder": 50,
        "commandOrder": 10,
        "enabled": True,
        "category": "文本输入",
        "icon": "fa-keyboard",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "input", "local": False}},
        "fields": [
            _window_var_field(),
            _element_name_field(),
            _scope_field(),
            {"name": "text", "label": "输入内容", "type": "text", "required": True},
            {"name": "clearFirst", "label": "先清空", "type": "bool", "default": True},
        ],
    },
    "inputAndPressEnter": {
        "label": "输入并回车",
        "categoryOrder": 50,
        "commandOrder": 20,
        "enabled": True,
        "category": "文本输入",
        "icon": "fa-keyboard",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "input", "local": False}},
        "fields": [
            _window_var_field(),
            _element_name_field(),
            _scope_field(),
            {"name": "text", "label": "输入内容", "type": "text", "required": True},
            {"name": "clearFirst", "label": "先清空", "type": "bool", "default": True},
        ],
    },
    "clearInput": {
        "label": "清空输入框",
        "categoryOrder": 50,
        "commandOrder": 30,
        "enabled": True,
        "category": "文本输入",
        "icon": "fa-eraser",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "clearInput", "local": False}},
        "fields": [
            _window_var_field(),
            _element_name_field(),
        ],
    },
    "pressKey": {
        "label": "按键",
        "categoryOrder": 50,
        "commandOrder": 40,
        "enabled": True,
        "category": "文本输入",
        "icon": "fa-arrow-turn-up",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "pressKey", "local": False}},
        "fields": [
            _window_var_field(),
            {"name": "key", "label": "按键", "type": "select", "options": [{"label": "回车", "value": "Enter"}, {"label": "Tab", "value": "Tab"}, {"label": "Esc", "value": "Esc"}, {"label": "向下箭头", "value": "ArrowDown"}, {"label": "向上箭头", "value": "ArrowUp"}, {"label": "PageDown", "value": "PageDown"}, {"label": "PageUp", "value": "PageUp"}, {"label": "空格", "value": "Space"}, {"label": "退格", "value": "Backspace"}], "default": "Enter"},
        ],
    },
    "selectOption": {
        "label": "下拉框选择",
        "categoryOrder": 50,
        "commandOrder": 50,
        "enabled": True,
        "category": "文本输入",
        "icon": "fa-list",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "selectOption", "local": False}},
        "fields": [
            _window_var_field(),
            _element_name_field(),
            {"name": "by", "label": "选择方式", "type": "select", "options": [{"label": "值", "value": "value"}, {"label": "文本", "value": "label"}, {"label": "索引", "value": "index"}], "default": "label"},
            {"name": "value", "label": "值", "type": "text", "required": True},
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 4. 数据提取 (Extraction)
    # ═══════════════════════════════════════════════════════════════
    "getText": {
        "label": "获取元素文本",
        "categoryOrder": 60,
        "commandOrder": 10,
        "enabled": True,
        "category": "数据提取",
        "icon": "fa-font",
        "iconColor": "text-green-500",
        "bgColor": "bg-green-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "extract", "local": False}},
        "fields": [
            _window_var_field(),
            _element_name_field(),
            _scope_field(),
            _var_field(),
        ],
    },
    "getAttr": {
        "label": "获取元素属性",
        "categoryOrder": 60,
        "commandOrder": 20,
        "enabled": True,
        "category": "数据提取",
        "icon": "fa-tag",
        "iconColor": "text-green-500",
        "bgColor": "bg-green-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "extract", "local": False}},
        "fields": [
            _window_var_field(),
            _element_name_field(),
            _scope_field(),
            {"name": "attrName", "label": "属性名", "type": "text", "required": True, "placeholder": "href / src / data-id"},
            _var_field(),
        ],
    },
    "getHtml": {
        "label": "获取元素HTML",
        "categoryOrder": 60,
        "commandOrder": 30,
        "enabled": True,
        "category": "数据提取",
        "icon": "fa-code",
        "iconColor": "text-green-500",
        "bgColor": "bg-green-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "extract", "local": False}},
        "fields": [
            _window_var_field(),
            _element_name_field(),
            {"name": "mode", "label": "模式", "type": "select", "options": [{"label": "内部HTML", "value": "inner"}, {"label": "包含标签", "value": "outer"}], "default": "inner"},
            _var_field(),
        ],
    },
    "getValue": {
        "label": "获取输入框值",
        "categoryOrder": 60,
        "commandOrder": 40,
        "enabled": True,
        "category": "数据提取",
        "icon": "fa-i-cursor",
        "iconColor": "text-green-500",
        "bgColor": "bg-green-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "extract", "local": False}},
        "fields": [
            _window_var_field(),
            _element_name_field(),
            _var_field(),
        ],
    },
    "getElementCount": {
        "label": "获取元素数量",
        "categoryOrder": 60,
        "commandOrder": 50,
        "enabled": False,
        "category": "数据提取",
        "icon": "fa-hashtag",
        "iconColor": "text-green-500",
        "bgColor": "bg-green-50",
        "isContainer": False,
        "fields": [
            _window_var_field(),
            _element_name_field(),
            _scope_field(),
            _var_field(),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 5. 滚动 (Scroll)
    # ═══════════════════════════════════════════════════════════════
    "scrollToBottom": {
        "label": "滚动到底部",
        "categoryOrder": 40,
        "commandOrder": 20,
        "enabled": True,
        "category": "滚动",
        "icon": "fa-arrow-down",
        "iconColor": "text-cyan-500",
        "bgColor": "bg-cyan-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "scroll", "local": False}},
        "fields": [
            _window_var_field(),
            {"name": "humanLike", "label": "平滑滚动", "type": "bool", "default": True},
        ],
    },
    "scrollToTop": {
        "label": "滚动到顶部",
        "categoryOrder": 40,
        "commandOrder": 30,
        "enabled": True,
        "category": "滚动",
        "icon": "fa-arrow-up",
        "iconColor": "text-cyan-500",
        "bgColor": "bg-cyan-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "scroll", "local": False}},
        "fields": [
            _window_var_field(),
            {"name": "humanLike", "label": "平滑滚动", "type": "bool", "default": True},
        ],
    },
    "scrollOneScreen": {
        "label": "滚动一屏",
        "categoryOrder": 40,
        "commandOrder": 10,
        "enabled": True,
        "category": "滚动",
        "icon": "fa-desktop",
        "iconColor": "text-cyan-500",
        "bgColor": "bg-cyan-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "scroll", "local": False}},
        "fields": [
            _window_var_field(),
            {"name": "humanLike", "label": "平滑滚动", "type": "bool", "default": True},
        ],
    },
    "scrollBy": {
        "label": "滚动指定距离",
        "categoryOrder": 40,
        "commandOrder": 40,
        "enabled": True,
        "category": "滚动",
        "icon": "fa-arrows-up-down",
        "iconColor": "text-cyan-500",
        "bgColor": "bg-cyan-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "scroll", "local": False}},
        "fields": [
            _window_var_field(),
            {"name": "x", "label": "水平距离(px)", "type": "number", "default": 0},
            {"name": "y", "label": "垂直距离(px)", "type": "number", "default": 500},
            {"name": "humanLike", "label": "平滑滚动", "type": "bool", "default": True},
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 6. 等待 (Wait)
    # ═══════════════════════════════════════════════════════════════
    "sleep": {
        "label": "等待固定时间",
        "categoryOrder": 30,
        "commandOrder": 10,
        "enabled": True,
        "category": "等待",
        "icon": "fa-clock",
        "iconColor": "text-gray-500",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "wait", "local": False}},
        "fields": [
            _window_var_field(),
            {"name": "seconds", "label": "等待秒数", "type": "number", "default": 1.0},
        ],
    },
    "waitForElement": {
        "label": "等待元素出现",
        "categoryOrder": 30,
        "commandOrder": 20,
        "enabled": True,
        "category": "等待",
        "icon": "fa-eye",
        "iconColor": "text-gray-500",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "wait", "local": False}},
        "fields": [
            _window_var_field(),
            _element_name_field(),
            _scope_field(),
            _timeout_field(10),
        ],
    },
    "waitForElementHide": {
        "label": "等待元素消失",
        "categoryOrder": 30,
        "commandOrder": 30,
        "enabled": False,
        "category": "等待",
        "icon": "fa-eye-slash",
        "iconColor": "text-gray-500",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            _window_var_field(),
            _element_name_field(),
            _scope_field(),
            _timeout_field(10),
        ],
    },
    "waitForText": {
        "label": "等待文本出现",
        "categoryOrder": 30,
        "commandOrder": 40,
        "enabled": False,
        "category": "等待",
        "icon": "fa-comment-dots",
        "iconColor": "text-gray-500",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            _window_var_field(),
            _element_name_field(),
            {"name": "text", "label": "期望文本", "type": "text", "required": True},
            _timeout_field(10),
        ],
    },
    "waitForUrl": {
        "label": "等待URL变化",
        "categoryOrder": 30,
        "commandOrder": 50,
        "enabled": False,
        "category": "等待",
        "icon": "fa-link",
        "iconColor": "text-gray-500",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            _window_var_field(),
            {"name": "urlPattern", "label": "URL包含", "type": "text", "required": True},
            _timeout_field(10),
        ],
    },
    "waitForLoad": {
        "label": "等待页面加载",
        "categoryOrder": 30,
        "commandOrder": 60,
        "enabled": False,
        "category": "等待",
        "icon": "fa-spinner",
        "iconColor": "text-gray-500",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            _window_var_field(),
            {"name": "state", "label": "加载状态", "type": "select", "options": [{"label": "DOM就绪", "value": "domcontentloaded"}, {"label": "网络空闲", "value": "networkidle"}], "default": "networkidle"},
            _timeout_field(30),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 7. 条件判断 (Condition) — 影刀式精细拆分 ⭐
    # ═══════════════════════════════════════════════════════════════
    "ifElementVisible": {
        "label": "如果元素可见/不可见",
        "categoryOrder": 70,
        "commandOrder": 20,
        "enabled": True,
        "description": "多元素组合逻辑：可见=任一元素可见即成立（OR）；不可见=所有元素都不可见才成立（AND）。",
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "closesWith": "endIf",
        "fields": [
            _element_name_field(),
            {"name": "element_names", "label": "附加元素", "type": "elementNameList", "required": False},
            _scope_field(),
            {"name": "operator", "label": "条件", "type": "select", "options": [{"label": "可见", "value": "visible"}, {"label": "不可见", "value": "notVisible"}], "default": "visible"},
        ],
    },
    "ifTextContains": {
        "label": "如果元素文本",
        "categoryOrder": 70,
        "commandOrder": 30,
        "enabled": True,
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "closesWith": "endIf",
        "fields": [
            _element_name_field(),
            _scope_field(),
            {"name": "operator", "label": "条件", "type": "select", "options": [{"label": "包含", "value": "contains"}, {"label": "不包含", "value": "notContains"}, {"label": "开头为", "value": "startsWith"}, {"label": "结尾为", "value": "endsWith"}], "default": "contains"},
            {"name": "text", "label": "文本", "type": "text", "required": True},
        ],
    },
    "ifTextEquals": {
        "label": "如果元素文本等于",
        "categoryOrder": 70,
        "commandOrder": 40,
        "enabled": True,
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "closesWith": "endIf",
        "fields": [
            _element_name_field(),
            {"name": "text", "label": "等于文本", "type": "text", "required": True},
        ],
    },
    "ifVarEquals": {
        "label": "如果变量比较",
        "categoryOrder": 70,
        "commandOrder": 60,
        "enabled": True,
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "closesWith": "endIf",
        "fields": [
            {"name": "varName", "label": "变量名", "type": "varName", "required": True},
            {"name": "operator", "label": "条件", "type": "select", "options": [{"label": "等于", "value": "equals"}, {"label": "大于", "value": "greaterThan"}, {"label": "小于", "value": "lessThan"}], "default": "equals"},
            {"name": "value", "label": "比较值", "type": "text", "required": True},
            {"name": "valueType", "label": "值类型", "type": "select", "options": [{"label": "字符串", "value": "string"}, {"label": "数字", "value": "number"}, {"label": "布尔值", "value": "bool"}], "default": "string"},
        ],
    },
    "ifVarContains": {
        "label": "如果变量匹配",
        "categoryOrder": 70,
        "commandOrder": 70,
        "enabled": True,
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "closesWith": "endIf",
        "fields": [
            {"name": "varName", "label": "变量名", "type": "varName", "required": True},
            {"name": "operator", "label": "条件", "type": "select", "options": [{"label": "包含", "value": "contains"}, {"label": "不包含", "value": "notContains"}, {"label": "开头为", "value": "startsWith"}, {"label": "结尾为", "value": "endsWith"}], "default": "contains"},
            {"name": "value", "label": "值", "type": "text", "required": True},
        ],
    },
    "ifListContains": {
        "label": "如果列表包含",
        "categoryOrder": 70,
        "commandOrder": 80,
        "enabled": True,
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "closesWith": "endIf",
        "fields": [
            {"name": "listName", "label": "列表变量", "type": "varName", "required": True},
            {"name": "value", "label": "包含值", "type": "text", "required": True},
        ],
    },
    "ifDictContains": {
        "label": "如果字典包含键",
        "categoryOrder": 70,
        "commandOrder": 90,
        "enabled": True,
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "closesWith": "endIf",
        "fields": [
            {"name": "dictName", "label": "字典变量", "type": "varName", "required": True},
            {"name": "key", "label": "键", "type": "text", "required": True},
        ],
    },
    "else": {
        "label": "否则",
        "categoryOrder": 70,
        "commandOrder": 100,
        "enabled": True,
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "isBranch": True,
        "closesWith": "endIf",
        "fields": [],
    },
    "endIf": {
        "label": "结束如果",
        "categoryOrder": 70,
        "commandOrder": 110,
        "enabled": True,
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": False,
        "fields": [],
        "isStructural": True,
    },

    # ═══════════════════════════════════════════════════════════════
    # 8. 循环 (Loop)
    # ═══════════════════════════════════════════════════════════════
    "forEachElement": {
        "label": "循环相似元素",
        "categoryOrder": 80,
        "commandOrder": 10,
        "enabled": True,
        "category": "循环",
        "icon": "fa-sync",
        "iconColor": "text-purple-500",
        "bgColor": "bg-purple-50",
        "isContainer": True,
        "closesWith": "endFor",
        "fields": [
            _element_name_field(),
            _scope_field(),
            {
                "name": "visibilityMode",
                "label": "元素可见性",
                "type": "select",
                "options": [
                    {"label": "视口内可见", "value": "visible"},
                    {"label": "已渲染（含屏幕外）", "value": "rendered"},
                    {"label": "全部（含隐藏元素）", "value": "any"},
                ],
                "default": "visible",
                "group": "advanced",
                "description": "视口内可见=既渲染又在当前浏览器可视区域；已渲染=CSS未隐藏但可能在屏幕外；全部=只要DOM存在就匹配。",
            },
            {"name": "itemVar", "label": "元素变量名", "type": "varName", "default": "item"},
            {"name": "indexVar", "label": "索引变量名", "type": "varName", "default": "index"},
        ],
    },
    "forRange": {
        "label": "循环次数",
        "categoryOrder": 80,
        "commandOrder": 20,
        "enabled": True,
        "category": "循环",
        "icon": "fa-repeat",
        "iconColor": "text-purple-500",
        "bgColor": "bg-purple-50",
        "isContainer": True,
        "closesWith": "endFor",
        "fields": [
            {"name": "start", "label": "起始值", "type": "number", "default": 0},
            {"name": "end", "label": "结束值", "type": "number", "default": 10},
            {"name": "step", "label": "步长", "type": "number", "default": 1},
            {"name": "varName", "label": "循环变量名", "type": "varName", "default": "i"},
        ],
    },
    "forList": {
        "label": "循环列表",
        "categoryOrder": 80,
        "commandOrder": 30,
        "enabled": True,
        "category": "循环",
        "icon": "fa-list-ol",
        "iconColor": "text-purple-500",
        "bgColor": "bg-purple-50",
        "isContainer": True,
        "closesWith": "endFor",
        "fields": [
            {"name": "listVar", "label": "列表变量", "type": "varName", "required": True},
            {"name": "itemVar", "label": "元素变量名", "type": "varName", "default": "item"},
            {"name": "indexVar", "label": "索引变量名", "type": "varName", "default": "index"},
        ],
    },
    "forEachTableRow": {
        "label": "循环表格",
        "categoryOrder": 80,
        "commandOrder": 40,
        "enabled": True,
        "category": "循环",
        "icon": "fa-table",
        "iconColor": "text-purple-500",
        "bgColor": "bg-purple-50",
        "isContainer": True,
        "closesWith": "endFor",
        "fields": [
            {"name": "itemVar", "label": "行变量名", "type": "varName", "default": "row"},
            {"name": "indexVar", "label": "索引变量名", "type": "varName", "default": "index"},
        ],
    },
    "whileCondition": {
        "label": "循环直到条件成立",
        "categoryOrder": 80,
        "commandOrder": 50,
        "enabled": True,
        "category": "循环",
        "icon": "fa-rotate",
        "iconColor": "text-purple-500",
        "bgColor": "bg-purple-50",
        "isContainer": True,
        "closesWith": "endFor",
        "fields": [
            {"name": "conditionType", "label": "条件类型", "type": "select", "options": [{"label": "元素存在", "value": "elementExists"}, {"label": "元素不存在", "value": "elementNotExists"}, {"label": "URL包含", "value": "urlContains"}, {"label": "变量等于", "value": "varEquals"}, {"label": "变量包含", "value": "varContains"}], "default": "elementExists"},
            _element_name_field(required=False),
            _scope_field(),
            {"name": "urlPattern", "label": "URL包含", "type": "text", "required": False},
            {"name": "varName", "label": "变量名", "type": "varName", "required": False},
            {"name": "varValue", "label": "变量值", "type": "text", "required": False},
            {"name": "maxIterations", "label": "最大迭代次数", "type": "number", "default": 100},
        ],
    },
    "break": {
        "label": "跳出循环",
        "categoryOrder": 80,
        "commandOrder": 60,
        "enabled": True,
        "category": "循环",
        "icon": "fa-ban",
        "iconColor": "text-purple-500",
        "bgColor": "bg-purple-50",
        "isContainer": False,
        "fields": [],
    },
    "continue": {
        "label": "继续下一次循环",
        "categoryOrder": 80,
        "commandOrder": 70,
        "enabled": True,
        "category": "循环",
        "icon": "fa-forward-step",
        "iconColor": "text-purple-500",
        "bgColor": "bg-purple-50",
        "isContainer": False,
        "fields": [],
    },
    "endFor": {
        "label": "结束循环",
        "categoryOrder": 80,
        "commandOrder": 80,
        "enabled": True,
        "category": "循环",
        "icon": "fa-sync",
        "iconColor": "text-purple-500",
        "bgColor": "bg-purple-50",
        "isContainer": False,
        "fields": [],
        "isStructural": True,
    },

    # ═══════════════════════════════════════════════════════════════
    # 9. 变量与数据 (Variables)
    # ═══════════════════════════════════════════════════════════════
    "setVar": {
        "label": "设置变量",
        "categoryOrder": 45,
        "commandOrder": 1,
        "enabled": True,
        "category": "变量与数据",
        "icon": "fa-superscript",
        "iconColor": "text-indigo-500",
        "bgColor": "bg-indigo-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "setVar", "local": True}},
        "fields": [
            {"name": "name", "label": "变量名", "type": "varName", "required": True},
            {"name": "value", "label": "值", "type": "text", "required": True},
            {"name": "valueType", "label": "值类型", "type": "select", "options": [{"label": "字符串", "value": "string"}, {"label": "数字", "value": "number"}, {"label": "布尔值", "value": "bool"}, {"label": "列表", "value": "list"}, {"label": "字典", "value": "dict"}], "default": "string"},
        ],
    },
    "appendToList": {
        "label": "追加到列表",
        "categoryOrder": 45,
        "commandOrder": 20,
        "enabled": True,
        "category": "变量与数据",
        "icon": "fa-plus",
        "iconColor": "text-indigo-500",
        "bgColor": "bg-indigo-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "appendToList", "local": True}},
        "fields": [
            {"name": "listName", "label": "列表变量", "type": "varName", "required": True},
            {"name": "value", "label": "值", "type": "text", "required": True},
        ],
    },
    "stringConcat": {
        "label": "字符串拼接",
        "categoryOrder": 45,
        "commandOrder": 30,
        "enabled": True,
        "category": "变量与数据",
        "icon": "fa-link",
        "iconColor": "text-indigo-500",
        "bgColor": "bg-indigo-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "stringConcat", "local": True}},
        "fields": [
            {"name": "targetVar", "label": "目标变量", "type": "varName", "required": True},
            {"name": "part1", "label": "片段1", "type": "text", "required": True},
            {"name": "part2", "label": "片段2", "type": "text", "required": False},
            {"name": "part3", "label": "片段3", "type": "text", "required": False},
        ],
    },
    "increment": {
        "label": "计数器累加",
        "categoryOrder": 45,
        "commandOrder": 40,
        "enabled": True,
        "category": "变量与数据",
        "icon": "fa-plus-minus",
        "iconColor": "text-indigo-500",
        "bgColor": "bg-indigo-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "increment", "local": True}},
        "fields": [
            {"name": "varName", "label": "变量名", "type": "varName", "required": True},
            {"name": "step", "label": "步长", "type": "number", "default": 1},
        ],
    },
    "setDictValue": {
        "label": "设置字典值",
        "categoryOrder": 45,
        "commandOrder": 50,
        "enabled": True,
        "category": "变量与数据",
        "icon": "fa-pen-to-square",
        "iconColor": "text-indigo-500",
        "bgColor": "bg-indigo-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "setDictValue", "local": True}},
        "fields": [
            {"name": "dictName", "label": "字典变量", "type": "varName", "required": True},
            {"name": "key", "label": "键", "type": "text", "required": True},
            {"name": "value", "label": "值", "type": "text", "required": True},
        ],
    },
    "getDictValue": {
        "label": "获取字典值",
        "categoryOrder": 45,
        "commandOrder": 60,
        "enabled": True,
        "category": "变量与数据",
        "icon": "fa-book-open",
        "iconColor": "text-indigo-500",
        "bgColor": "bg-indigo-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "getDictValue", "local": True}},
        "fields": [
            {"name": "dictName", "label": "字典变量", "type": "varName", "required": True},
            {"name": "key", "label": "键", "type": "text", "required": True},
            _var_field("varName", "保存到变量"),
        ],
    },
    "removeDictKey": {
        "label": "删除字典键",
        "categoryOrder": 45,
        "commandOrder": 70,
        "enabled": True,
        "category": "变量与数据",
        "icon": "fa-eraser",
        "iconColor": "text-indigo-500",
        "bgColor": "bg-indigo-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "removeDictKey", "local": True}},
        "fields": [
            {"name": "dictName", "label": "字典变量", "type": "varName", "required": True},
            {"name": "key", "label": "键", "type": "text", "required": True},
        ],
    },
    "readTableCell": {
        "label": "读取表格单元格",
        "categoryOrder": 65,
        "commandOrder": 10,
        "enabled": True,
        "category": "数据表格",
        "icon": "fa-table-cells",
        "iconColor": "text-indigo-500",
        "bgColor": "bg-indigo-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "readTableCell", "local": True}},
        "fields": [
            {"name": "rowIndex", "label": "行号(从0开始)", "type": "number", "default": 0},
            {"name": "columnName", "label": "列名", "type": "text", "required": True},
            _var_field("varName", "保存到变量"),
        ],
    },
    "writeTableCell": {
        "label": "写入表格单元格",
        "categoryOrder": 65,
        "commandOrder": 20,
        "enabled": True,
        "category": "数据表格",
        "icon": "fa-pen-to-square",
        "iconColor": "text-indigo-500",
        "bgColor": "bg-indigo-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "writeTableCell", "local": True}},
        "fields": [
            {"name": "rowIndex", "label": "行号(从0开始)", "type": "number", "default": 0},
            {"name": "columnName", "label": "列名", "type": "text", "required": True},
            {"name": "value", "label": "值", "type": "text", "required": True},
        ],
    },
    "getTableRowCount": {
        "label": "获取表格行数",
        "categoryOrder": 65,
        "commandOrder": 30,
        "enabled": True,
        "category": "数据表格",
        "icon": "fa-list-ol",
        "iconColor": "text-indigo-500",
        "bgColor": "bg-indigo-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "getTableRowCount", "local": True}},
        "fields": [
            _var_field("varName", "保存到变量"),
        ],
    },
    "writeTableRow": {
        "label": "写入表格行",
        "categoryOrder": 65,
        "commandOrder": 40,
        "enabled": True,
        "category": "数据表格",
        "icon": "fa-table-cells-row",
        "iconColor": "text-indigo-500",
        "bgColor": "bg-indigo-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "writeTableRow", "local": True}},
        "fields": [
            {"name": "writeMode", "label": "写入方式", "type": "select", "options": [{"label": "追加一行", "value": "append"}, {"label": "插入一行", "value": "insert"}, {"label": "覆盖一行", "value": "overwrite"}], "default": "append"},
            {"name": "rowIndex", "label": "行号(插入/覆盖时生效)", "type": "number", "default": 0},
            {"name": "rowData", "label": "行数据(列表或字典)", "type": "textarea", "required": True},
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 10. 输出与日志 (Output)
    # ═══════════════════════════════════════════════════════════════
    "log": {
        "label": "记录日志",
        "categoryOrder": 110,
        "commandOrder": 10,
        "enabled": True,
        "category": "输出与日志",
        "icon": "fa-terminal",
        "iconColor": "text-gray-600",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "log", "local": True}},
        "fields": [
            {"name": "message", "label": "日志内容", "type": "text", "required": True},
            {"name": "level", "label": "级别", "type": "select", "options": [{"label": "信息", "value": "info"}, {"label": "警告", "value": "warn"}, {"label": "错误", "value": "error"}], "default": "info"},
        ],
    },
    "takeScreenshot": {
        "label": "页面截图",
        "categoryOrder": 110,
        "commandOrder": 30,
        "enabled": False,
        "category": "输出与日志",
        "icon": "fa-camera",
        "iconColor": "text-gray-600",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            _window_var_field(),
            {"name": "savePath", "label": "保存路径", "type": "text", "required": True, "placeholder": "screenshots/001.png"},
            {"name": "fullPage", "label": "整页截图", "type": "bool", "default": False},
            _element_name_field(required=False),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 11. 鼠标键盘 (Mouse/Keyboard)
    # ═══════════════════════════════════════════════════════════════
    "keyCombo": {
        "label": "组合键",
        "categoryOrder": 120,
        "commandOrder": 10,
        "enabled": False,
        "category": "鼠标键盘",
        "icon": "fa-keyboard",
        "iconColor": "text-gray-600",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            {"name": "keys", "label": "按键组合", "type": "text", "required": True, "placeholder": "Ctrl+A 或 Ctrl+Shift+T"},
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 12. 网络请求 (Network)
    # ═══════════════════════════════════════════════════════════════
    "httpRequest": {
        "label": "HTTP请求",
        "categoryOrder": 130,
        "commandOrder": 10,
        "enabled": True,
        "category": "网络请求",
        "icon": "fa-globe",
        "iconColor": "text-blue-700",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "httpRequest", "local": True}},
        "fields": [
            {"name": "method", "label": "方法", "type": "select", "options": [{"label": "GET", "value": "GET"}, {"label": "POST", "value": "POST"}, {"label": "PUT", "value": "PUT"}, {"label": "DELETE", "value": "DELETE"}], "default": "GET"},
            {"name": "url", "label": "URL", "type": "text", "required": True},
            {"name": "headers", "label": "Headers(JSON)", "type": "textarea", "required": False},
            {"name": "body", "label": "Body", "type": "textarea", "required": False},
            _timeout_field(30),
            _var_field("resultVar", "保存响应到变量"),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 13. AI 集成
    # ═══════════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════════
    # 14. 子流程
    # ═══════════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════════
    # 15. 异常处理
    # ═══════════════════════════════════════════════════════════════
    "try": {
        "label": "捕获异常",
        "categoryOrder": 160,
        "commandOrder": 10,
        "enabled": True,
        "category": "异常处理",
        "icon": "fa-shield-halved",
        "iconColor": "text-red-500",
        "bgColor": "bg-red-50",
        "isContainer": True,
        "closesWith": "endTry",
        "fields": [],
    },
    "catch": {
        "label": "异常处理",
        "categoryOrder": 160,
        "commandOrder": 20,
        "enabled": True,
        "category": "异常处理",
        "icon": "fa-bug",
        "iconColor": "text-red-500",
        "bgColor": "bg-red-50",
        "isContainer": True,
        "isBranch": True,
        "closesWith": "endTry",
        "fields": [
            {"name": "errorVar", "label": "错误变量名", "type": "varName", "default": "error"},
        ],
    },
    "endTry": {
        "label": "结束捕获",
        "categoryOrder": 160,
        "commandOrder": 30,
        "enabled": True,
        "category": "异常处理",
        "icon": "fa-shield-halved",
        "iconColor": "text-red-500",
        "bgColor": "bg-red-50",
        "isContainer": False,
        "fields": [],
        "isStructural": True,
    },

    # ═══════════════════════════════════════════════════════════════
    # 16. 自定义代码 (Custom)
    # ═══════════════════════════════════════════════════════════════
    "custom": {
        "label": "自定义代码",
        "categoryOrder": 170,
        "commandOrder": 10,
        "enabled": True,
        "category": "自定义",
        "icon": "fa-code",
        "iconColor": "text-gray-500",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "custom", "local": True}},
        "fields": [
            {"name": "code", "label": "Python代码", "type": "textarea", "required": True, "rows": 6, "placeholder": "# 直接插入的Python代码\nprint('hello')"},
            {"name": "description", "label": "描述", "type": "text", "required": False},
            _var_field("resultVar", "返回值变量"),
        ],
    },
    "executeJs": {
        "label": "执行JS",
        "categoryOrder": 170,
        "commandOrder": 20,
        "enabled": True,
        "category": "自定义",
        "icon": "fa-js",
        "iconColor": "text-gray-500",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "executeJs", "local": False}},
        "fields": [
            {"name": "script", "label": "JavaScript代码", "type": "textarea", "required": True, "rows": 4},
            _var_field("resultVar", "返回值变量"),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 17. Hover (保留兼容)
    # ═══════════════════════════════════════════════════════════════
    "hover": {
        "label": "悬停",
        "categoryOrder": 20,
        "commandOrder": 30,
        "enabled": True,
        "category": "元素点击",
        "icon": "fa-hand-pointer",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "hover", "local": False}},
        "fields": [
            _element_name_field(),
            _scope_field(),
        ],
    },
    "unhover": {
        "label": "取消悬停",
        "categoryOrder": 20,
        "commandOrder": 35,
        "enabled": True,
        "category": "元素点击",
        "icon": "fa-hand-pointer",
        "iconColor": "text-gray-500",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "runtimes": {"extension": {"handler": "unhover", "local": False}},
        "fields": [
            _window_var_field(),
            _element_name_field(required=False),
            _scope_field(),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 18. 网络拦截 (Network Interception)
    # ═══════════════════════════════════════════════════════════════
}


# ─── Helpers ──────────────────────────────────────────────────────

def get_command(type_name: str) -> dict | None:
    cmd = COMMAND_REGISTRY.get(type_name)
    if cmd is None:
        return None
    result = copy.deepcopy(cmd)
    # 为普通指令自动附加通用高级参数
    if not cmd.get("isContainer") and not cmd.get("isStructural"):
        result["fields"] = _attach_common_advanced(cmd.get("fields", []))
    return result


def list_categories() -> list[str]:
    """返回所有分类名称（去重且保持注册顺序）"""
    seen = set()
    result = []
    for cmd in COMMAND_REGISTRY.values():
        cat = cmd["category"]
        if cat not in seen:
            seen.add(cat)
            result.append(cat)
    return result


def list_commands_by_category() -> dict[str, list[dict]]:
    """按分类分组返回指令列表"""
    result: dict[str, list[dict]] = {}
    for type_name, cmd in COMMAND_REGISTRY.items():
        cat = cmd["category"]
        if cat not in result:
            result[cat] = []
        cmd_copy = copy.deepcopy(cmd)
        # 为普通指令自动附加通用高级参数（容器/结构标记除外）
        if not cmd.get("isContainer") and not cmd.get("isStructural"):
            cmd_copy["fields"] = _attach_common_advanced(cmd.get("fields", []))
        result[cat].append({"type": type_name, **cmd_copy})
    return result


def get_container_types() -> list[str]:
    """返回所有可包含子节点的指令类型"""
    return [t for t, c in COMMAND_REGISTRY.items() if c.get("isContainer")]


def get_structural_types() -> list[str]:
    """返回结构标记型指令（endIf/endFor/endTry）"""
    return [t for t, c in COMMAND_REGISTRY.items() if c.get("isStructural")]


def get_branch_types() -> list[str]:
    """返回分支切换型指令（else/catch）— 既关闭前一分支又开启新分支"""
    return [t for t, c in COMMAND_REGISTRY.items() if c.get("isBranch")]


def enrich_command_meta(row: dict) -> dict:
    """从 COMMAND_REGISTRY 读取 runtime 元数据并附加到数据库行字典。
    若数据库已存储 handler/local，优先使用数据库值（允许运行时覆盖）。"""
    reg = COMMAND_REGISTRY.get(row.get("type", ""), {})
    ext = reg.get("runtimes", {}).get("extension")

    # 优先数据库值，其次 registry
    db_handler = row.get("handler")
    db_local = row.get("local")
    if db_handler is not None or db_local is not None:
        row["handler"] = db_handler
        row["local"] = db_local
        row["hasRuntime"] = bool(db_handler is not None)
    else:
        row["handler"] = ext.get("handler") if ext else None
        row["local"] = ext.get("local") if ext else None
        row["hasRuntime"] = bool(ext)

    # 补充结构元数据（若数据库未存储）
    if not row.get("closesWith"):
        row["closesWith"] = reg.get("closesWith") or None
    return row


