"""
Handler 模板 — 供 AI 代码生成使用。

占位符:
  {{type}}       — 指令类型名，如 setVar
  {{label}}      — 显示名，如 设置变量
  {{category}}   — 分类，如 变量操作
  {{ClassName}}  — Handler 类名，如 SetVarHandler
  {{params}}     — 参数定义 (Param 列表)
  {{body}}       — execute 方法体
"""

TEMPLATE = '''"""{{label}}"""
from src.runtime.workflow.handlers.registry import register_handler, Param


@register_handler(
    cmd=
    cmd="{{type}}",
    label="{{label}}",
    category="{{category}}",
    runtime="backend",
    icon="fa-circle",
    icon_color="text-gray-500",
    bg_color="bg-gray-50",
)
class {{ClassName}}Handler:
    params = [
{{params}}
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra") or {}
{{body}}
        runner.completed += 1
        runner.results.append({
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "status": "success",
            "result": {"{{type}}": True},
        })
        await runner._emit({
            "type": "stepComplete",
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "result": {"{{type}}": True},
        })
        return True
'''


def build_handler_code(definition: dict) -> str:
    """从指令 JSON 定义生成 handler 代码框架。"""
    type_name = definition.get("type", "example")
    label = definition.get("label", type_name)
    category = definition.get("category", "其他")
    class_name = "".join(p.capitalize() for p in type_name.replace("-", "_").split("_")) + "Handler"

    params = definition.get("params", [])
    param_lines = []
    for p in params:
        name = p.get("name", "")
        label_p = p.get("label", name)
        ptype = p.get("type", "str-input")
        parts = [f'        Param("{name}", "{label_p}", "{ptype}"']
        if p.get("required"):
            parts.append(", required=True")
        if "default" in p and p["default"] is not None:
            parts.append(f', default={repr(p["default"])}')
        if p.get("options"):
            parts.append(f', options={repr(p["options"])}')
        if p.get("group") and p["group"] != "主属性":
            parts.append(f', group="{p["group"]}"')
        parts.append("),")
        param_lines.append("".join(parts))

    param_block = "\n".join(param_lines) if param_lines else "        pass"

    return TEMPLATE.replace("{{type}}", type_name) \
                   .replace("{{label}}", label) \
                   .replace("{{category}}", category) \
                   .replace("{{ClassName}}", class_name) \
                   .replace("{{params}}", param_block) \
                   .replace("{{body}}", "        # TODO: implement business logic\n")
