"""
Workflow command registry — schema-driven instruction catalog.

Design philosophy (影刀-style granularity):
- Each command is a specific use-case, not a generic action + parameters.
- Commands declare their own form fields via a schema; the frontend renders dynamically.
- Container commands (if/for/try) can hold child nodes.
"""

from typing import Any

# ─── Field type helpers ───────────────────────────────────────────

def _locator_field(required: bool = True) -> dict:
    return {"name": "locator", "label": "元素定位器", "type": "locator", "required": required}

def _locator_type_field(default: str = "css") -> dict:
    return {
        "name": "locator_type",
        "label": "定位方式",
        "type": "select",
        "options": ["css", "xpath", "id", "class", "text", "data-attr"],
        "default": default,
    }

def _method_field(default: str = "ele") -> dict:
    return {
        "name": "method",
        "label": "查找方法",
        "type": "select",
        "options": ["ele", "eles", "s_ele", "s_eles"],
        "default": default,
    }

def _timeout_field(default: int = 10) -> dict:
    return {"name": "timeout", "label": "超时(秒)", "type": "number", "default": default}

def _var_field(name: str = "varName", label: str = "保存到变量") -> dict:
    return {"name": name, "label": label, "type": "varName", "required": False}

# ─── Command registry ─────────────────────────────────────────────

