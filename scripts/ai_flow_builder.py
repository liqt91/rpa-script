#!/usr/bin/env python3
"""
AI 流程编排助手 —— 输入意图 + 元素，AI 生成工作流 JSON。

用法：
    python scripts/ai_flow_builder.py -i "意图描述" -e "元素1,元素2" -o flow.json

AI 服务商（.env 配置 AI_API_KEY，默认 DeepSeek）：
    DeepSeek（默认）:  只需 AI_API_KEY=sk-xxx
    OpenAI:            AI_PROVIDER=openai  AI_API_KEY=sk-xxx
    自定义:            AI_PROVIDER=custom  AI_API_URL=... AI_MODEL=... AI_API_KEY=...

输出：可导入工作流编辑器的 JSON
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ── AI 服务商预设 ──────────────────────────────────────────
_PROVIDERS = {
    "deepseek": {
        "url": "https://api.deepseek.com/v1/chat/completions",
        "model": "deepseek-v4-pro",
    },
    "openai": {
        "url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o",
    },
}

# ── 加载 .env ──────────────────────────────────────────────
def _load_env():
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()


# ── 收集所有可用指令 ────────────────────────────────────────
def _load_elements(workflow_id: int, names: list) -> list:
    """从数据库读取元素定义（含选择器），匹配给定的元素名列表。"""
    import sqlite3
    db_path = Path(__file__).resolve().parent.parent / "data" / "data.db"
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    elems = []
    for name in names:
        cur.execute(
            "SELECT name, web_selector, drission_selector, element_kind, relative_selector, anchor_selector "
            "FROM workflow_elements WHERE workflow_id=? AND name=?",
            (workflow_id, name),
        )
        row = cur.fetchone()
        if row:
            d = {"name": row[0], "web_selector": row[1]}
            if row[2]:
                d["drission_selector"] = row[2]
            if row[3]:
                d["element_kind"] = row[3]
            if row[4]:
                d["relative_selector"] = row[4]
            if row[5]:
                d["anchor_selector"] = row[5]
            elems.append(d)
    conn.close()
    return elems


def _load_commands():
    """从 handler registry 读取所有指令定义。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.runtime.workflow.handlers.registry import build_command_registry
    reg = build_command_registry()
    cmds = []
    for t, c in reg.items():
        if not c.get("enabled", True):
            continue
        fields = []
        for f in c.get("fields", []):
            fd = {"name": f["name"], "type": f["type"]}
            if f.get("required"):
                fd["required"] = True
            if f.get("options"):
                fd["options"] = [o if isinstance(o, str) else o.get("value", str(o)) for o in f["options"]]
            if f.get("default") is not None:
                fd["default"] = f["default"]
            if f.get("placeholder"):
                fd["placeholder"] = f["placeholder"]
            fields.append(fd)
        cmds.append({
            "type": t,
            "label": c.get("label", t),
            "category": c.get("category", ""),
            "isContainer": c.get("isContainer", False),
            "closesWith": c.get("closesWith"),
            "isBranch": c.get("isBranch", False),
            "isStructural": c.get("isStructural", False),
            "description": c.get("description", ""),
            "fields": fields,
        })
    return cmds


# ── 指令白名单：只给 AI 看网页抓取场景常用的指令 ─────────
_CORE_COMMANDS = {
    # 容器/流程控制
    "forList", "forRange", "forEachElement", "endFor",
    "ifElementVisible", "ifElementExists", "endIf",
    "whileCondition",
    "try", "catch", "endTry", "else",
    "break", "continue",
    # 变量/数据
    "setVar", "log",
    "writeTableRow", "readTableCell", "getTableRowCount",
    "stringConcat", "increment", "appendToList",
    "custom",
    # 浏览器
    "openBrowser", "closeBrowser", "navigate", "newTab",
    # 页面操作
    "getText", "clickElement", "inputText",
    "scrollToBottom", "scrollOneScreen",
    "sleep", "randomWait",
}


def _filter_commands(cmds: list) -> list:
    """只保留白名单内的指令。"""
    return [c for c in cmds if c["type"] in _CORE_COMMANDS]


# ── 构建 Prompt ─────────────────────────────────────────────
def build_system_prompt(commands: list, elements: list) -> str:
    """构建 AI 编排指令。"""
    cmds_text = []
    for c in commands:
        params = []
        for f in c['fields']:
            p = f['name']
            if f.get('options'):
                p += '=' + '/'.join(str(o) for o in f['options'])
            params.append(p)
        meta = []
        if c['isContainer']:
            meta.append(f"容器")
        if c['closesWith']:
            meta.append(f"被 {c['closesWith']} 关闭")
        if c['isBranch']:
            meta.append("分支标记")
        if c['isStructural']:
            meta.append("结束标记")

        line = f"- {c['type']} ({c['label']})"
        if meta:
            line += f" [{', '.join(meta)}]"
        if params:
            line += f": {', '.join(params)}"
        if c.get('description'):
            line += f"\n  说明: {c['description']}"
        cmds_text.append(line)

    elems_text = "\n".join(f"- {e}" for e in elements) if elements else "(无预捕获元素)"

    return f"""你是一个 RPA 工作流编排助手。根据用户的意图描述，生成一个工作流 JSON。

## ⚠️ 铁律（违反则流程无法运行）

1. **只能用上面清单中的指令 type**，绝对不允许编造新指令。清单里没有的就是不存在。
2. **每个 if* / for* / try 必须有对应的 end*** 结束标记，且 end* 的 parent_id 必须等于容器的 parent_id。
3. **元素名必须用上面"已捕获的页面元素"列表中精确的名字**，不能自己编。如果不知道该用哪个元素，留空 `element_name: null`。
4. **变量是平铺字典**，不支持 `${{a.b}}` 点号访问。要分别保存：getText 存到 `${{标题}}`，然后引用 `${{标题}}`。
5. **custom 代码只能通过以下对象操作**：
   - `_vars` — 所有工作流变量的字典（读：`_vars.get("x")`，写：不要直接写）
   - `_table` — 表格对象，支持 `_table[0][0]`、`_table[0]["A"]`
   - `_log("消息")` — 打印日志
   - 不能使用 `runner.xxx`、`page.xxx` 等
6. **列表变量设置**：setVar 的 valueType 用 `list-input`，value 写 JSON 数组如 `["a","b"]`
7. **写入表格行**：rowData 填 `["${{var1}}", "${{var2}}"]`
8. **stringConcat 的 parts 参数**：填拼接表达式如 `"url前缀" + ${{变量}}`，绝对不能填 JSON 数组。
9. **whileCondition 建议用 forRange 替代**：如果循环固定页数用 forRange(start=0, end=999)，更简单可靠。whileCondition 需设置 conditionType="expression" 且 condition 填 Python 表达式。

## 可用指令清单

{chr(10).join(cmds_text)}

## 已捕获的页面元素

用户已在目标页面上手动捕获了以下元素（在指令中引用元素时用这些名字）：
{elems_text}

## 输出格式

严格输出以下 JSON 结构（不要包含任何解释文字，只输出 JSON）：

{{
  "name": "流程名称",
  "nodes": [
    {{
      "order": 1,
      "type": "指令类型",
      "parent_id": null,
      "extra": {{
        "参数名": "参数值"
      }}
    }}
  ]
}}

## 编排规则

1. 父子关系用 parent_id 表示：子节点 parent_id = 父节点 id
2. 每个节点必须有 order（从 1 开始递增）
3. 容器节点（循环、条件）的子节点 parent_id 指向容器
4. 引用元素用元素名，引用变量用 ${{变量名}}
5. 打开浏览器 (openBrowser) 应在最前面，windowVar 默认 browser1
6. 获取文本 (getText) 的 varName 参数指定保存到的变量名
7. 写入数据行 (writeTableRow) 的 rowData 格式：["${{var1}}", "${{var2}}"]
8. 列表输入 (list-input) 类型参数同样用 JSON 数组格式
9. 遍历元素列表 (forEachElement) 需要 element_name 参数指向列表元素
10. 自动生成必要的父/子关系、order、end* 结束标记
11. 如果意图需要循环，用 forList/forEachElement 等，并配对应的 endFor
12. 如果意图需要条件判断，用 if* 指令，并配对应的 endIf

## 变量命名建议

- 循环项变量：itemVar="当前项" / itemVar="当前关键词"
- 索引变量：indexVar="index"
- 保存结果的变量：varName="标题" / varName="摘要" 等有意义的名称
"""


def build_user_prompt(intent: str) -> str:
    return f"请根据以下意图生成工作流：\n\n{intent}"