COMMAND_REGISTRY: dict[str, dict[str, Any]] = {
    # ═══════════════════════════════════════════════════════════════
    # 1. 页面导航 (Navigation)
    # ═══════════════════════════════════════════════════════════════
    "navigate": {
        "label": "打开网页",
        "category": "页面导航",
        "icon": "fa-globe",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            {"name": "url", "label": "网址", "type": "text", "required": True, "placeholder": "https://..."},
            {"name": "waitLoad", "label": "等待加载完成", "type": "bool", "default": True},
            _timeout_field(30),
        ],
    },
    "goBack": {
        "label": "返回上一页",
        "category": "页面导航",
        "icon": "fa-arrow-left",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [],
    },
    "goForward": {
        "label": "前进",
        "category": "页面导航",
        "icon": "fa-arrow-right",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [],
    },
    "refresh": {
        "label": "刷新页面",
        "category": "页面导航",
        "icon": "fa-rotate-right",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            {"name": "hardReload", "label": "强制刷新(忽略缓存)", "type": "bool", "default": False},
        ],
    },
    "newTab": {
        "label": "新建标签页",
        "category": "页面导航",
        "icon": "fa-plus",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            {"name": "url", "label": "网址(可选)", "type": "text", "required": False, "placeholder": "https://..."},
        ],
    },
    "closeTab": {
        "label": "关闭当前标签页",
        "category": "页面导航",
        "icon": "fa-xmark",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [],
    },
    "switchTab": {
        "label": "切换标签页",
        "category": "页面导航",
        "icon": "fa-window-restore",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            {"name": "by", "label": "切换方式", "type": "select", "options": ["index", "url", "title"], "default": "index"},
            {"name": "value", "label": "值", "type": "text", "required": True, "placeholder": "0 或 https://... 或 标题"},
        ],
    },
    "switchToFrame": {
        "label": "进入 iframe",
        "category": "页面导航",
        "icon": "fa-object-group",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
        ],
    },
    "switchToMain": {
        "label": "退出 iframe",
        "category": "页面导航",
        "icon": "fa-object-ungroup",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [],
    },
    "getCurrentUrl": {
        "label": "获取当前URL",
        "category": "页面导航",
        "icon": "fa-link",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [_var_field()],
    },
    "getPageTitle": {
        "label": "获取页面标题",
        "category": "页面导航",
        "icon": "fa-heading",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [_var_field()],
    },

    # ═══════════════════════════════════════════════════════════════
    # 2. 元素点击 (Click)
    # ═══════════════════════════════════════════════════════════════
    "click": {
        "label": "点击元素",
        "category": "元素点击",
        "icon": "fa-mouse-pointer",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            _method_field(),
            {"name": "forceJs", "label": "强制JS点击", "type": "bool", "default": False},
        ],
    },
    "doubleClick": {
        "label": "双击元素",
        "category": "元素点击",
        "icon": "fa-mouse-pointer",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            _method_field(),
        ],
    },
    "rightClick": {
        "label": "右键点击",
        "category": "元素点击",
        "icon": "fa-mouse-pointer",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            _method_field(),
        ],
    },
    "clickByIndex": {
        "label": "点击第N个相似元素",
        "category": "元素点击",
        "icon": "fa-hand-pointer",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            {"name": "index", "label": "序号(从0开始)", "type": "number", "default": 0},
        ],
    },
    "clickIfExists": {
        "label": "如果存在则点击",
        "category": "元素点击",
        "icon": "fa-hand-point-up",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            _method_field(),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 3. 文本输入 (Input)
    # ═══════════════════════════════════════════════════════════════
    "input": {
        "label": "输入文本",
        "category": "文本输入",
        "icon": "fa-keyboard",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            {"name": "text", "label": "输入内容", "type": "text", "required": True},
            {"name": "clearFirst", "label": "先清空", "type": "bool", "default": True},
        ],
    },
    "inputAndPressEnter": {
        "label": "输入并回车",
        "category": "文本输入",
        "icon": "fa-keyboard",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            {"name": "text", "label": "输入内容", "type": "text", "required": True},
            {"name": "clearFirst", "label": "先清空", "type": "bool", "default": True},
        ],
    },
    "clearInput": {
        "label": "清空输入框",
        "category": "文本输入",
        "icon": "fa-eraser",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
        ],
    },
    "pressKey": {
        "label": "按键",
        "category": "文本输入",
        "icon": "fa-arrow-turn-up",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            {"name": "key", "label": "按键", "type": "select", "options": ["Enter", "Tab", "Esc", "ArrowDown", "ArrowUp", "PageDown", "PageUp", "Space", "Backspace"], "default": "Enter"},
        ],
    },
    "selectOption": {
        "label": "下拉框选择",
        "category": "文本输入",
        "icon": "fa-list",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            {"name": "by", "label": "选择方式", "type": "select", "options": ["value", "label", "index"], "default": "label"},
            {"name": "value", "label": "值", "type": "text", "required": True},
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 4. 数据提取 (Extraction)
    # ═══════════════════════════════════════════════════════════════
    "getText": {
        "label": "获取元素文本",
        "category": "数据提取",
        "icon": "fa-font",
        "iconColor": "text-green-500",
        "bgColor": "bg-green-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            _method_field(),
            _var_field(),
        ],
    },
    "getAttr": {
        "label": "获取元素属性",
        "category": "数据提取",
        "icon": "fa-tag",
        "iconColor": "text-green-500",
        "bgColor": "bg-green-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            _method_field(),
            {"name": "attrName", "label": "属性名", "type": "text", "required": True, "placeholder": "href / src / data-id"},
            _var_field(),
        ],
    },
    "getHtml": {
        "label": "获取元素HTML",
        "category": "数据提取",
        "icon": "fa-code",
        "iconColor": "text-green-500",
        "bgColor": "bg-green-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            _method_field(),
            {"name": "mode", "label": "模式", "type": "select", "options": ["inner", "outer"], "default": "inner"},
            _var_field(),
        ],
    },
    "getValue": {
        "label": "获取输入框值",
        "category": "数据提取",
        "icon": "fa-i-cursor",
        "iconColor": "text-green-500",
        "bgColor": "bg-green-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            _var_field(),
        ],
    },
    "getElementCount": {
        "label": "获取元素数量",
        "category": "数据提取",
        "icon": "fa-hashtag",
        "iconColor": "text-green-500",
        "bgColor": "bg-green-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            _var_field(),
        ],
    },
    "getElementList": {
        "label": "获取相似元素列表",
        "category": "数据提取",
        "icon": "fa-list-ul",
        "iconColor": "text-green-500",
        "bgColor": "bg-green-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            _var_field(),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 5. 滚动 (Scroll)
    # ═══════════════════════════════════════════════════════════════
    "scrollToBottom": {
        "label": "滚动到底部",
        "category": "滚动",
        "icon": "fa-arrow-down",
        "iconColor": "text-cyan-500",
        "bgColor": "bg-cyan-50",
        "isContainer": False,
        "fields": [
            {"name": "smooth", "label": "平滑滚动", "type": "bool", "default": False},
        ],
    },
    "scrollToTop": {
        "label": "滚动到顶部",
        "category": "滚动",
        "icon": "fa-arrow-up",
        "iconColor": "text-cyan-500",
        "bgColor": "bg-cyan-50",
        "isContainer": False,
        "fields": [
            {"name": "smooth", "label": "平滑滚动", "type": "bool", "default": False},
        ],
    },
    "scrollIntoView": {
        "label": "滚动到元素",
        "category": "滚动",
        "icon": "fa-crosshairs",
        "iconColor": "text-cyan-500",
        "bgColor": "bg-cyan-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            {"name": "block", "label": "对齐方式", "type": "select", "options": ["start", "center", "end", "nearest"], "default": "center"},
        ],
    },
    "scrollBy": {
        "label": "滚动指定距离",
        "category": "滚动",
        "icon": "fa-arrows-up-down",
        "iconColor": "text-cyan-500",
        "bgColor": "bg-cyan-50",
        "isContainer": False,
        "fields": [
            {"name": "x", "label": "水平距离(px)", "type": "number", "default": 0},
            {"name": "y", "label": "垂直距离(px)", "type": "number", "default": 500},
        ],
    },
    "infiniteScroll": {
        "label": "无限滚动",
        "category": "滚动",
        "icon": "fa-infinity",
        "iconColor": "text-cyan-500",
        "bgColor": "bg-cyan-50",
        "isContainer": False,
        "fields": [
            {"name": "endMarker", "label": "结束标记文本", "type": "text", "required": False, "placeholder": "如: - THE END -"},
            {"name": "maxScrolls", "label": "最大滚动次数", "type": "number", "default": 50},
            {"name": "interval", "label": "滚动间隔(秒)", "type": "number", "default": 2.0},
            {"name": "clickMoreSelector", "label": "点击展开选择器", "type": "text", "required": False, "placeholder": "如 .show-more"},
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 6. 等待 (Wait)
    # ═══════════════════════════════════════════════════════════════
    "sleep": {
        "label": "等待固定时间",
        "category": "等待",
        "icon": "fa-clock",
        "iconColor": "text-gray-500",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            {"name": "seconds", "label": "等待秒数", "type": "number", "default": 1.0},
        ],
    },
    "waitForElement": {
        "label": "等待元素出现",
        "category": "等待",
        "icon": "fa-eye",
        "iconColor": "text-gray-500",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            _timeout_field(10),
        ],
    },
    "waitForElementHide": {
        "label": "等待元素消失",
        "category": "等待",
        "icon": "fa-eye-slash",
        "iconColor": "text-gray-500",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            _timeout_field(10),
        ],
    },
    "waitForText": {
        "label": "等待文本出现",
        "category": "等待",
        "icon": "fa-comment-dots",
        "iconColor": "text-gray-500",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            {"name": "text", "label": "期望文本", "type": "text", "required": True},
            _timeout_field(10),
        ],
    },
    "waitForUrl": {
        "label": "等待URL变化",
        "category": "等待",
        "icon": "fa-link",
        "iconColor": "text-gray-500",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            {"name": "urlPattern", "label": "URL包含", "type": "text", "required": True},
            _timeout_field(10),
        ],
    },
    "waitForLoad": {
        "label": "等待页面加载",
        "category": "等待",
        "icon": "fa-spinner",
        "iconColor": "text-gray-500",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            {"name": "state", "label": "加载状态", "type": "select", "options": ["domcontentloaded", "networkidle"], "default": "networkidle"},
            _timeout_field(30),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 7. 条件判断 (Condition) — 影刀式精细拆分 ⭐
    # ═══════════════════════════════════════════════════════════════
    "ifElementExists": {
        "label": "如果元素存在",
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            _method_field(),
        ],
    },
    "ifElementNotExists": {
        "label": "如果元素不存在",
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            _method_field(),
        ],
    },
    "ifElementVisible": {
        "label": "如果元素可见",
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            _method_field(),
        ],
    },
    "ifTextContains": {
        "label": "如果元素文本包含",
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            {"name": "text", "label": "包含文本", "type": "text", "required": True},
        ],
    },
    "ifTextEquals": {
        "label": "如果元素文本等于",
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            {"name": "text", "label": "等于文本", "type": "text", "required": True},
        ],
    },
    "ifUrlContains": {
        "label": "如果URL包含",
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "fields": [
            {"name": "urlPattern", "label": "URL包含", "type": "text", "required": True},
        ],
    },
    "ifVarEquals": {
        "label": "如果变量等于",
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "fields": [
            {"name": "varName", "label": "变量名", "type": "varName", "required": True},
            {"name": "value", "label": "比较值", "type": "text", "required": True},
            {"name": "valueType", "label": "值类型", "type": "select", "options": ["string", "number", "bool"], "default": "string"},
        ],
    },
    "ifVarGreaterThan": {
        "label": "如果变量大于",
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "fields": [
            {"name": "varName", "label": "变量名", "type": "varName", "required": True},
            {"name": "value", "label": "比较值", "type": "number", "required": True},
        ],
    },
    "else": {
        "label": "否则",
        "category": "条件判断",
        "icon": "fa-code-branch",
        "iconColor": "text-orange-500",
        "bgColor": "bg-orange-50",
        "isContainer": True,
        "isBranch": True,
        "fields": [],
    },
    "endIf": {
        "label": "结束如果",
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
        "category": "循环",
        "icon": "fa-sync",
        "iconColor": "text-purple-500",
        "bgColor": "bg-purple-50",
        "isContainer": True,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            {"name": "itemVar", "label": "元素变量名", "type": "varName", "default": "item"},
            {"name": "indexVar", "label": "索引变量名", "type": "varName", "default": "index"},
        ],
    },
    "forRange": {
        "label": "循环次数",
        "category": "循环",
        "icon": "fa-repeat",
        "iconColor": "text-purple-500",
        "bgColor": "bg-purple-50",
        "isContainer": True,
        "fields": [
            {"name": "start", "label": "起始值", "type": "number", "default": 0},
            {"name": "end", "label": "结束值", "type": "number", "default": 10},
            {"name": "step", "label": "步长", "type": "number", "default": 1},
            {"name": "varName", "label": "循环变量名", "type": "varName", "default": "i"},
        ],
    },
    "forList": {
        "label": "循环列表",
        "category": "循环",
        "icon": "fa-list-ol",
        "iconColor": "text-purple-500",
        "bgColor": "bg-purple-50",
        "isContainer": True,
        "fields": [
            {"name": "listVar", "label": "列表变量", "type": "varName", "required": True},
            {"name": "itemVar", "label": "元素变量名", "type": "varName", "default": "item"},
            {"name": "indexVar", "label": "索引变量名", "type": "varName", "default": "index"},
        ],
    },
    "whileCondition": {
        "label": "循环直到条件成立",
        "category": "循环",
        "icon": "fa-rotate",
        "iconColor": "text-purple-500",
        "bgColor": "bg-purple-50",
        "isContainer": True,
        "fields": [
            {"name": "conditionType", "label": "条件类型", "type": "select", "options": ["elementExists", "elementNotExists", "urlContains", "varEquals"], "default": "elementExists"},
            {"name": "locator", "label": "元素定位器", "type": "locator", "required": False},
            {"name": "locator_type", "label": "定位方式", "type": "select", "options": ["css", "xpath", "text"], "default": "css"},
            {"name": "urlPattern", "label": "URL包含", "type": "text", "required": False},
            {"name": "varName", "label": "变量名", "type": "varName", "required": False},
            {"name": "varValue", "label": "变量值", "type": "text", "required": False},
            {"name": "maxIterations", "label": "最大迭代次数", "type": "number", "default": 100},
        ],
    },
    "break": {
        "label": "跳出循环",
        "category": "循环",
        "icon": "fa-ban",
        "iconColor": "text-purple-500",
        "bgColor": "bg-purple-50",
        "isContainer": False,
        "fields": [],
    },
    "continue": {
        "label": "继续下一次",
        "category": "循环",
        "icon": "fa-forward-step",
        "iconColor": "text-purple-500",
        "bgColor": "bg-purple-50",
        "isContainer": False,
        "fields": [],
    },
    "endFor": {
        "label": "结束循环",
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
        "category": "变量与数据",
        "icon": "fa-superscript",
        "iconColor": "text-indigo-500",
        "bgColor": "bg-indigo-50",
        "isContainer": False,
        "fields": [
            {"name": "name", "label": "变量名", "type": "varName", "required": True},
            {"name": "value", "label": "值", "type": "text", "required": True},
            {"name": "valueType", "label": "值类型", "type": "select", "options": ["string", "number", "bool", "list"], "default": "string"},
        ],
    },
    "appendToList": {
        "label": "追加到列表",
        "category": "变量与数据",
        "icon": "fa-plus",
        "iconColor": "text-indigo-500",
        "bgColor": "bg-indigo-50",
        "isContainer": False,
        "fields": [
            {"name": "listName", "label": "列表变量", "type": "varName", "required": True},
            {"name": "value", "label": "值", "type": "text", "required": True},
        ],
    },
    "stringConcat": {
        "label": "字符串拼接",
        "category": "变量与数据",
        "icon": "fa-link",
        "iconColor": "text-indigo-500",
        "bgColor": "bg-indigo-50",
        "isContainer": False,
        "fields": [
            {"name": "targetVar", "label": "目标变量", "type": "varName", "required": True},
            {"name": "part1", "label": "片段1", "type": "text", "required": True},
            {"name": "part2", "label": "片段2", "type": "text", "required": False},
            {"name": "part3", "label": "片段3", "type": "text", "required": False},
        ],
    },
    "increment": {
        "label": "计数器累加",
        "category": "变量与数据",
        "icon": "fa-plus-minus",
        "iconColor": "text-indigo-500",
        "bgColor": "bg-indigo-50",
        "isContainer": False,
        "fields": [
            {"name": "varName", "label": "变量名", "type": "varName", "required": True},
            {"name": "step", "label": "步长", "type": "number", "default": 1},
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 10. 输出与日志 (Output)
    # ═══════════════════════════════════════════════════════════════
    "log": {
        "label": "记录日志",
        "category": "输出与日志",
        "icon": "fa-terminal",
        "iconColor": "text-gray-600",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            {"name": "message", "label": "日志内容", "type": "text", "required": True},
            {"name": "level", "label": "级别", "type": "select", "options": ["info", "warn", "error"], "default": "info"},
        ],
    },
    "pushItem": {
        "label": "推送结果项",
        "category": "输出与日志",
        "icon": "fa-upload",
        "iconColor": "text-gray-600",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            {"name": "dataExpr", "label": "数据(JSON)", "type": "textarea", "required": True, "placeholder": '{"title": "${titleVar}", "url": "${urlVar}"}'},
        ],
    },
    "takeScreenshot": {
        "label": "页面截图",
        "category": "输出与日志",
        "icon": "fa-camera",
        "iconColor": "text-gray-600",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            {"name": "savePath", "label": "保存路径", "type": "text", "required": True, "placeholder": "screenshots/001.png"},
            {"name": "fullPage", "label": "整页截图", "type": "bool", "default": False},
            {"name": "locator", "label": "元素定位器(可选,仅截元素)", "type": "locator", "required": False},
        ],
    },
    "saveToFile": {
        "label": "保存数据到文件",
        "category": "输出与日志",
        "icon": "fa-file-export",
        "iconColor": "text-gray-600",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            {"name": "dataVar", "label": "数据变量", "type": "varName", "required": True},
            {"name": "filePath", "label": "文件路径", "type": "text", "required": True},
            {"name": "format", "label": "格式", "type": "select", "options": ["json", "csv"], "default": "json"},
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 11. 鼠标键盘 (Mouse/Keyboard)
    # ═══════════════════════════════════════════════════════════════
    "keyCombo": {
        "label": "组合键",
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
        "category": "网络请求",
        "icon": "fa-globe",
        "iconColor": "text-blue-700",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            {"name": "method", "label": "方法", "type": "select", "options": ["GET", "POST", "PUT", "DELETE"], "default": "GET"},
            {"name": "url", "label": "URL", "type": "text", "required": True},
            {"name": "headers", "label": "Headers(JSON)", "type": "textarea", "required": False},
            {"name": "body", "label": "Body", "type": "textarea", "required": False},
            {"name": "timeout", "label": "超时(秒)", "type": "number", "default": 30},
            _var_field("resultVar", "保存响应到变量"),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 13. AI 集成
    # ═══════════════════════════════════════════════════════════════
    "callAiApp": {
        "label": "调用AI应用",
        "category": "AI集成",
        "icon": "fa-brain",
        "iconColor": "text-indigo-500",
        "bgColor": "bg-indigo-50",
        "isContainer": False,
        "fields": [
            {"name": "appType", "label": "AI应用类型", "type": "text", "required": True},
            {"name": "inputs", "label": "输入参数(JSON)", "type": "textarea", "required": True},
            _var_field("resultVar", "保存结果到变量"),
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 14. 子流程
    # ═══════════════════════════════════════════════════════════════
    "callWorkflow": {
        "label": "调用其他流程",
        "category": "子流程",
        "icon": "fa-sitemap",
        "iconColor": "text-pink-500",
        "bgColor": "bg-pink-50",
        "isContainer": False,
        "fields": [
            {"name": "workflowId", "label": "流程ID", "type": "number", "required": True},
            {"name": "inputs", "label": "输入参数(JSON)", "type": "textarea", "required": False},
        ],
    },
    "return": {
        "label": "结束并返回",
        "category": "子流程",
        "icon": "fa-flag-checkered",
        "iconColor": "text-pink-500",
        "bgColor": "bg-pink-50",
        "isContainer": False,
        "fields": [
            {"name": "resultExpr", "label": "返回数据(JSON)", "type": "textarea", "required": False},
        ],
    },

    # ═══════════════════════════════════════════════════════════════
    # 15. 异常处理
    # ═══════════════════════════════════════════════════════════════
    "try": {
        "label": "捕获异常",
        "category": "异常处理",
        "icon": "fa-shield-halved",
        "iconColor": "text-red-500",
        "bgColor": "bg-red-50",
        "isContainer": True,
        "fields": [],
    },
    "catch": {
        "label": "异常处理",
        "category": "异常处理",
        "icon": "fa-bug",
        "iconColor": "text-red-500",
        "bgColor": "bg-red-50",
        "isContainer": True,
        "isBranch": True,
        "fields": [
            {"name": "errorVar", "label": "错误变量名", "type": "varName", "default": "error"},
        ],
    },
    "endTry": {
        "label": "结束捕获",
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
        "category": "自定义",
        "icon": "fa-code",
        "iconColor": "text-gray-500",
        "bgColor": "bg-gray-50",
        "isContainer": False,
        "fields": [
            {"name": "code", "label": "Python代码", "type": "textarea", "required": True, "rows": 6, "placeholder": "# 直接插入的Python代码\nprint('hello')"},
            {"name": "description", "label": "描述", "type": "text", "required": False},
        ],
    },
    "executeJs": {
        "label": "执行JS",
        "category": "自定义",
        "icon": "fa-js",
        "iconColor": "text-yellow-500",
        "bgColor": "bg-yellow-50",
        "isContainer": False,
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
        "category": "元素点击",
        "icon": "fa-hand-pointer",
        "iconColor": "text-blue-500",
        "bgColor": "bg-blue-50",
        "isContainer": False,
        "fields": [
            _locator_field(),
            _locator_type_field(),
            _method_field(),
        ],
    },
}


# ─── Helpers ──────────────────────────────────────────────────────

def get_command(type_name: str) -> dict | None:
    return COMMAND_REGISTRY.get(type_name)


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
        result[cat].append({"type": type_name, **cmd})
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