# ── AI 调用 ─────────────────────────────────────────────────
def call_ai(system: str, user: str) -> dict:
    provider_name = os.getenv("AI_PROVIDER", "deepseek")
    provider = _PROVIDERS.get(provider_name, {})

    # 优先级: AI_API_URL > provider 默认。OPENAI_* 仅在 provider=openai 时兜底
    api_url = os.getenv("AI_API_URL") or provider.get("url", "")
    if not api_url and provider_name == "openai":
        api_url = os.getenv("OPENAI_BASE_URL", "").rstrip("/") + "/chat/completions"

    api_key = os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY") or ""

    # 优先级: AI_MODEL > AI_DEFAULT_MODEL（仅 openai）> provider 默认
    model = os.getenv("AI_MODEL") or provider.get("model", "")
    if not os.getenv("AI_MODEL") and provider_name == "openai":
        model = os.getenv("AI_DEFAULT_MODEL") or model

    if not api_key:
        print("❌ 未设置 AI_API_KEY，请在 .env 中添加：AI_API_KEY=sk-xxx", file=sys.stderr)
        sys.exit(1)
    if not api_url:
        print("❌ 未找到 API 地址，请设置 AI_API_URL 或 AI_PROVIDER", file=sys.stderr)
        sys.exit(1)

    print(f"   provider={provider_name} model={model}", file=sys.stderr)

    import urllib.request, urllib.error

    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(api_url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
        # DeepSeek 响应可能包裹在 ```json ... ``` 中
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r'^```\w*\n?', '', content)
            content = re.sub(r'\n?```$', '', content)
        return json.loads(content)
    except Exception as e:
        print(f"❌ AI 调用失败: {e}", file=sys.stderr)
        if hasattr(e, 'read'):
            print(e.read().decode(), file=sys.stderr)
        sys.exit(1)


# ── 后处理：补 id ───────────────────────────────────────────
def _postprocess(flow: dict) -> dict:
    """为节点分配 id 并建立 parent_id 映射。"""
    nodes = flow.get("nodes", [])
    # 分配 id（用递增整数，从 1 开始）
    for i, node in enumerate(nodes):
        node["id"] = i + 1

    # 如果使用 order 做 parent_id 引用，转换为 id 引用
    order_to_id = {n["order"]: n["id"] for n in nodes}
    for node in nodes:
        pid = node.get("parent_id")
        if isinstance(pid, int) and pid in order_to_id:
            node["parent_id"] = order_to_id[pid]

    return flow


def _auto_fill_elements(flow: dict, elements: list):
    """AI 经常漏填 element_name，根据指令类型和可用元素自动补全。"""
    if not elements:
        return
    elem_to_cmd = {
        "getText": ["标题", "摘要", "内容", "正文"],
        "clickElement": ["按钮", "搜索", "提交"],
        "ifElementVisible": ["没有", "到底", "更多", "结果"],
        "ifElementExists": ["没有", "到底", "更多"],
        "forEachElement": ["列表", "卡片", "容器"],
    }
    for node in flow.get("nodes", []):
        if node.get("element_name"):
            continue
        t = node.get("type", "")
        hints = elem_to_cmd.get(t, [])
        found = None
        for hint in hints:
            for e in elements:
                if hint in e:
                    found = e
                    break
            if found:
                break
        if found:
            node["element_name"] = found
            print(f"   🔧 {t}: element_name 自动补全为 '{found}'", file=sys.stderr)


# ── 主入口 ──────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="AI 流程编排助手")
    parser.add_argument("--intent", "-i", required=True, help="自动化意图描述")
    parser.add_argument("--elements", "-e", default="", help="已捕获的元素名，逗号分隔")
    parser.add_argument("--workflow-id", "-w", type=int, default=None,
                        help="从指定工作流 ID 读取元素库（含选择器）")
    parser.add_argument("--output", "-o", help="输出 JSON 文件路径（默认输出到 stdout）")
    parser.add_argument("--raw", action="store_true", help="直接输出 AI 原始响应，不做后处理")
    args = parser.parse_args()

    elements = [e.strip() for e in args.elements.split(",") if e.strip()]

    # 从数据库加载元素定义（含选择器）
    elem_defs = []
    if args.workflow_id:
        elem_defs = _load_elements(args.workflow_id, elements)
        if not elem_defs:
            print("⚠️  未找到匹配的元素，请确认元素名和 workflow-id", file=sys.stderr)

    print("📋 加载指令清单...", file=sys.stderr)
    commands = _filter_commands(_load_commands())
    print(f"   共 {len(commands)} 个可用指令（已过滤），{len(elem_defs)} 个元素定义", file=sys.stderr)

    print("🤖 调用 AI...", file=sys.stderr)
    system = build_system_prompt(commands, elements)
    user = build_user_prompt(args.intent)

    flow = call_ai(system, user)

    if args.raw:
        result = flow
    else:
        flow = _postprocess(flow)

    # 补默认字段
    for node in flow.get("nodes", []):
        node.setdefault("parent_id", None)
        node.setdefault("element_name", None)
        node.setdefault("action", node["type"])
        extra = node.get("extra", {})
        extra.setdefault("onError", "stop")
        extra.setdefault("retryCount", 3)
        extra.setdefault("timeout", 10)
        extra.setdefault("humanLike", True)

    # 自动补全空元素名：根据指令类型猜匹配元素
    _auto_fill_elements(flow, elements)

    # 附加元素定义
    if elem_defs:
        flow["elements"] = elem_defs

    output = json.dumps(flow, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"✅ 已保存到 {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
